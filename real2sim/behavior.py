"""Stage 1 behaviour simulation: a vehicle ahead slows down or stops; the vehicles behind it react like
human drivers (docs/thiet-ke-kich-ban-hanh-vi.md, section 4).

Everything an event does not affect replays its nominal motion: the pilot reconstruction (the ego: its
recording). So an empty event reproduces the scene exactly, by construction, and only the vehicles whose
situation changes deviate from it.

Per vehicle, on a DT time grid:
  nominal   replays its nominal motion
  waiting   saw its leader deviate; still nominal during the reaction time REACTION
  driving   IDM car following (Treiber et al. 2000) on its own path: desired speed = the nominal speed at
            its plan clock tau, leader = the closest vehicle ahead on its path corridor, the stops of its
            nominal motion are virtual obstacles it waits at for the recorded dwell time
  late      back on its nominal motion, delayed: s(t) = s_nominal(t - delta)
  event     the event vehicle: jerk-limited braking to a stop or to half its speed, optional dwell,
            then driving
Updates use one common state per step, so the order of the agents does not matter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from real2sim.abstraction import reconstruct
from real2sim.tracks import Scene, Track

DT = 0.05  # s, the esmini step
REACTION = 1.0  # s, from seeing the leader deviate to acting
IDM_A = 1.5  # m/s^2, IDM maximum (comfortable) acceleration
IDM_B = 2.0  # m/s^2, IDM comfortable deceleration
MAX_DECEL = 8.0  # m/s^2, emergency braking limit of a car
HEAVY_MAX_DECEL = 5.0  # m/s^2, ... of trucks and buses (FMVSS 121: a loaded truck stops from 60 mph within
#                       250 ft, about 4.7 m/s^2 on average; a bus with standing passengers cannot brake harder)
HEAVY_CATEGORIES = ("vehicle.bus.bendy", "vehicle.bus.rigid", "vehicle.truck", "vehicle.construction",
                    "vehicle.trailer")
JERK_BRAKE = 10.0  # m/s^3, how fast braking may build up
JERK_NORMAL = 3.0  # m/s^3, how fast acceleration may build up / braking may ease
T_DEFAULT, T_RANGE = 1.2, (0.6, 2.5)  # s, desired time gap
S0_DEFAULT, S0_RANGE = 2.0, (1.0, 3.0)  # m, standstill gap
MIN_V0 = 1.0  # m/s, lowest IDM desired speed (stops are handled as virtual obstacles)
LOOKAHEAD = 60.0  # m, leader search distance (front bumper to rear bumper)
CORRIDOR_MARGIN = 0.5  # m, lateral slack of the path corridor
HEADING_TOL = math.radians(30.0)  # a moving leader must travel within this of the path direction
LEADER_HOLD = 2.0  # m, keep the previous leader unless another is closer by more than this
FOLLOW_MIN_TIME = 1.0  # s, a following relation counts after this long
DEV_SPEED = 0.3  # m/s, a leader slower than its nominal motion by this has deviated
DEV_LAG = 0.2  # m, ... or lagging its nominal position by this
STOP_SPEED = 0.3  # m/s, below this the nominal motion is stopped
STOP_MIN = 1.0  # s, a nominal stop lasts at least this long
STOP_REACH = 0.6  # m, close enough to a nominal stop point to wait there
REJOIN_SPEED = 0.05  # m/s, back on the plan when speed matches it this well ...
REJOIN_TIME = 1.0  # s, ... for this long, without a leader interaction
REJOIN_INTERACTION = 0.05  # IDM interaction term below which the leader no longer matters
STATIC_SPEED = 0.5  # m/s, a vehicle slower than this is a static obstacle (heading not checked)
ALONGSIDE_GAP = 0.0  # m, a vehicle whose nearest point is not ahead of the front bumper is beside, not ahead
WATCH_AHEAD = 2  # a driver notices a deviation of any of the nearest this many vehicles ahead (brake lights)
TRACK_GAIN = 1.0  # 1/s, speed feedback when following the plan freely
COOLNESS = 0.99  # enhanced IDM coolness factor (Kesting et al. 2010)
STOP_S0 = 0.3  # m, how close to a nominal stop point a driver pulls up

NOMINAL, WAITING, DRIVING, LATE, EVENT = range(5)
MODE_NAMES = ("nominal", "waiting", "driving", "late", "event")


def _wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


# ---------------------------------------------------------------------------- paths
class Path:
    """A polyline parametrised by arc length s, with a heading along it."""

    RES = 0.5  # m, spacing of the samples used for projection

    def __init__(self, xy, heading):
        xy = np.asarray(xy, float).reshape(-1, 2)
        heading = np.unwrap(np.asarray(heading, float).reshape(-1))
        step = np.hypot(*np.diff(xy, axis=0).T) if len(xy) > 1 else np.zeros(0)
        keep = np.concatenate([[True], step > 1e-6])
        self.xy, self.h = xy[keep], heading[keep]
        self.s = np.concatenate([[0.0], np.cumsum(step[step > 1e-6])])
        self.length = float(self.s[-1])
        n = max(2, int(math.ceil(self.length / self.RES)) + 1)
        self.ds = np.linspace(0.0, self.length, n)
        self.dxy = self.pos(self.ds)
        self.dh = self.heading(self.ds)

    def pos(self, s):
        s = np.clip(np.asarray(s, float), 0.0, self.length)
        if len(self.s) == 1:
            return np.broadcast_to(self.xy[0], (*s.shape, 2)).copy()
        return np.stack([np.interp(s, self.s, self.xy[:, k]) for k in (0, 1)], axis=-1)

    def heading(self, s):
        s = np.clip(np.asarray(s, float), 0.0, self.length)
        return np.interp(s, self.s, self.h) if len(self.s) > 1 else np.full(s.shape, self.h[0])

    def project_many(self, points, s_lo: float, s_hi: float):
        """(arc length, signed lateral offset, path heading) of each point (P, 2), searched in [s_lo, s_hi]
        only; None when that window holds no path sample."""
        i0 = int(np.searchsorted(self.ds, max(s_lo, 0.0), "left"))
        i1 = int(np.searchsorted(self.ds, min(s_hi, self.length), "right"))
        if i1 <= i0:
            return None
        d = points[:, None, :] - self.dxy[None, i0:i1, :]
        k = i0 + np.argmin(np.einsum("pij,pij->pi", d, d), axis=1)
        c, s = np.cos(self.dh[k]), np.sin(self.dh[k])
        rx, ry = points[:, 0] - self.dxy[k, 0], points[:, 1] - self.dxy[k, 1]
        return self.ds[k] + rx * c + ry * s, c * ry - s * rx, self.dh[k]

    def project(self, point, s_lo: float, s_hi: float):
        """(arc length, signed lateral offset, path heading) of point, searched in [s_lo, s_hi] only
        (a local window, so a point is never projected onto another branch); None outside the path."""
        i0 = int(np.searchsorted(self.ds, max(s_lo, 0.0), "left"))
        i1 = int(np.searchsorted(self.ds, min(s_hi, self.length), "right"))
        if i1 <= i0:
            return None
        d = self.dxy[i0:i1] - point
        k = i0 + int(np.argmin(np.einsum("ij,ij->i", d, d)))
        c, s = math.cos(self.dh[k]), math.sin(self.dh[k])
        rx, ry = point[0] - self.dxy[k, 0], point[1] - self.dxy[k, 1]
        return self.ds[k] + rx * c + ry * s, c * ry - s * rx, self.dh[k]


# ---------------------------------------------------------------------------- agents
@dataclass
class Agent:
    name: str
    kind: str  # vehicle | pedestrian | misc
    is_ego: bool
    static: bool
    length: float
    width: float
    centre_x: float  # box centre ahead of the reference point
    path: Path
    k0: int  # first grid step present
    k1: int  # last grid step present
    s_nom: np.ndarray  # (K,) progress along the path, nan when absent
    v_nom: np.ndarray  # (K,) nominal speed, nan when absent
    stops: list = field(default_factory=list)  # (s_star, k_start, k_end) of nominal stops
    T: float = T_DEFAULT
    s0: float = S0_DEFAULT
    max_decel: float = MAX_DECEL  # m/s^2, its emergency braking limit
    T_measured: bool = False  # T and s0 measured on its own recording (else the defaults)
    s0_measured: bool = False

    @property
    def vehicle(self) -> bool:
        return self.kind == "vehicle"

    @property
    def front(self) -> float:
        """Front bumper ahead of the reference point."""
        return self.centre_x + self.length / 2

    def centre(self, s: float):
        ref = self.path.pos(s)
        h = float(self.path.heading(s))
        return ref[0] + self.centre_x * math.cos(h), ref[1] + self.centre_x * math.sin(h), h


class SceneModel:
    """Nominal motion of every object of a scene on the DT grid, the nominal leader of every vehicle,
    and each vehicle's following parameters measured on its own recording."""

    def __init__(self, gt: Scene):
        self.name = gt.name
        self.duration = float(gt.duration)
        self.K = int(math.floor(self.duration / DT + 1e-9)) + 1
        self.t = np.arange(self.K) * DT
        recon = {tr.name: tr for tr in reconstruct(gt, "pilot").tracks}
        self.agents = [self._agent(tr, tr if tr.name == "ego" else recon[tr.name]) for tr in gt.tracks]
        self.index = {a.name: i for i, a in enumerate(self.agents)}
        n = len(self.agents)
        self.S = np.full((self.K, n), np.nan)
        self.V = np.full((self.K, n), np.nan)
        self.X = np.full((self.K, n), np.nan)
        self.Y = np.full((self.K, n), np.nan)
        self.H = np.full((self.K, n), np.nan)
        for i, a in enumerate(self.agents):
            k = slice(a.k0, a.k1 + 1)
            self.S[k, i], self.V[k, i] = a.s_nom[k], a.v_nom[k]
            ref = a.path.pos(a.s_nom[k])
            h = a.path.heading(a.s_nom[k])
            self.X[k, i] = ref[:, 0] + a.centre_x * np.cos(h)
            self.Y[k, i] = ref[:, 1] + a.centre_x * np.sin(h)
            self.H[k, i] = h
        self.present = ~np.isnan(self.S)
        self.vehicles = np.array([a.vehicle for a in self.agents])
        self.movers = np.array([a.vehicle and not a.static for a in self.agents])
        self.half_length = np.array([a.length / 2 for a in self.agents])
        self.half_diag = np.array([math.hypot(a.length, a.width) / 2 for a in self.agents])
        self.outlines = [outline(0.0, 0.0, 0.0, a.length, a.width) for a in self.agents]  # box frame
        self.leader, self.gap = self._nominal_leaders()
        self._calibrate()

    # ------------------------------------------------------------------ building
    def _agent(self, raw: Track, nominal: Track) -> Agent:
        kind = raw.kind
        static = raw.name != "ego" and (raw.is_stationary or nominal.is_static)
        t0, t1 = float(raw.t[0]), float(raw.t[-1])
        k0 = min(self.K - 1, max(0, int(math.ceil(t0 / DT - 1e-6))))
        k1 = min(self.K - 1, max(k0, int(math.floor(t1 / DT + 1e-6))))
        s_nom = np.full(self.K, np.nan)
        v_nom = np.full(self.K, np.nan)
        length, width, _ = raw.size
        if static:
            path = Path(nominal.xy[:1], nominal.yaw[:1])
            s_nom[k0:k1 + 1] = 0.0
            v_nom[k0:k1 + 1] = 0.0
        else:
            path = Path(nominal.xy, nominal.yaw)
            s_track = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(nominal.xy, axis=0).T))])
            s_track = np.maximum.accumulate(s_track)
            tk = self.t[k0:k1 + 1]
            s_nom[k0:k1 + 1] = np.clip(np.interp(tk, nominal.t, s_track), 0.0, path.length)
            v_nom[k0:k1 + 1] = np.gradient(s_nom[k0:k1 + 1], DT) if k1 > k0 else 0.0
        agent = Agent(raw.name, kind, raw.name == "ego", static, float(length), float(width),
                      float(raw.bbox_center_x), path, k0, k1, s_nom, v_nom,
                      max_decel=HEAVY_MAX_DECEL if raw.category in HEAVY_CATEGORIES else MAX_DECEL)
        if not static:
            agent.stops = self._stops(agent)
        return agent

    def _stops(self, a: Agent) -> list:
        """Nominal stops: at least STOP_MIN slower than STOP_SPEED, then moving again."""
        v = a.v_nom[a.k0:a.k1 + 1]
        slow = v < STOP_SPEED
        stops, k = [], 0
        while k < len(v):
            if not slow[k]:
                k += 1
                continue
            j = k
            while j + 1 < len(v) and slow[j + 1]:
                j += 1
            if (j - k + 1) * DT >= STOP_MIN and j + 1 < len(v) and v[j + 1:].max() > 1.0:
                stops.append((float(a.s_nom[a.k0 + k]), a.k0 + k, a.k0 + j))
            k = j + 1
        return stops

    def _nominal_leaders(self):
        n = len(self.agents)
        leader = np.full((self.K, n), -1, int)
        gap = np.full((self.K, n), np.nan)
        for i, a in enumerate(self.agents):
            if not self.movers[i]:
                continue
            prev = -1
            for k in range(a.k0, a.k1 + 1):
                j, g = find_leader(self, i, a.s_nom[k], self.X[k], self.Y[k], self.H[k], self.V[k],
                                   self.present[k], prev)
                leader[k, i], gap[k, i] = j, g
                prev = j
        return leader, gap

    def _calibrate(self):
        """T: median time gap while steadily following above 3 m/s; s0: smallest gap with both stopped."""
        hold = int(round(FOLLOW_MIN_TIME / DT))
        for i, a in enumerate(self.agents):
            if not self.movers[i]:
                continue
            lead, g, v = self.leader[:, i], self.gap[:, i], self.V[:, i]
            steady = np.zeros(self.K, bool)
            run = 0
            for k in range(self.K):
                run = run + 1 if lead[k] >= 0 and k > 0 and lead[k] == lead[k - 1] else (1 if lead[k] >= 0 else 0)
                steady[k] = run >= hold
            following = steady & (v > 3.0) & (g > 0)
            if following.sum() >= hold:
                a.T = float(np.clip(np.median(g[following] / v[following]), *T_RANGE))
                a.T_measured = True
            lead_v = np.array([self.V[k, lead[k]] if lead[k] >= 0 else np.nan for k in range(self.K)])
            stopped = steady & (v < STOP_SPEED) & (lead_v < STOP_SPEED) & (g > 0)
            if stopped.any():
                a.s0 = float(np.clip(g[stopped].min(), *S0_RANGE))
                a.s0_measured = True

    # ------------------------------------------------------------------ helpers
    def tau_of_s(self, i: int, s: float) -> float:
        """Earliest nominal time at which agent i reaches progress s."""
        a = self.agents[i]
        sn = a.s_nom[a.k0:a.k1 + 1]
        k = int(np.searchsorted(sn, s - 1e-9, "left"))
        if k <= 0:
            return float(self.t[a.k0])
        if k >= len(sn):
            return float(self.t[a.k1])
        s_lo, s_hi = sn[k - 1], sn[k]
        frac = 0.0 if s_hi <= s_lo else (s - s_lo) / (s_hi - s_lo)
        return float(self.t[a.k0 + k - 1] + frac * DT)

    def nominal_at(self, i: int, tau: float):
        """(progress, speed) of agent i's nominal motion at time tau (clamped to its span)."""
        a = self.agents[i]
        tk = self.t[a.k0:a.k1 + 1]
        return (float(np.interp(tau, tk, a.s_nom[a.k0:a.k1 + 1])),
                float(np.interp(tau, tk, a.v_nom[a.k0:a.k1 + 1])))

    def nominal_accel(self, i: int, tau: float) -> float:
        a = self.agents[i]
        if a.k1 <= a.k0:
            return 0.0
        tk = self.t[a.k0:a.k1 + 1]
        return float(np.interp(tau, tk, np.gradient(a.v_nom[a.k0:a.k1 + 1], DT)))


