"""Write a replay scenario in OpenSCENARIO XML 1.1.

Every moving track replays its trajectory with FollowTrajectoryAction (Polyline, absolute timing,
followingMode="position"), started by a SimulationTimeCondition at the track's first timestamp.
Static tracks are only placed, never moved.

An object exists only while it has data: one that starts later than PRESENCE_MARGIN after time 0 is
removed in Init (DeleteEntityAction) and added at its first pose (AddEntityAction) PRESENCE_MARGIN
before its first timestamp; one that ends before the scene does is removed PRESENCE_MARGIN after its
last timestamp. The margin covers esmini's time step, so the log holds the first and last sample.
Checked with esmini 3.9.0: a removed object has no columns in the CSV log rows of that time.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from real2sim.tracks import EGO_SIZE, EGO_WHEELBASE, WHEELBASE_RATIO, Scene, Track, entity_class

SubElement = ET.SubElement
PRESENCE_MARGIN = 0.1  # s, an object appears this long before its first sample and leaves this long after its last


def _num(value: float) -> str:
    return f"{value:.4f}"


def _world_position(parent: ET.Element, x: float, y: float, h: float) -> ET.Element:
    position = SubElement(parent, "Position")
    SubElement(position, "WorldPosition", x=_num(x), y=_num(y), h=_num(h))
    return position


def _sim_time_trigger(parent: ET.Element, tag: str, name: str, value: float, rule: str) -> None:
    trigger = SubElement(parent, tag)
    group = SubElement(trigger, "ConditionGroup")
    condition = SubElement(group, "Condition", name=name, delay="0", conditionEdge="none")
    by_value = SubElement(condition, "ByValueCondition")
    SubElement(by_value, "SimulationTimeCondition", value=_num(value), rule=rule)


def _bounding_box(parent: ET.Element, track: Track) -> None:
    length, width, height = track.size
    box = SubElement(parent, "BoundingBox")
    SubElement(box, "Center", x=_num(track.bbox_center_x), y="0", z=_num(height / 2))
    SubElement(box, "Dimensions", width=_num(width), length=_num(length), height=_num(height))


def _entity(entities: ET.Element, track: Track) -> None:
    kind, category = entity_class(track.category)
    obj = SubElement(entities, "ScenarioObject", name=track.name)
    if kind == "vehicle":
        node = SubElement(obj, "Vehicle", name=track.name, vehicleCategory=category)
        SubElement(node, "ParameterDeclarations")
        _bounding_box(node, track)
        SubElement(node, "Performance", maxSpeed="70", maxAcceleration="10", maxDeceleration="10")
        # esmini treats the reference point as the rear axle and shifts the bounding box when
        # RearAxle.positionX != 0, so the rear axle stays on the reference point. For annotated objects
        # the reference point is the box centre, so their "rear axle" is a nominal point there.
        axles = SubElement(node, "Axles")
        length, width, _ = track.size
        # the Renault Zoe wheelbase only for the nuScenes ego; an ego from a CSV has its own size
        zoe = track.category == "vehicle.ego" and tuple(track.size) == EGO_SIZE
        wheelbase = EGO_WHEELBASE if zoe else WHEELBASE_RATIO * length
        for tag, x in (("FrontAxle", wheelbase), ("RearAxle", 0.0)):
            SubElement(
                axles,
                tag,
                maxSteering="0.5",
                wheelDiameter="0.6",
                trackWidth=_num(width * 0.85),
                positionX=_num(x),
                positionZ="0.3",
            )
    elif kind == "pedestrian":
        node = SubElement(obj, "Pedestrian", name=track.name, mass="80", model=category, pedestrianCategory=category)
        SubElement(node, "ParameterDeclarations")
        _bounding_box(node, track)
    else:
        node = SubElement(obj, "MiscObject", name=track.name, mass="100", miscObjectCategory=category)
        SubElement(node, "ParameterDeclarations")
        _bounding_box(node, track)
    properties = SubElement(node, "Properties")
    SubElement(properties, "Property", name="nuscenes_category", value=track.category)


def _trajectory_event(maneuver: ET.Element, track: Track) -> None:
    event = SubElement(maneuver, "Event", name=f"replay_{track.name}", priority="overwrite", maximumExecutionCount="1")
    action = SubElement(event, "Action", name=f"follow_{track.name}")
    follow = SubElement(SubElement(SubElement(action, "PrivateAction"), "RoutingAction"), "FollowTrajectoryAction")
    trajectory = SubElement(SubElement(follow, "TrajectoryRef"), "Trajectory", name=f"traj_{track.name}", closed="false")
    SubElement(trajectory, "ParameterDeclarations")
    polyline = SubElement(SubElement(trajectory, "Shape"), "Polyline")
    start = float(track.t[0])
    for t, (x, y), h in zip(track.t, track.xy, track.yaw):
        vertex = SubElement(polyline, "Vertex", time=_num(t))
        _world_position(vertex, x, y, h)
    # Absolute timing: esmini starts a triggered action one step late, so relative timing would
    # replay every trajectory one time step behind the recording.
    SubElement(SubElement(follow, "TimeReference"), "Timing", domainAbsoluteRelative="absolute", scale="1", offset="0")
    SubElement(follow, "TrajectoryFollowingMode", followingMode="position")
    _sim_time_trigger(event, "StartTrigger", f"start_{track.name}", start, "greaterOrEqual")


def presence(track: Track, duration: float) -> tuple[float | None, float | None]:
    """(time the object is added, time it is removed); None when it is there from the start / to the end."""
    appear = float(track.t[0]) - PRESENCE_MARGIN
    vanish = float(track.t[-1]) + PRESENCE_MARGIN
    return (appear if appear > 0 else None), (vanish if vanish < duration else None)


def _entity_action(parent: ET.Element, name: str, track: Track | None = None) -> None:
    """GlobalAction removing the entity, or adding it at the track's first pose when track is given."""
    action = SubElement(SubElement(parent, "GlobalAction"), "EntityAction", entityRef=name)
    if track is None:
        SubElement(action, "DeleteEntityAction")
    else:
        _world_position(SubElement(action, "AddEntityAction"), track.xy[0, 0], track.xy[0, 1], track.yaw[0])


