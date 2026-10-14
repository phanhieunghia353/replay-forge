// The "?" marks: one explanation per term, used everywhere the term appears (so the app never explains
// the same thing two ways). Each entry: what it is, how it is measured, where the number comes from.
// The texts follow docs/gia-dinh-va-chi-so.md (sections 5, 7, 8 and 9); change both together.
//
// helpIcon(key) gives the markup; one listener on the document shows the explanation on hover, keyboard
// focus or click (touch screens), and hides it on leave, blur, Escape or a click elsewhere.

export const HELP = {
  // ---------------------------------------------------------------- making a scenario
  pick: ["Xe có thể cho phanh",
    "Xe đang chạy (từ 3 m/s), có một xe khác chạy theo sau nó ít nhất 1 giây, và còn dữ liệu ít nhất 4 giây sau lúc phanh. Chỉ những xe này mới tạo được phản ứng dây chuyền phía sau."],
  ego: ["Xe của bạn",
    "Xe đã ghi lại cảnh này (xe ghi hình của nuScenes). Khi kiểm thử, đây là chỗ phần mềm lái xe tự động của bạn ngồi. Trong mô phỏng, nó được lái bởi người lái mẫu (xem “Phản xạ người lái”)."],
  t0: ["Bắt đầu phanh",
    "Thời điểm (tính từ đầu cảnh) xe phía trước bắt đầu đạp phanh. Ở chế độ đơn giản, kéo thanh thời gian để chọn; tool tự lấy mốc gần nhất mà xe đó đang có xe theo sau."],
  strength: ["Phanh mạnh cỡ nào",
    "Nhẹ = 2 m/s², vừa = 4 m/s², gấp = 6 m/s². Tham khảo: phanh thoải mái của người lái khoảng 3,4 m/s² (AASHTO); phanh gấp hết sức của xe con khoảng 8 m/s². Xe buýt, xe tải tối đa 5 m/s²."],
  decel: ["Mức phanh (m/s²)",
    "Độ giảm tốc mà xe phía trước giữ khi phanh. Lực phanh tăng dần, độ giật tối đa 10 m/s³, như chân người đạp phanh. Giới hạn: xe con 8 m/s², xe buýt và xe tải 5 m/s² (FMVSS 121: xe tải dừng từ 60 mph trong 250 ft, trung bình khoảng 4,7 m/s²)."],
  target: ["Rồi làm gì",
    "Dừng hẳn: phanh tới khi đứng yên rồi đi tiếp ngay. Dừng 3 s: đứng yên 3 giây rồi đi tiếp. Chậm lại: giảm còn một nửa tốc độ rồi tăng lại. Sau đó xe quay về kế hoạch của nó (tăng tốc tối đa 1,5 m/s²)."],
  dwell: ["Thời gian dừng (s)", "Số giây xe phía trước đứng yên trước khi đi tiếp (chỉ khi đích là dừng)."],
  reaction: ["Phản xạ người lái (s)",
    "Thời gian từ lúc người lái thấy xe trước chậm lại (chậm hơn kế hoạch 0,3 m/s, hoặc tụt sau 0,2 m) tới lúc bắt đầu tự xử lý. Mặc định 1,0 s (cùng giá trị với tiêu chí tình huống hiếm). Trong lúc phản xạ, xe vẫn chạy như bản ghi."],
  react: ["Xe phía sau phản ứng",
    "Bật (pilot): các xe phía sau, kể cả xe của bạn, phản ứng như người lái. Tắt (baseline): không ai phản ứng, mọi xe chạy đúng bản ghi; dùng để thấy vì sao cần mô phỏng phản ứng."],
  trigger: ["Kích hoạt theo thời gian",
    "Kịch bản xuất ra là quỹ đạo tính sẵn: mỗi xe đi đúng vị trí đó vào đúng giây đó. Nếu phần mềm lái của bạn chạy khác người lái mẫu (phanh sớm hơn, muộn hơn), các xe khác không phản ứng lại. Khắc phục cần kích hoạt theo khoảng cách, chưa làm."],
  sensitivity: ["Thử độ nhạy",
    "Chạy lại cùng tình huống với phản xạ 0,7 s, 1,0 s và 1,5 s. Nếu kết luận đổi, nó phụ thuộc nhiều vào giả định về người lái."],
  // ---------------------------------------------------------------- result
  valid: ["Hợp lệ",
    "Qua cả 7 điều kiện: esmini chạy được; mọi xe trong giới hạn vật lý; nhãn gốc không lỗi ở đoạn bị đổi; không xe nào đâm nhau (trừ xe của bạn); không bám sát phi lý; không có nhập làn, cắt ngang, người đi bộ ở chỗ va chạm (chưa mô phỏng); không có xe vừa vào khung hình đúng chỗ đó. Chi tiết: tab “Kiểm tra hợp lệ”."],
  group: ["Nhóm",
    "Việc xe của bạn phải làm: suýt chạm hoặc phải phanh gấp (tính là ca hiếm), phanh nhẹ là đủ, hoặc không bị ảnh hưởng."],
  close: ["Suýt chạm",
    "Xe của bạn không chạm, nhưng: hoặc một xe phía trước hay phía sau, trong cùng làn, có lúc cách dưới 1 m; hoặc ở bất kỳ phía nào chỉ còn dưới 1,5 s là chạm (TTC). Phải gần hơn chính cặp xe đó trong bản ghi ít nhất 0,1 m (hoặc 0,1 s). Xe đi song song ở làn bên, dù sát, không tính là suýt chạm nếu hai xe không lao vào nhau. Ngưỡng 1 m và 1,5 s là giả định của đội."],
  hard: ["Phải phanh gấp", "Mức phanh tối thiểu để xe của bạn tránh được, tính sau 1 s phản xạ, lớn hơn 3,4 m/s² (mức phanh thoải mái, AASHTO)."],
  min_gap: ["Gần nhất", "Khoảng cách nhỏ nhất giữa hộp xe của bạn và hộp các xe bị thay đổi, ở bất kỳ phía nào (kể cả xe đi song song ở làn bên), đo mỗi 0,05 s."],
  ttc: ["TTC (thời gian tới va chạm)",
    "Nếu hai xe giữ nguyên vận tốc hiện tại, còn bao nhiêu giây thì hai hộp chạm nhau (xét tối đa 5 s). Càng nhỏ càng nguy hiểm; dưới 1,5 s được tính là suýt chạm."],
  braking: ["Xe bạn cần / đã phanh",
    "Cần: mức phanh nhỏ nhất (lưới 0,2 m/s²) để tránh mọi xe bị thay đổi, nếu bắt đầu phanh sau 1 s phản xạ trên đường đi đã ghi. Đã phanh: mức người lái mẫu thật sự dùng; có thể lớn hơn mức cần."],
  recorded_gap: ["Cùng cặp xe trong bản ghi", "Khoảng cách gần nhất giữa đúng hai xe đó trong cảnh thật, để so: tình huống mới gần hơn bao nhiêu."],
  reacted: ["Xe phản ứng", "Số xe đã chuyển sang tự lái vì xe phía trước chậm lại (kể cả xe của bạn)."],
  // ---------------------------------------------------------------- drivers
  idm: ["IDM",
    "Mô hình người lái bám xe (Treiber và cộng sự 2000), bản cải tiến của Kesting, Treiber, Helbing (2010): chỉ phanh mạnh khi tình huống thật sự cần. Tăng tốc tối đa 1,5 m/s², phanh thoải mái 2,0 m/s²."],
  T_s0: ["T · s₀",
    "T: khoảng thời gian xe này hay giữ với xe trước khi bám ổn định (khoảng cách ÷ tốc độ, trung vị, 0,6–2,5 s). s₀: khoảng cách nhỏ nhất khi cả hai đứng (1–3 m). “Đo” = lấy từ chính bản ghi của xe đó; “mặc định” = 1,2 s và 2,0 m vì bản ghi không có đoạn bám xe."],
  jerk: ["Độ giật", "Tốc độ thay đổi của gia tốc. Phanh tăng tối đa 10 m/s³; khi chạy thường 3 m/s³ (giả định). Đang tăng tốc mà cần phanh thì nhả ga ngay rồi mới phanh."],
  max_decel: ["Phanh tối đa", "Xe con, xe máy, xe đạp 8 m/s²; xe buýt, xe tải, xe công trình, rơ-moóc 5 m/s² (FMVSS 121)."],
  modes: ["Trạng thái theo thời gian",
    "Xám: chạy như bản ghi. Vàng: đã thấy xe trước chậm lại, đang phản xạ. Màu xe: tự lái theo mô hình người lái. Xanh lục: đã quay lại kế hoạch, trễ hơn bản ghi."],
  // ---------------------------------------------------------------- checks
  c_esmini: ["esmini chạy hết", "esmini phát lại file xuất ra, thoát mã 0, và log có đủ mọi vật thể trong thời gian chúng có mặt. Chỉ chạy khi bấm “Tải gói kịch bản”."],
  c_physics: ["Giới hạn vật lý", "Tăng tốc ≤ 4 m/s², phanh ≤ giới hạn của loại xe + 0,2 m/s², tốc độ ≤ 40 m/s; đo từ vị trí x, y (trung bình 0,2 s), nên bắt được cả bước nhảy vị trí."],
  c_label: ["Nhãn gốc lỗi", "Nếu chỗ vi phạm vật lý trùng (trong 5 m dọc đường đi) với chỗ chính nhãn gốc đã phi lý, lỗi là của dữ liệu. Biến thể vẫn bị loại vì kịch bản sẽ chứa chuyển động đó."],
  c_collision: ["Không xe nào đâm nhau", "Hộp hai xe không được chồng nhau, trừ khi một trong hai là xe của bạn. Kiểm mỗi 0,025 s."],
  c_excused: ["Chồng hộp được miễn", "Nhãn có thể vẽ hai hộp chồng nhau dù xe không chạm. Chồng hộp được miễn khi bản ghi có đúng cặp đó ở cùng vị trí tương đối (lệch dọc < 1,5 m, ngang < 0,75 m) và không sâu hơn quá 0,1 m."],
  c_tailgate: ["Bám sát phi lý", "Khoảng cách cản < 0,5 m khi xe sau chạy > 3 m/s, kéo dài quá 0,5 s. Ngoài đời không ai lái như vậy."],
  c_merge: ["Nhập làn, cắt ngang", "Va chạm giữa hai xe lệch hướng quá 30° trong 3 s trước khi chạm, hoặc với người đi bộ: kiểu tương tác này chưa được mô phỏng, nên biến thể bị loại chứ không đoán."],
  c_appear: ["Xe vừa vào khung hình", "Va chạm trong 2 s đầu sau khi một xe mới xuất hiện trong dữ liệu: không biết trước đó nó ở đâu."],
  // ---------------------------------------------------------------- replay and data
  esmini_err: ["Lệch so với quỹ đạo định đưa", "Khoảng cách giữa vị trí esmini ghi trong log và vị trí trong kịch bản, cùng thời điểm (bỏ 0,2 s hai đầu). Gần 0 nghĩa là esmini chạy đúng file."],
  esmini_acc: ["Gia tốc trong esmini", "esmini giữ tốc độ không đổi giữa hai điểm quỹ đạo (0,05 s), nên gia tốc đo thô hơi nhảy bậc; trung bình 0,2 s thì khớp mô phỏng."],
  ade: ["Sai số phát lại (chỉ số 1)",
    "Khoảng cách trung bình giữa vị trí esmini phát lại và vị trí nhãn gốc, tại các mốc nhãn. pilot = quỹ đạo làm mượt, tốc độ theo mốc 2 s; baseline = một tốc độ không đổi."],
  keyframes: ["Mốc nhãn", "Số lần vật thể được gán nhãn (nuScenes: 2 lần mỗi giây)."],
  label_problem: ["Nhãn lỗi", "Đoạn mà chính nhãn gốc cho chuyển động phi lý (vượt giới hạn tăng tốc hoặc phanh của loại xe), ví dụ vị trí nhảy. Tình huống chạm vào đoạn này sẽ bị loại."],
  space: ["Không gian tham số",
    "Kết quả của mọi cách phanh tool đã tự thử khi xử lý cảnh: mức phanh × thời điểm, cho một xe và một đích. Nhìn chỗ màu đổi từ cam sang đỏ là thấy ranh giới tình huống bắt đầu nguy hiểm."],
  provenance: ["Truy vết", "Phiên bản code (commit) và esmini đã tạo số liệu. “Đang sửa” nghĩa là có thay đổi chưa commit."],
  quality: ["Đoạn nhãn lỗi", "Số xe mà nhãn gốc có chuyển động phi lý ở đâu đó. Xem tab “Dữ liệu gốc”."],
  package: ["Gói kịch bản",
    ".xosc: OpenSCENARIO 1.1; .xodr: mạng đường từ bản đồ; trajectories.csv: quỹ đạo mọi vật thể; report.json: tham số, kết quả từng điều kiện, độ khớp esmini, phiên bản. Trước khi đóng gói, esmini chạy lại để kiểm."],
  found: ["Ca hiếm tìm sẵn", "Khi xử lý cảnh, tool tự thử mọi cách phanh trên lưới cố định (mỗi 2 s; 2, 4, 6, 8 m/s²; 3 đích). Đây là các lần phanh nguy hiểm nhất trong số đó."],
};