def outline(cx: float, cy: float, h: float, length: float, width: float, step: float = 1.0):
    """Points on a box outline, at most `step` apart (a long box at an angle can block a path even when
    its centre is well off it)."""
    c, s = math.cos(h), math.sin(h)
    lx, ly = length / 2, width / 2
    corners = [(-lx, -ly), (lx, -ly), (lx, ly), (-lx, ly)]
    pts = []
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
        n = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / step)))
        u = np.arange(n) / n
        px, py = x0 + u * (x1 - x0), y0 + u * (y1 - y0)
        pts.append(np.column_stack([cx + px * c - py * s, cy + px * s + py * c]))
    return np.vstack(pts)


def find_leader(model: SceneModel, i: int, s_i: float, cx, cy, ch, cv, present, prev: int = -1):
    """Closest vehicle ahead of agent i whose box reaches into i's path corridor (the strip of i's own
    width plus CORRIDOR_MARGIN): (index, bumper gap along the path), or (-1, nan). A moving vehicle must
    travel along the path (within HEADING_TOL); one crossing it is not a leader (stage 1 does not handle
    crossings). A vehicle slower than STATIC_SPEED blocking the corridor is a leader at any angle.
    cx, cy, ch, cv, present: box centres, headings, speeds and presence of every agent at this instant.
    prev: the previous leader, kept unless another is closer by more than LEADER_HOLD."""
    ahead = vehicles_ahead(model, i, s_i, cx, cy, ch, cv, present)
    if not ahead:
        return -1, float("nan")
    best_gap, best = ahead[0]
    for g, j in ahead:
        if j == prev and g <= best_gap + LEADER_HOLD:
            return j, g
    return best, best_gap


