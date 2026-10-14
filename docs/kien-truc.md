# Kiến trúc real2sim — đọc trước khi sửa code

Tài liệu này giúp người mới (hoặc người nhờ AI viết code) biết **chỗ nào làm gì** và **sửa ở đâu**. Định nghĩa chỉ số và các giả định nằm ở [gia-dinh-va-chi-so.md](gia-dinh-va-chi-so.md).

## 1. Toàn cảnh

```text
 nuScenes (JSON nhãn + bản đồ)        file CSV quỹ đạo (+ .xodr)       ← dữ liệu của người dùng
        │  nuscenes_io.py, nuscenes_map.py     │  (định dạng: dinh-dang-csv.md)
        └───────────────┬────────────────────────┘
                        │  sources.py: NuScenesSource / CsvSource — cùng một giao diện "nguồn"
                        ▼
 Quỹ đạo gốc (Scene, Track)                       tracks.py
        │  abstraction.py                         dựng lại: exact / baseline / pilot
        ▼
 Kịch bản OpenSCENARIO (.xosc) + đường (.xodr)    xosc.py, xodr.py
        │  esmini.py                              chạy esmini, đọc log CSV
        ▼
 Log mô phỏng ──► metrics.py   CHỈ SỐ 1: sai số phát lại
        │
        │  behavior.py + events.py                xe trước phanh, xe sau phản ứng như người
        │                                         → kiểm hợp lệ, độ hiếm (variants.py: cách cũ)
        ▼
 Biến thể ──► CHỈ SỐ 2: số kịch bản hợp lệ, số tình huống hiếm
        │
        ├─► report.py        bảng tổng nhiều scene (out/<nguồn>/summary.md)
        └─► app/             ứng dụng xem trong trình duyệt
```

Các bước xử lý (chỉ số 1, chỉ số 2) nằm trong `pipeline.py`. Có **hai cách dùng**, cùng gọi `pipeline.py`:

- **Dòng lệnh** (`python -m real2sim ...`, file `__main__.py`): chạy hàng loạt.
- **Ứng dụng** (`real2sim.bat` → `python -m real2sim app`):
  - thêm nguồn dữ liệu, bấm "Xử lý" (chạy nền qua `app/jobs.py`), xem kết quả;
  - gọi lại đúng các hàm của lõi, **không** có bản tính riêng.

**Kết quả** của cảnh S thuộc nguồn X luôn nằm ở `out/X/S/`, ví dụ `out/nuscenes-mini/scene-0061/`. Danh sách nguồn của app nằm ở `data/sources.json`. File CSV nhập qua app được chép vào `data/imported/<mã nguồn>/`.

## 2. Từng file làm gì

