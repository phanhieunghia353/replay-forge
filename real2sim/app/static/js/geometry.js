// Shared geometry for both viewers (top-down and 3D). World frame: metres, x east, y north.
// A track's poses are {t, x, y, yaw} arrays; see track_poses() in real2sim/app/api.py.

// An object is shown only while it is annotated (inside its gt time span).
export function present(track, t) {
  const times = track.gt.t;
  return t >= times[0] - 1e-6 && t <= times[times.length - 1] + 1e-6;
}

// Pose at time t by linear interpolation; null outside the sampled span. A single-sample track
// (stationary object in pilot) is valid at any time.
export function poseAt(poses, t) {
  const times = poses.t;
  const n = times.length;
  if (n === 1) return { x: poses.x[0], y: poses.y[0], yaw: poses.yaw[0] };
  if (t < times[0] - 1e-6 || t > times[n - 1] + 1e-6) return null;
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; (times[mid] <= t ? (lo = mid) : (hi = mid)); }
  const span = times[hi] - times[lo];
  const u = span > 0 ? Math.min(Math.max((t - times[lo]) / span, 0), 1) : 0;
  let dyaw = poses.yaw[hi] - poses.yaw[lo];
  dyaw = Math.atan2(Math.sin(dyaw), Math.cos(dyaw));
  return {
    x: poses.x[lo] + u * (poses.x[hi] - poses.x[lo]),
    y: poses.y[lo] + u * (poses.y[hi] - poses.y[lo]),
    yaw: poses.yaw[lo] + u * dyaw,
  };
}

// Box centre: bbox_center_x metres ahead of the reference point (the ego's rear axle; 0 otherwise).
export function boxCentre(track, pose) {
  return [pose.x + track.bbox_center_x * Math.cos(pose.yaw), pose.y + track.bbox_center_x * Math.sin(pose.yaw)];
}

// Corners rear-right, front-right, front-left, rear-left (so corners[1]..[2] is the front edge).
export function boxCorners(track, pose) {
  const [cx, cy] = boxCentre(track, pose);
  const [length, width] = track.size;
  const c = Math.cos(pose.yaw), s = Math.sin(pose.yaw);
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([u, v]) => {
    const lx = (u * length) / 2, ly = (v * width) / 2;
    return [cx + lx * c - ly * s, cy + lx * s + ly * c];
  });
}

export function zip(poses) {
  return poses.x.map((x, i) => [x, poses.y[i]]);
}

// Bounds of all annotated positions: [xmin, ymin, xmax, ymax].
export function sceneBounds(scene) {
  let [xmin, ymin, xmax, ymax] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const track of scene.tracks) {
    for (let i = 0; i < track.gt.x.length; i++) {
      xmin = Math.min(xmin, track.gt.x[i]); xmax = Math.max(xmax, track.gt.x[i]);
      ymin = Math.min(ymin, track.gt.y[i]); ymax = Math.max(ymax, track.gt.y[i]);
    }
  }
  return [xmin, ymin, xmax, ymax];
}