export function helpIcon(key) {
  return HELP[key] ? `<span class="help" tabindex="0" role="button" aria-label="Giải thích: ${HELP[key][0]}" data-help="${key}">?</span>` : "";
}

// Static markup: <span data-help-for="key"></span> placeholders become "?" marks.
export function initHelp(root = document) {
  for (const el of root.querySelectorAll("[data-help-for]")) {
    el.outerHTML = helpIcon(el.dataset.helpFor);
  }
  const tip = document.createElement("div");
  tip.className = "help-tip";
  tip.hidden = true;
  tip.setAttribute("role", "tooltip");
  document.body.append(tip);
  let pinned = null;
  const show = (el) => {
    const [title, body] = HELP[el.dataset.help] || [];
    if (!title) return;
    tip.innerHTML = `<b>${title}</b>${body}`;
    tip.hidden = false;
    const r = el.getBoundingClientRect(), w = Math.min(340, window.innerWidth - 16);
    tip.style.width = `${w}px`;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    tip.style.left = `${left}px`;
    const below = r.bottom + 8, height = tip.offsetHeight;
    tip.style.top = `${below + height < window.innerHeight ? below : Math.max(8, r.top - height - 8)}px`;
  };
  const hide = () => { if (!pinned) tip.hidden = true; };
  document.addEventListener("mouseover", (e) => { const el = e.target.closest?.(".help"); if (el && !pinned) show(el); });
  document.addEventListener("mouseout", (e) => { if (e.target.closest?.(".help")) hide(); });
  document.addEventListener("focusin", (e) => { if (e.target.classList?.contains("help")) show(e.target); });
  document.addEventListener("focusout", (e) => { if (e.target.classList?.contains("help") && !pinned) tip.hidden = true; });
  document.addEventListener("click", (e) => {
    const el = e.target.closest?.(".help");
    if (el) { e.preventDefault(); e.stopPropagation(); pinned = pinned === el ? null : el; if (pinned) show(el); else tip.hidden = true; return; }
    if (pinned) { pinned = null; tip.hidden = true; }
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { pinned = null; tip.hidden = true; }
    if ((e.key === "Enter" || e.key === " ") && e.target.classList?.contains("help")) { e.preventDefault(); show(e.target); }
  });
}