| File | Việc | Sửa khi muốn… |
|---|---|---|
| `real2sim/nuscenes_io.py` | Đọc các bảng JSON của nuScenes (scene, sample, annotation, ego_pose, log…) | đọc thêm bảng/trường mới của nuScenes |
| `real2sim/nuscenes_map.py` | Đọc map expansion: đường tâm làn (arcline), đa giác, đường kẻ | dùng thêm lớp bản đồ |
| `real2sim/sources.py` | "Nguồn dữ liệu": `NuScenesSource`, `CsvSource`; đọc và kiểm file CSV (báo lỗi theo dòng); xuất CSV | thêm loại dữ liệu mới, đổi định dạng CSV |
| `real2sim/pipeline.py` | Các bước xử lý dùng chung cho dòng lệnh và app: `replay_scene` (chỉ số 1), `events_scene` (chỉ số 2), `process_scene` (cả hai, nút "Xử lý" của app), `variants_scene` (cách sinh biến thể cũ, chỉ để so sánh); có báo tiến độ | đổi trình tự xử lý, nơi ghi kết quả |
| `real2sim/tracks.py` | `Track`, `Scene`; trích quỹ đạo từ nhãn nuScenes; các hằng số kích thước, ngưỡng đứng yên | đổi cách gom nhãn thành quỹ đạo |
| `real2sim/abstraction.py` | Ba cách dựng lại quỹ đạo: `exact`, `baseline`, `pilot` | cải tiến cách tóm gọn (chỉ số 1) |
| `real2sim/xosc.py` | Viết file OpenSCENARIO 1.1 | đổi cấu trúc kịch bản |
| `real2sim/xodr.py` | Viết file OpenDRIVE (đường thật từ bản đồ, hoặc mặt phẳng) | đổi cách dựng đường |
| `real2sim/esmini.py` | Gọi esmini, đọc log CSV | đổi tham số chạy esmini |
| `real2sim/metrics.py` | Sai số phát lại (ADE, FDE, …) | thêm/đổi đại lượng chỉ số 1 |
| `real2sim/safety.py` | Hình hộp, va chạm, khoảng cách, TTC (thường và theo đường đi), gia tốc, mô phỏng xe ghi hình phanh trên đường đi đã ghi | thêm thước đo nguy hiểm |
| `real2sim/behavior.py` | Mô phỏng hành vi (giai đoạn 1): chuyển động gốc của mọi vật thể, tìm xe phía trước theo hình hộp, sự kiện phanh, người lái phản ứng (IDM cải tiến, phản xạ 1 s, giới hạn phanh theo loại xe) | đổi cách người lái phản ứng |
| `real2sim/events.py` | Lưới sự kiện (chốt trước), kiểm hợp lệ chung cho baseline và pilot (vật lý, nhãn gốc lỗi, va chạm, nhập làn, bám sát), nhóm theo việc xe ghi hình phải làm, tóm tắt | đổi điều kiện hợp lệ, ngưỡng (chỉ số 2) |
| `real2sim/variants.py` | Cách sinh biến thể cũ: dời thời gian, đổi tốc độ cả quỹ đạo, không ai phản ứng. Chỉ giữ để so sánh | – |
| `real2sim/report.py` | Gộp kết quả nhiều scene | đổi bảng tổng |
| `real2sim/__main__.py` | Các lệnh dòng lệnh: `scenes`, `replay`, `events`, `variants` (cũ), `report`, `export-csv`, `app`; chọn nguồn bằng `--csv` hoặc `--dataroot/--version` | thêm lệnh, thêm tuỳ chọn |
| `real2sim/app/api.py` | Lớp `Workspace`: danh sách nguồn, dữ liệu JSON cho giao diện, gửi việc xử lý, mô phỏng một tình huống người dùng tạo (`simulate_event`), xuất gói kịch bản (`export_event`, gọi `pipeline.export_event`) | giao diện cần thêm dữ liệu |
| `real2sim/app/registry.py` | Danh sách nguồn dữ liệu (`data/sources.json`), thêm hoặc gỡ nguồn, chép file CSV nhập vào `data/imported/` | đổi cách lưu nguồn |
| `real2sim/app/jobs.py` | Hàng đợi xử lý chạy nền (một luồng, lần lượt từng cảnh), có tiến độ và lỗi | đổi cách chạy nền |
| `real2sim/app/server.py` | Máy chủ web nhỏ (thư viện chuẩn), các đường dẫn `/api/...` (danh sách đầy đủ ở đầu file) | thêm đường dẫn API |
| `real2sim/app/static/js/sources-dialog.js` | Hộp thoại "Thêm nguồn dữ liệu" (CSV hoặc thư mục nuScenes) | đổi cách thêm dữ liệu |
| `real2sim/app/static/examples/tracks-vi-du.csv` | File CSV mẫu (cảnh tự dựng, không lấy từ nuScenes) | cập nhật khi đổi định dạng CSV |
| `real2sim/app/static/index.html` | Khung trang | thêm khối giao diện |
| `real2sim/app/static/style.css` | Toàn bộ màu và bố cục (màu là biến `--...` ở đầu file) | đổi màu, bố cục |
| `real2sim/app/static/js/main.js` | Nối các phần (docs/thiet-ke-giao-dien.md): chọn cảnh, hai chế độ, chọn xe và tham số, gọi `/api/simulate` và `/api/export`, kết luận bằng lời, lớp phủ và mốc thời gian, hộp "Dữ liệu…" | thêm tương tác |
| `real2sim/app/static/js/dock.js` | Ngăn dưới của chế độ kỹ thuật: biểu đồ, không gian tham số, các xe, kiểm tra hợp lệ, độ khớp esmini, dữ liệu gốc, xuất và truy vết | thêm thông tin kỹ thuật |
| `real2sim/app/static/js/help.js` | Dấu "?" và bảng giải thích thuật ngữ (một lời giải thích cho mỗi thuật ngữ, theo `docs/gia-dinh-va-chi-so.md`): hiện khi di chuột, bấm, hoặc Tab tới | đổi lời giải thích (đổi cả tài liệu) |
| `real2sim/app/static/js/charts.js` | Biểu đồ đường trên canvas (không thư viện): nhiều chuỗi, nét đứt, ngưỡng, thời điểm đang xem | đổi cách vẽ biểu đồ |
| `real2sim/app/static/js/viewer.js` | Khung **từ trên xuống** (canvas 2D): vẽ bản đồ và vật thể, kéo/phóng to/bấm chọn | đổi cách vẽ 2D |
| `real2sim/app/static/js/viewer3d.js` | Khung **góc tự do 3D** (three.js): mặt đường, khối hộp vật thể, xoay/di chuyển/phóng to, bấm chọn | đổi cách vẽ 3D |
| `real2sim/app/static/js/deviation.js` | Độ lệch của pilot/baseline so với xe thật tại một thời điểm (tổng, trước–sau, trái–phải) và biểu đồ độ lệch theo thời gian ở bảng chi tiết | đổi cách đo hoặc hiển thị độ lệch |
| `real2sim/app/static/js/geometry.js` | Hàm hình học dùng chung cho cả hai khung: vị trí theo thời gian, góc hộp | đổi cách nội suy, hình hộp |
| `real2sim/app/static/js/colors.js` | Đọc màu từ `style.css` cho cả hai khung | thêm màu mới |
| `real2sim/app/static/vendor/` | three.js 0.170.0 (giấy phép MIT, file `three-LICENSE.txt`), sao chép nguyên bản từ jsDelivr để chạy không cần internet | **không sửa tay**; muốn nâng phiên bản thì thay cả ba file cùng lúc |
| `real2sim/app/static/js/timeline.js` | Thanh thời gian, phát/tạm dừng | đổi cách phát |
| `real2sim/app/static/js/api.js` | Hàm gọi máy chủ | thêm lời gọi API |
| `real2sim/app/static/js/format.js` | Định dạng số kiểu Việt Nam, nhãn tiếng Việt | đổi cách hiển thị số |
| `tests/` | Test tự động (pytest), chạy không cần nuScenes hay esmini | luôn thêm test khi sửa lõi |

