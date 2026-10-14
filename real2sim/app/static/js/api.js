// Calls to the local server (real2sim/app/server.py). Every function returns parsed JSON or throws
// an Error carrying the server's message (written for the user, in Vietnamese).

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

const post = (url, body) => request(url, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
const q = encodeURIComponent;

export const getStatus = () => request("/api/status");
export const listSources = () => request("/api/sources");
export const listScenes = (source) => request(`/api/scenes?source=${q(source)}`);
export const loadScene = (source, name) => request(`/api/scene?source=${q(source)}&name=${q(name)}`);
// one variant: {method, case, actor: {name, poses}, ego_brake: {decel, avoids, t_brake, poses} | null}
export const loadVariant = (source, name, method, id) =>
  request(`/api/variant?source=${q(source)}&name=${q(name)}&method=${q(method)}&id=${q(id)}`);
export const listJobs = () => request("/api/jobs");

// {kind: "nuscenes", dataroot, version, label} or {kind: "csv", label, csv_text, xodr: {file: text}}
export const addSource = (spec) => post("/api/sources", spec);
export const removeSource = (id) => post("/api/sources/remove", { id });
// scenes = null: every scene of the source that has not been processed yet
export const processScenes = (source, scenes = null) => post("/api/process", { source, scenes });
// A user-made scenario ({actor, t0, decel, target, dwell, react, reaction}): see Workspace.simulate_event.
export const simulateEvent = (source, name, params) => post("/api/simulate", { source, name, ...params });
// The same, replayed in esmini and packed: {id, report, download}.
export const exportEvent = (source, name, params) => post("/api/export", { source, name, ...params });
export const rareUrl = (source, name) => `/api/download?source=${q(source)}&name=${q(name)}&id=rare`;
