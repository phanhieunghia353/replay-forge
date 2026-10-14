// "Add a data source" dialog: a CSV file (+ optional OpenDRIVE files) or a nuScenes folder.
// The files are read in the browser and sent as text; the server checks them and answers with
// readable errors (shown in the dialog) or the new source entry.

import { addSource } from "./api.js";

export function initSourceDialog({ onAdded }) {
  const dialog = document.getElementById("dialog");
  const form = document.getElementById("source-form");
  const error = document.getElementById("form-error");
  const submit = form.querySelector("button[type=submit]");

  const kind = () => form.elements.kind.value;
  const showKind = () => {
    for (const block of form.querySelectorAll("[data-kind]")) block.hidden = block.dataset.kind !== kind();
  };
  const showError = (text) => { error.textContent = text; error.hidden = !text; };
  const close = () => { dialog.hidden = true; };

  for (const radio of form.elements.kind) radio.addEventListener("change", showKind);
  document.getElementById("cancel-source").addEventListener("click", close);
  dialog.addEventListener("click", (e) => { if (e.target === dialog) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !dialog.hidden) close(); });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");
    const label = form.elements.label.value.trim();
    let spec;
    if (kind() === "csv") {
      const file = form.elements.csv.files[0];
      if (!file) return showError("Chọn file .csv chứa quỹ đạo.");
      const xodr = {};
      for (const road of form.elements.xodr.files) xodr[road.name] = await road.text();
      spec = { kind: "csv", label: label || file.name.replace(/\.csv$/i, ""), csv_text: await file.text(), xodr };
    } else {
      const dataroot = form.elements.dataroot.value.trim();
      if (!dataroot) return showError("Nhập đường dẫn thư mục gốc nuScenes.");
      spec = { kind: "nuscenes", label, dataroot, version: form.elements.version.value.trim() };
    }
    submit.disabled = true;
    submit.textContent = "Đang kiểm tra…";
    try {
      const entry = await addSource(spec);
      close();
      form.reset();
      showKind();
      onAdded(entry);
    } catch (e) {
      showError(e.message);
    } finally {
      submit.disabled = false;
      submit.textContent = "Thêm";
    }
  });

  return {
    open() {
      showError("");
      showKind();
      dialog.hidden = false;
      form.elements.label.focus();
    },
  };
}
