// Colours used for drawing, read from the CSS variables at the top of style.css (change them there).

export function readColors() {
  const css = getComputedStyle(document.documentElement);
  const get = (name) => css.getPropertyValue(name).trim();
  return {
    ground: get("--map-ground"), drivable: get("--map-drivable"), carpark: get("--map-carpark"),
    walkway: get("--map-walkway"), crossing: get("--map-crossing"), laneEdge: get("--map-lane-edge"),
    divider: get("--map-divider"), stopline: get("--map-stopline"),
    ego: get("--obj-ego"), vehicle: get("--obj-vehicle"), pedestrian: get("--obj-pedestrian"),
    misc: get("--obj-misc"), gt: get("--obj-gt"), baseline: get("--obj-baseline"), selected: get("--obj-selected"),
    actor: get("--obj-actor"), reacted: get("--obj-reacted"), ghost: get("--obj-ghost"),
    pick: get("--obj-pick"), leader: get("--obj-leader"), danger: get("--danger"),
  };
}

// Dashed ghost outline in variant view: the braking ego in the ego's colour, otherwise grey.
export function ghostColour(colors, track) {
  return track.name === "ego" ? colors.ego : colors.ghost;
}

// Fill colour of an object by role: the event vehicle of a variant, a vehicle reacting to it, the ego,
// then by kind.
export function objectColour(colors, track) {
  if (track.actor) return colors.actor;
  if (track.reacted && track.name !== "ego") return colors.reacted;
  if (track.name === "ego") return colors.ego;
  return { vehicle: colors.vehicle, pedestrian: colors.pedestrian }[track.kind] || colors.misc;
}