def vehicles_ahead(model: SceneModel, i: int, s_i: float, cx, cy, ch, cv, present) -> list:
    """Every vehicle ahead in agent i's path corridor (see find_leader), as (bumper gap, index), closest first."""
    a = model.agents[i]
    hx, hy = a.centre(s_i)[:2]
    dx, dy = cx - hx, cy - hy
    h_i = float(a.path.heading(s_i))
    reach = model.half_length
    ahead = dx * math.cos(h_i) + dy * math.sin(h_i) > -a.length / 2 - reach
    near = present & model.vehicles & ahead & (np.hypot(dx, dy) < LOOKAHEAD + a.length + reach + 5.0)
    near[i] = False
    half = a.width / 2 + CORRIDOR_MARGIN
    window = (s_i, s_i + a.front + LOOKAHEAD + 1.0)
    cand = np.flatnonzero(near)
    if not len(cand):
        return []
    # cheap reject, all candidates at once: a centre further from the path than its box can reach
    centre = a.path.project_many(np.column_stack([cx[cand], cy[cand]]), *window)
    if centre is None:
        return []
    cand = cand[np.abs(centre[1]) <= half + model.half_diag[cand]]
    if not len(cand):
        return []
    # every candidate's outline, projected in one go
    c, s = np.cos(ch[cand]), np.sin(ch[cand])
    sizes = np.array([len(model.outlines[j]) for j in cand])
    owner = np.repeat(np.arange(len(cand)), sizes)
    local = np.vstack([model.outlines[j] for j in cand])
    pts = np.column_stack([cx[cand][owner] + local[:, 0] * c[owner] - local[:, 1] * s[owner],
                           cy[cand][owner] + local[:, 0] * s[owner] + local[:, 1] * c[owner]])
    along, lateral, h_path = a.path.project_many(pts, *window)
    inside = (np.abs(lateral) < half) & (along > s_i)
    nearest = np.where(inside, along, np.inf)
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    first = np.minimum.reduceat(nearest, starts)
    found = []
    for n, j in enumerate(cand):
        if not np.isfinite(first[n]):
            continue
        if cv[j] > STATIC_SPEED:  # a moving vehicle must travel along the path, not across it
            k = starts[n] + int(np.argmin(nearest[starts[n]:starts[n] + sizes[n]]))
            if abs(_wrap(ch[j] - h_path[k])) > HEADING_TOL:
                continue
        g = float(first[n]) - s_i - a.front
        if g < ALONGSIDE_GAP or g > LOOKAHEAD:  # beside or overlapping (not ahead), or too far
            continue
        found.append((g, int(j)))
    return sorted(found)


