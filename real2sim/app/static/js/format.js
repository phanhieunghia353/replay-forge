// Number and label formatting for the Vietnamese UI (decimal comma, units).

const formatters = new Map();

function formatter(digits) {
  if (!formatters.has(digits)) {
    formatters.set(digits, new Intl.NumberFormat("vi-VN", { minimumFractionDigits: digits, maximumFractionDigits: digits }));
  }
  return formatters.get(digits);
}

export function num(value, digits = 2) {
  return value == null || Number.isNaN(value) ? "–" : formatter(digits).format(value);
}

export function metres(value, digits = 3) {
  return value == null ? "–" : `${num(value, digits)} m`;
}

export function seconds(value, digits = 1) {
  return value == null ? "∞" : `${num(value, digits)} s`;
}

export function percent(part, whole, digits = 1) {
  return whole ? `${num((100 * part) / whole, digits)}%` : "–";
}

// Text from the dataset goes through this before being put into HTML.
export function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
}

export const KIND_LABEL = { vehicle: "Xe", pedestrian: "Người đi bộ", misc: "Vật cản" };

export const METHOD_LABEL = { exact: "Chép từng điểm", baseline: "Baseline", pilot: "Pilot" };

// What the ego goes through in a stage-1 variant (docs/thiet-ke-kich-ban-hanh-vi.md, 4.8), in display order.
export const GROUPS = [
  { key: "close", label: "Suýt chạm", valuable: true,
    explain: "Xe của bạn không chạm, nhưng có lúc cách xe khác dưới 1 m hoặc chỉ còn dưới 1,5 s là chạm." },
  { key: "hard", label: "Phải phanh gấp", valuable: true,
    explain: "Xe của bạn phải phanh mạnh hơn 3,4 m/s² mới tránh được." },
  { key: "mild", label: "Phanh nhẹ là đủ", valuable: false,
    explain: "Xe của bạn phải phanh, nhưng phanh nhẹ (tối đa 3,4 m/s²) là đủ. Không tính là hiếm." },
  { key: "far", label: "Không ảnh hưởng tới xe của bạn", valuable: false,
    explain: "Tình huống xảy ra, các xe khác phản ứng, nhưng xe của bạn không phải làm gì." },
  { key: "collision", label: "Xe của bạn đâm (vì không phản ứng)", valuable: false,
    explain: "Chỉ có ở baseline: không ai phản ứng, kể cả xe của bạn, nên nó đâm. Cho thấy vì sao cần mô phỏng phản ứng." },
];

// Why a variant was rejected (summary line under the list).
export const REASON_LABEL = {
  collision: "các xe khác đâm nhau",
  label_error: "nhãn gốc của dữ liệu bị lỗi",
  physics: "sai vật lý",
  tailgating: "bám sát phi lý",
  unsupported_interaction: "có xe nhập làn, cắt ngang hoặc người đi bộ (chưa mô phỏng)",
  unsupported_appearing: "có xe vừa đi vào khung hình đúng chỗ tình huống (chưa mô phỏng)",
  esmini: "esmini báo lỗi",
};

// "phanh 6 m/s² tới dừng, đứng 3 s, lúc 7 s": what the event vehicle does.
export function eventParams(c) {
  const target = c.target === "stop" ? `tới dừng${c.dwell ? `, đứng ${num(c.dwell, 0)} s` : ""}` : "xuống nửa tốc độ";
  return `phanh ${num(c.decel, 0)} m/s² ${target}, lúc ${num(c.t0, 0)} s`;
}