## 3. Quy ước bắt buộc

- **Hệ toạ độ:** mét, x hướng đông, y hướng bắc. Gốc là vị trí xe ghi hình ở khung đầu, thời gian 0 là khung đầu. Mọi dữ liệu gửi sang giao diện đều ở hệ này.
- **Điểm vị trí:** với vật thể là tâm hộp nhãn; với xe ghi hình là tâm cầu sau (tâm hộp lệch lên trước `bbox_center_x`).
- **Không có số liệu thì không bịa:** giao diện ghi "chưa chạy" khi thiếu kết quả trong `out/`.
- **App vẽ quỹ đạo dựng lại, không vẽ log esmini.** Cái được vẽ chính là đầu vào của esmini (với biến thể: quỹ đạo `behavior.simulate` tính lại cho các xe bị thay đổi, đúng như khi ghi báo cáo). Ở chế độ `position`, log esmini khớp đầu vào tới khoảng 0,001 m (sai số `exact`), nên hai thứ trùng nhau khi nhìn bằng mắt.
- **Lõi không biết giao diện tồn tại:** không import gì từ `app/` trong các file lõi.
- **Mã nguồn dùng tên tiếng Anh, tài liệu và chữ trên giao diện bằng tiếng Việt.**

## 4. Những điểm đặc biệt của esmini (đừng phá)