# ---------------------------------------------------------------------------- events
@dataclass(frozen=True)
class Event:
    actor: str
    t0: float  # s, braking starts
    decel: float  # m/s^2
    target: str  # "stop" | "half"
    dwell: float = 0.0  # s standing still, for target "stop"


@dataclass
class Outcome:
    """Progress of every agent whose motion differs from nominal (nan when absent), and what happened."""

    event: Event
    react: bool
    S: np.ndarray  # (K, N) progress of every agent (nominal where unchanged)
    V: np.ndarray  # (K, N) speed
    A: np.ndarray  # (K, N) commanded acceleration (0 where nominal)
    changed: np.ndarray  # (N,) motion differs from nominal at some time
    stimulus: dict  # agent -> time it saw its leader deviate
    driving_from: dict  # agent -> time it started driving itself
    event_phases: dict  # brake_start, target_reached, dwell_end
    entered: dict = field(default_factory=dict)  # agent -> time it entered the data behind a changed situation
    mode: np.ndarray | None = None  # (K, N) mode of every agent at every step (NOMINAL ... EVENT)
    leader: np.ndarray | None = None  # (K, N) the leader a driving agent followed (-1: none or not driving)
    gap: np.ndarray | None = None  # (K, N) bumper gap to that leader (nan: none or not driving)
    reaction: float = REACTION  # s, the reaction time used