def _presence_event(maneuver: ET.Element, name: str, at: float, track: Track | None) -> None:
    kind = "appear" if track is not None else "vanish"
    event = SubElement(maneuver, "Event", name=f"{kind}_{name}", priority="parallel", maximumExecutionCount="1")
    _entity_action(SubElement(event, "Action", name=f"{kind}_{name}"), name, track)
    _sim_time_trigger(event, "StartTrigger", f"{kind}_{name}_at", at, "greaterOrEqual")


def build_xosc(scene: Scene, xodr_path: str | None = None, date: str | None = None) -> ET.ElementTree:
    root = ET.Element("OpenSCENARIO")
    SubElement(
        root,
        "FileHeader",
        revMajor="1",
        revMinor="1",
        date=date or datetime.now().replace(microsecond=0).isoformat(),
        description=f"real2sim replay of nuScenes {scene.name}",
        author="real2sim",
    )
    SubElement(root, "ParameterDeclarations")
    SubElement(root, "CatalogLocations")
    road = SubElement(root, "RoadNetwork")
    if xodr_path:
        SubElement(road, "LogicFile", filepath=xodr_path)

    entities = SubElement(root, "Entities")
    for track in scene.tracks:
        _entity(entities, track)

    storyboard = SubElement(root, "Storyboard")
    actions = SubElement(SubElement(storyboard, "Init"), "Actions")
    spans = {track.name: presence(track, scene.duration) for track in scene.tracks}
    # Every entity is placed; a late one is also removed (global actions come first in Init). esmini 3.9.0
    # logs an error when it removes an entity that was never placed, so the placement stays.
    for track in scene.tracks:
        if spans[track.name][0] is not None:
            _entity_action(actions, track.name)
    for track in scene.tracks:
        private = SubElement(actions, "Private", entityRef=track.name)
        teleport = SubElement(SubElement(private, "PrivateAction"), "TeleportAction")
        _world_position(teleport, track.xy[0, 0], track.xy[0, 1], track.yaw[0])

    movers = [track for track in scene.tracks if not track.is_static]
    timed = [track for track in scene.tracks if spans[track.name] != (None, None)]
    if movers or timed:
        act = SubElement(SubElement(storyboard, "Story", name="replay"), "Act", name="replay")
        if timed:
            group = SubElement(act, "ManeuverGroup", maximumExecutionCount="1", name="presence")
            SubElement(group, "Actors", selectTriggeringEntities="false")
            maneuver = SubElement(group, "Maneuver", name="presence")
            for track in timed:
                appear, vanish = spans[track.name]
                if appear is not None:
                    _presence_event(maneuver, track.name, appear, track)
                if vanish is not None:
                    _presence_event(maneuver, track.name, vanish, None)
        for track in movers:
            group = SubElement(act, "ManeuverGroup", maximumExecutionCount="1", name=f"group_{track.name}")
            actors = SubElement(group, "Actors", selectTriggeringEntities="false")
            SubElement(actors, "EntityRef", entityRef=track.name)
            _trajectory_event(SubElement(group, "Maneuver", name=f"maneuver_{track.name}"), track)
        _sim_time_trigger(act, "StartTrigger", "act_start", 0.0, "greaterOrEqual")
    _sim_time_trigger(storyboard, "StopTrigger", "end", scene.duration + 0.5, "greaterThan")

    tree = ET.ElementTree(root)
    ET.indent(tree)
    return tree


def write_xosc(scene: Scene, path: str | Path, xodr_path: str | None = None, date: str | None = None) -> Path:
    path = Path(path)
    build_xosc(scene, xodr_path, date).write(path, encoding="utf-8", xml_declaration=True)
    return path