Chi tiết và số đo ở mục 2 của [gia-dinh-va-chi-so.md](gia-dinh-va-chi-so.md).

1. **Cầu sau phải đặt tại điểm vị trí** (`RearAxle positionX = 0`, trong `xosc.py`). Nếu không, esmini tự dời hộp xe.
2. **Thời gian các điểm phải là tuyệt đối** (`domainAbsoluteRelative="absolute"`). esmini khởi động hành động trễ một bước, nên tính theo thời gian tương đối thì mọi quỹ đạo bị trễ theo.
3. **Luôn chạy với `--traj_filter 0`** (trong `esmini.py`). Nếu không, esmini gộp các điểm gần nhau và xe chạy chậm bị giật.
4. **Bộ lái `followReference`:** esmini chỉ tạo xe dẫn đường cho xe đầu tiên. Nếu dùng bộ lái này, phải tự tạo xe dẫn đường riêng cho từng xe.

Có test giữ các điểm 1–2 (`tests/test_xosc.py`). Kiểm tra nhanh sau mọi thay đổi ở `xosc.py` hoặc `esmini.py`: cách `exact` phải cho sai số ~0 trên mọi scene:

```powershell
.venv\Scripts\python.exe -m real2sim replay --scene scene-1077 --method exact
```

## 5. Công thức cho việc hay gặp

### Thêm một loại dữ liệu đầu vào (ví dụ một bộ dữ liệu khác)
1. `sources.py`: viết lớp kế thừa `Source`, cài đặt `scene_names()` và `scene(name)`. Hàm `scene` trả về `Scene` với các `Track` theo quy ước ở mục 3. Các hàm bản đồ là tuỳ chọn.
2. `sources.py`: thêm nhánh cho `kind` mới trong `load_source()`.
3. `app/registry.py` và `sources-dialog.js`: thêm cách khai báo nguồn mới trong app.
4. `tests/test_sources.py`: thêm test với dữ liệu nhỏ tự tạo.

Không cần sửa `pipeline.py` hay phần giao diện xem: mọi thứ sau `Source` dùng chung.