def enhanced_idm(v: float, v0: float, gap: float, v_l: float, a_l: float, s0: float, T: float):
    """(IDM interaction term (s*/gap)^2, acceleration) of the enhanced IDM ("ACC model": Kesting, Treiber
    and Helbing 2010; Treiber and Kesting, Traffic Flow Dynamics, 2013, section 11.3.5).

    The plain IDM brakes strongly whenever the gap is well below its desired gap, even if the leader is
    pulling away. The constant-acceleration heuristic (CAH) asks instead: if the leader keeps its current
    acceleration, how hard must I brake to just not hit it? Where the IDM brakes harder than the CAH, the
    two are blended with a coolness factor COOLNESS."""
    g = max(gap, 0.05)
    dv = v - v_l
    s_star = s0 + max(0.0, v * T + v * dv / (2 * math.sqrt(IDM_A * IDM_B)))
    term = (s_star / g) ** 2
    a_idm = IDM_A * (1.0 - (v / v0) ** 4 - term)
    a_l = min(a_l, IDM_A)
    denom = v_l * v_l - 2 * g * a_l
    if v_l * dv <= -2 * g * a_l and denom > 1e-9:
        a_cah = v * v * a_l / denom
    else:
        a_cah = a_l - max(dv, 0.0) ** 2 / (2 * g)
    if a_idm >= a_cah:
        return term, a_idm
    return term, (1 - COOLNESS) * a_idm + COOLNESS * (a_cah + IDM_B * math.tanh((a_idm - a_cah) / IDM_B))


def _accel_of(model, j, k, t, mode, changed, A, delta) -> float:
    """Current acceleration of agent j: commanded when it drives itself, else that of its (delayed) plan."""
    if changed[j] and mode[j] in (DRIVING, EVENT):
        return float(A[k, j])
    if changed[j]:
        return model.nominal_accel(j, t - delta[j])
    return model.nominal_accel(j, t)


def _integrate(s: float, v: float, a: float, dt: float = DT):
    """One step at constant acceleration; a stop inside the step ends exactly at standstill."""
    v1 = v + a * dt
    if v1 < 0.0:
        return (s + v * v / (-2.0 * a) if a < 0 else s), 0.0
    return s + v * dt + 0.5 * a * dt * dt, v1


def _jerk_limited(a_prev: float, a_target: float, brake_jerk: float = JERK_BRAKE) -> float:
    """Acceleration after one step towards a_target. A driver who must brake while accelerating takes the
    foot off the throttle first: the drive force goes at once, then braking builds up from zero."""
    if a_target < a_prev:
        if a_target < 0.0 < a_prev:
            a_prev = 0.0
        return max(a_target, a_prev - brake_jerk * DT)
    return min(a_target, a_prev + JERK_NORMAL * DT)


def simulate(model: SceneModel, event: Event, react: bool = True, reaction: float = REACTION) -> Outcome:
    """Run one event. react=False: only the event vehicle changes, everyone else replays (baseline).
    reaction: the drivers' reaction time (REACTION; other values for sensitivity checks)."""
    n, K = len(model.agents), model.K
    mode_hist = np.zeros((K, n), np.int8)
    leader_hist = np.full((K, n), -1, int)
    gap_hist = np.full((K, n), np.nan)
    S, V = model.S.copy(), model.V.copy()
    A = np.zeros((K, n))
    mode = np.full(n, NOMINAL)
    changed = np.zeros(n, bool)
    tau = np.full(n, np.nan)  # plan clock of driving agents
    drive_at = np.full(n, np.inf)  # waiting agents start driving at this time
    delta = np.zeros(n)
    rejoin = np.zeros(n)
    dwelling = np.full(n, -1)  # index into agent.stops while waiting at a nominal stop
    done_stops = [set() for _ in range(n)]
    stimulus, driving_from, phases, entered = {}, {}, {}, {}
    e = model.index[event.actor]
    k_event = int(round(event.t0 / DT))
    phase, v_target, dwell_until = None, 0.0, None
    present = model.present.copy()

    for k in range(K - 1):
        t = k * DT
        # ---------------- positions now (unchanged agents: nominal rows)
        cx, cy, ch = model.X[k].copy(), model.Y[k].copy(), model.H[k].copy()
        cv = V[k].copy()
        for i in np.flatnonzero(changed):
            if present[k, i]:
                cx[i], cy[i], ch[i] = model.agents[i].centre(S[k, i])
        pres = present[k]

        # ---------------- the event vehicle takes over
        if k == k_event and pres[e] and mode[e] == NOMINAL:
            mode[e], changed[e] = EVENT, True
            phase = "brake"
            v_target = 0.0 if event.target == "stop" else 0.5 * V[k, e]
            phases["brake_start"] = t

        # ---------------- who notices a deviating leader (react only)
        live = np.flatnonzero(changed & pres)
        if react and len(live):
            watchers = model.movers & pres & ((mode == NOMINAL) | (mode == LATE))
            # only vehicles near a changed one can see it among the nearest vehicles ahead
            d = np.hypot(cx[:, None] - cx[live][None, :], cy[:, None] - cy[live][None, :])
            watchers &= np.nanmin(np.where(np.isnan(d), np.inf, d), axis=1) < LOOKAHEAD + 30.0
            for i in np.flatnonzero(watchers):
                deviates = False
                for g, j in vehicles_ahead(model, i, S[k, i], cx, cy, ch, cv, pres)[:WATCH_AHEAD]:
                    if not changed[j]:
                        continue
                    if mode[i] == NOMINAL:
                        deviates = V[k, j] < model.V[k, j] - DEV_SPEED or model.S[k, j] - S[k, j] > DEV_LAG \
                            or np.isnan(model.S[k, j])
                    else:  # late: react when a vehicle ahead is still being driven and too close
                        a_i = model.agents[i]
                        deviates = mode[j] in (DRIVING, EVENT) and g < a_i.s0 + V[k, i] * a_i.T
                    if deviates:
                        break
                if deviates and mode[i] == NOMINAL and k == model.agents[i].k0:
                    # it only now enters the recorded data, behind a situation that had already changed:
                    # in reality it was there before and saw it, so it drives itself at once
                    mode[i], changed[i] = DRIVING, True
                    tau[i] = t
                    A[k, i] = model.nominal_accel(i, t)
                    entered.setdefault(model.agents[i].name, t)
                    driving_from.setdefault(model.agents[i].name, t)
                    continue
                if deviates:
                    if mode[i] == LATE:  # keep its delayed state while reacting
                        changed[i] = True
                    mode[i], drive_at[i] = WAITING, t + reaction
                    stimulus.setdefault(model.agents[i].name, t)
            for i in np.flatnonzero(mode == WAITING):
                if t + 1e-9 >= drive_at[i] and not np.isnan(S[k, i]):
                    tau[i] = min(model.tau_of_s(i, S[k, i]), t)
                    if not changed[i]:  # starts from its nominal motion, acceleration included
                        A[k, i] = model.nominal_accel(i, tau[i])
                    mode[i], changed[i] = DRIVING, True
                    driving_from.setdefault(model.agents[i].name, t)
                    rejoin[i] = 0.0

        # ---------------- commands and integration
        for i in range(n):
            if not changed[i] or not pres[i] or np.isnan(S[k, i]):
                continue
            a_i = model.agents[i]
            s, v, a_prev = S[k, i], V[k, i], A[k, i]
            if mode[i] in (LATE, WAITING):  # delayed nominal motion (also while reacting again)
                s1, v1 = model.nominal_at(i, t + DT - delta[i])
                S[k + 1, i], V[k + 1, i] = s1, v1
                continue
            if mode[i] == EVENT:
                if phase == "brake":
                    a_cmd = _jerk_limited(a_prev, -event.decel)
                    s1, v1 = _integrate(s, v, a_cmd)
                    if v1 <= v_target + 1e-9:
                        phases["target_reached"] = t + DT
                        if event.target == "stop":
                            v1, phase, dwell_until = 0.0, "dwell", t + DT + event.dwell
                        else:
                            v1 = v_target
                            mode[i], phase = DRIVING, "done"
                            tau[i] = min(model.tau_of_s(i, s1), t + DT)
                            driving_from.setdefault(a_i.name, t + DT)
                elif phase == "dwell":
                    a_cmd, s1, v1 = 0.0, s, 0.0
                    if t + DT + 1e-9 >= dwell_until:
                        phases["dwell_end"] = t + DT
                        mode[i], phase = DRIVING, "done"
                        tau[i] = min(model.tau_of_s(i, s), t + DT)
                        driving_from.setdefault(a_i.name, t + DT)
                if s1 >= a_i.path.length - 1e-6 and a_i.path.length > 0:  # end of its recorded path: gone
                    S[k + 1:, i], V[k + 1:, i] = np.nan, np.nan
                    present[k + 1:, i] = False
                    continue
                S[k + 1, i], V[k + 1, i], A[k + 1, i] = s1, v1, a_cmd
                continue
            # ---- driving: IDM with the plan clock
            stop = dwelling[i]
            if stop >= 0:
                s_star, ks, ke = a_i.stops[stop]
                tau[i] = min(tau[i] + DT, t + DT)
                if tau[i] >= model.t[ke]:
                    done_stops[i].add(stop)
                    dwelling[i] = -1
                S[k + 1, i], V[k + 1, i], A[k + 1, i] = s, 0.0, 0.0
                continue
            obstacles = []  # (gap, speed, acceleration, s0, T) of the leader and of a nominal stop ahead
            j, g = find_leader(model, i, s, cx, cy, ch, cv, pres)
            leader_hist[k, i], gap_hist[k, i] = j, g
            if j >= 0:
                along = math.cos(_wrap(ch[j] - float(a_i.path.heading(s))))
                obstacles.append((g, cv[j] * along, _accel_of(model, j, k, t, mode, changed, A, delta) * along,
                                  a_i.s0, a_i.T))
            for idx, (s_stop, ks, ke) in enumerate(a_i.stops):
                if idx in done_stops[i] or s_stop < s - STOP_REACH or model.t[ke] <= tau[i]:
                    continue
                g_stop = s_stop - s
                if abs(g_stop) < STOP_REACH and v < 0.1:
                    dwelling[i] = idx
                    tau[i] = max(tau[i], model.t[ks])
                    break
                if g_stop < LOOKAHEAD:
                    obstacles.append((g_stop, 0.0, 0.0, STOP_S0, 0.0))
                break
            if dwelling[i] >= 0:
                S[k + 1, i], V[k + 1, i], A[k + 1, i] = s, 0.0, 0.0
                continue
            v_plan = model.nominal_at(i, tau[i])[1]
            # free: follow the plan (its acceleration plus speed feedback); a leader or a stop ahead: the
            # enhanced IDM (IDM blended with the constant-acceleration heuristic, so it brakes hard only
            # when the situation needs it, not merely because the gap is shorter than it would like)
            a_free = float(np.clip(model.nominal_accel(i, tau[i]) + TRACK_GAIN * (v_plan - v), -IDM_B, IDM_A))
            a_target, interaction = a_free, 0.0
            v0 = max(v_plan, MIN_V0)
            for gap_o, v_l, a_l, s0_o, T_o in obstacles:
                term, a_o = enhanced_idm(v, v0, gap_o, v_l, a_l, s0_o, T_o)
                interaction = max(interaction, term)
                if term >= REJOIN_INTERACTION:
                    a_target = min(a_target, a_o)
            a_cmd = _jerk_limited(a_prev, float(np.clip(a_target, -a_i.max_decel, IDM_A)))
            s1, v1 = _integrate(s, v, a_cmd)
            if s1 >= a_i.path.length - 1e-6 and a_i.path.length > 0:  # reached the end of its recorded path
                S[k + 1:, i], V[k + 1:, i] = np.nan, np.nan
                present[k + 1:, i] = False
                continue
            S[k + 1, i], V[k + 1, i], A[k + 1, i] = s1, v1, a_cmd
            tau[i] = min(max(tau[i], model.tau_of_s(i, s1)), t + DT)
            if abs(v1 - model.nominal_at(i, tau[i])[1]) < REJOIN_SPEED and interaction < REJOIN_INTERACTION:
                rejoin[i] += DT
                if rejoin[i] >= REJOIN_TIME:
                    mode[i], delta[i] = LATE, t + DT - tau[i]
            else:
                rejoin[i] = 0.0
        mode_hist[k] = mode
        # agents that stay nominal keep the nominal rows of S and V
        # delayed agents stay present until their delayed motion ends
        for i in np.flatnonzero(changed & ((mode == LATE) | (mode == WAITING))):
            a_i = model.agents[i]
            if t + DT - delta[i] > model.t[a_i.k1] + 1e-9:
                S[k + 1:, i], V[k + 1:, i] = np.nan, np.nan
                present[k + 1:, i] = False
            else:
                present[k + 1, i] = True
        for i in np.flatnonzero(changed & ((mode == DRIVING) | (mode == EVENT))):
            if not np.isnan(S[k + 1, i]):
                present[k + 1, i] = True
    mode_hist[K - 1] = mode
    return Outcome(event, react, S, V, A, changed, stimulus, driving_from, phases, entered, mode_hist, leader_hist,
                   gap_hist, reaction)


def poses(model: SceneModel, outcome: Outcome, i: int):
    """(t, reference xy, heading) of agent i in an outcome, where present."""
    a = model.agents[i]
    s = outcome.S[:, i]
    ok = ~np.isnan(s)
    ref = a.path.pos(s[ok])
    return model.t[ok], ref, a.path.heading(s[ok])


def centres(model: SceneModel, outcome: Outcome):
    """Box centres and headings of every agent on the grid (K, N), nan when absent."""
    X, Y, H = model.X.copy(), model.Y.copy(), model.H.copy()
    for i in np.flatnonzero(outcome.changed):
        a = model.agents[i]
        s = outcome.S[:, i]
        ok = ~np.isnan(s)
        X[:, i] = Y[:, i] = H[:, i] = np.nan
        if ok.any():
            ref = a.path.pos(s[ok])
            h = a.path.heading(s[ok])
            X[ok, i] = ref[:, 0] + a.centre_x * np.cos(h)
            Y[ok, i] = ref[:, 1] + a.centre_x * np.sin(h)
            H[ok, i] = h
    return X, Y, H