### Thêm một kiểu biến thể (ví dụ "dời ngang trong làn")
Kiểu "dời thời gian" (họ B) đã làm theo đúng công thức này; xem `retime(..., shift)`.
1. `variants.py`: thêm tham số vào `retime()` hoặc viết hàm mới trả về `Track` đã biến đổi (hoặc `None` nếu không đủ dữ liệu). Không bịa chuyển động ra ngoài dữ liệu thật.
2. `variants.py`: thêm giá trị vào lưới (`grid(track)`, có thể khác nhau theo loại diễn viên), và vào `variant_id()` để tên biến thể phân biệt được. Hàm `job` trong `pipeline.variants_scene` nhận thêm tham số tương ứng.
3. `tests/test_variants.py`: thêm test cho hàm mới, gồm cả trường hợp trả về `None`.
4. Cập nhật mục 8.1 và 10.3 trong `gia-dinh-va-chi-so.md`.
5. Kiểm biến thể mới **không làm vật thể hiện ra hay biến mất giữa đường** (luật `pop_in` / `pop_out`), và xem thử bằng ảnh động: `tools\reviews\render_variant.py` (nằm ngoài git, trong `tools\`).

### Thêm một điều kiện hợp lệ hoặc thước đo nguy hiểm
1. Thước đo hình học: viết trong `safety.py`, có test.
2. Điều kiện: thêm vào `assess()` trong `variants.py`. Đặt ngưỡng thành hằng số ở đầu file, rồi thêm vào `thresholds()`.
3. Ghi vào mục 8.2/8.3 và bảng giả định (mục 9) của `gia-dinh-va-chi-so.md`.

### Hiển thị thêm một lớp bản đồ
1. `app/api.py`: thêm tên lớp vào `POLYGON_LAYERS` hoặc `LINE_LAYERS`.
2. `app/static/js/viewer.js`: thêm vào `_drawMap()` (khung từ trên xuống).
3. `app/static/js/viewer3d.js`: thêm vào `MAP_LEVELS` hoặc `_buildMap()` (khung 3D).
4. `app/static/style.css`: thêm biến màu `--map-...`, rồi đọc nó trong `readColors()` của `colors.js`.

### Thêm một chức năng cho khung xem
`Viewer` (2D) và `Viewer3D` có **cùng các hàm**: `setScene`, `setTime`, `setLayer`, `setFollow`, `setSelected`, `select`, `fit`. `main.js` gọi hàm cho cả hai khung qua `eachView`. Thêm chức năng mới thì thêm vào **cả hai lớp** với cùng tên hàm.

### Thêm một chức năng giao diện cần dữ liệu mới
1. `app/api.py`: thêm hàm hoặc phương thức trả về dict.
2. `app/server.py`: thêm đường dẫn trong `do_GET` (hoặc `do_POST`).
3. `app/static/js/api.js`: thêm hàm gọi.
4. `app/static/js/main.js`: dùng dữ liệu và vẽ ra trang.
5. `tests/test_app.py`: thêm test cho đường dẫn mới.

## 6. Hiệu năng của khung xem

**Mục tiêu:** mỗi lần vẽ dưới 16 ms (60 hình/giây), để kéo, xoay và phát không bị giật.

**Bài học đã gặp:** bản đầu của khung từ trên xuống mất 68 ms mỗi lần vẽ. Nguyên nhân là mỗi khung hình nó đổi toạ độ lại cho 16.545 điểm bản đồ, và với mỗi điểm lại hỏi kích thước khung vẽ (`getBoundingClientRect`, buộc trình duyệt tính lại bố cục). Sau khi sửa còn 0,4–1 ms.

**Quy tắc:**
- Hình tĩnh (bản đồ) được dựng **một lần** khi mở cảnh: `Path2D` ở bản 2D, `BufferGeometry` ở bản 3D. Mỗi khung hình chỉ đặt phép biến đổi camera rồi vẽ lại các hình đó.
- Không gọi `getBoundingClientRect` hay đọc kích thước bố cục bên trong vòng lặp theo điểm. Đo **một lần** mỗi lần vẽ.
- Sự kiện chuột dồn dập (kéo, cuộn) gọi `requestDraw()`, để gộp lại thành **tối đa một lần vẽ** mỗi khung hình màn hình.

**Cách đo:** mở console (F12) trên trang ứng dụng và chạy:

```js
const v = real2sim.views.top, t = [];
for (let i = 0; i < 30; i++) { const s = performance.now(); v.draw(); t.push(performance.now() - s); }
t.sort((a, b) => a - b); t[15]  // trung vị, tính bằng ms
```

## 7. Kiểm tra trước khi coi là xong

```powershell
cd C:\Codes\real2sim
.venv\Scripts\python.exe -m pytest -q
```

- **Test phải qua hết.** Test không cần nuScenes hay esmini, dùng một cảnh giả trong `tests/conftest.py`.
- **Sửa giao diện:** chạy `real2sim.bat`, mở trang, nhấn F12 xem tab Console không có lỗi đỏ.
- **Sửa lõi:** chạy lại ít nhất một scene thật bằng `replay` và `variants`, rồi so số với bảng trong `out/nuscenes-mini/summary.md`.
- **Sửa phần nhập CSV:** thêm `tracks-vi-du.csv` qua app, bấm "Xử lý", và kiểm cảnh `vi-du` ra số hợp lý.
