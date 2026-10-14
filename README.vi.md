# replay-forge: xuất cảnh thật thành kịch bản mô phỏng (đề N3-09B)

[English](README.md) · Tiếng Việt. Gói Python bên trong vẫn tên là `real2sim` (`python -m real2sim ...`).

Chuyển quỹ đạo các vật thể đã gán nhãn (từ nuScenes, hoặc từ dữ liệu của bạn ở dạng CSV) thành kịch bản OpenSCENARIO (`.xosc`) kèm mạng đường OpenDRIVE (`.xodr`). Sau đó:
- phát lại bằng esmini và đo **sai số phát lại** (chỉ số 1);
- sinh biến thể đổi tốc độ và khoảng cách (một xe phía trước phanh hoặc giảm tốc; các xe phía sau, kể cả xe ghi hình, phản ứng như người lái), rồi đếm **số kịch bản hợp lệ** và tình huống hiếm (chỉ số 2).

Mọi kịch bản đều do chương trình tự sinh từ dữ liệu đầu vào, theo luật cố định trong code, và tự kiểm tra hợp lệ. Không có bước nào cần người chỉnh tay từng kịch bản. Tình huống nào chương trình chưa mô phỏng được (xe nhập làn, cắt ngang, người đi bộ, nhãn gốc lỗi) thì biến thể đó bị loại và ghi rõ lý do, không xuất ra kịch bản sai.

**Tài liệu:**
- [Giả định và định nghĩa chỉ số](docs/gia-dinh-va-chi-so.md)
- [Định dạng CSV để đưa dữ liệu của bạn vào](docs/dinh-dang-csv.md)
- Muốn sửa code: [docs/kien-truc.md](docs/kien-truc.md)

## Mở ứng dụng

Bấm đúp `real2sim.bat`. Trình duyệt mở `http://127.0.0.1:8765`. Ứng dụng chạy hoàn toàn trên máy, không cần internet. Đóng cửa sổ dòng lệnh để tắt. Thiết kế giao diện: [docs/thiet-ke-giao-dien.md](docs/thiet-ke-giao-dien.md).

Có hai chế độ, chuyển bằng nút ở góc trên phải:

**Đơn giản** (mặc định): ba bước ghi trên thanh trên cùng.
1. **Chọn xe:** chọn cảnh ở thanh trên. Những xe có **viền hồng** là xe đang có xe khác chạy phía sau; bấm vào một xe đó (hoặc tên nó ở cột phải).
2. **Chỉnh cách phanh:** kéo thanh thời gian để chọn lúc phanh; chọn mạnh cỡ nào (nhẹ / vừa / gấp) và rồi làm gì (dừng hẳn / dừng 3 s / chậm lại). Bấm **"Tạo tình huống"**: chưa tới 1 giây đã thấy các xe phía sau, kể cả xe của bạn, phản ứng.
3. **Xem và tải:** kết luận là một câu (dùng được hay không, vì sao, gợi ý nếu không dùng được). **Phát lại** để xem; **Tải gói kịch bản** cho esmini chạy lại để kiểm tra rồi tải về `.zip` gồm `.xosc`, `.xodr`, `trajectories.csv`, `report.json`.

Tab **"Ca hiếm tìm sẵn"**: các lần phanh nguy hiểm nhất mà tool đã tự thử khi xử lý cảnh, mỗi dòng có nút "Xem"; tải cả bộ ca hiếm của cảnh.

**Kỹ thuật**: như trên, thêm:
- tham số bằng số (thời điểm, mức phanh kèm giới hạn của xe, đích, thời gian dừng, phản xạ người lái, bật/tắt phản ứng), nút **"Thử độ nhạy"** (phản xạ 0,7 / 1,0 / 1,5 s);
- lớp phủ trên khung xem: vị trí trong bản ghi, mũi tên "ai đang theo ai", khoảng cách và TTC, mã xe, dải đường đi, vạch dừng, đo khoảng cách;
- mốc sự kiện trên thanh thời gian (phanh, phản ứng, lúc gần nhất, va chạm; vùng vàng là chỗ nhãn gốc lỗi), bước ±0,05 s;
- ngăn dưới 7 tab: **Biểu đồ** (tốc độ, gia tốc, khoảng cách, TTC, có ngưỡng và bản ghi gốc), **Không gian tham số** (lưới mức phanh × thời điểm, bấm ô để mở), **Các xe** (trạng thái theo thời gian, xe phía trước, tham số người lái đo hay mặc định), **Kiểm tra hợp lệ** (từng điều kiện, ngưỡng, số đo, lúc xảy ra), **Độ khớp esmini**, **Dữ liệu gốc** (từng vật thể, sai số phát lại, nhãn lỗi), **Xuất và truy vết** (file, lệnh esmini, phiên bản code và dữ liệu, bộ ngưỡng).

Dấu **?** cạnh mỗi thông số: di chuột, bấm, hoặc Tab tới để xem nó là gì, đo thế nào, lấy từ đâu.

Phím tắt: cách = phát / dừng; ← → = lùi / tiến 0,05 s (giữ Shift: 1 s).

**Dữ liệu…** (thanh trên): thêm nguồn (**file CSV** theo [mẫu](docs/dinh-dang-csv.md), kèm `.xodr` nếu có; hoặc **thư mục nuScenes** bất kỳ), gỡ nguồn (không xoá dữ liệu), và **xử lý** cảnh: đo sai số phát lại (chỉ số 1) và để tool tự thử mọi cách phanh trên lưới (chỉ số 2). Tạo tình huống của riêng bạn thì không cần xử lý trước.

## Cài đặt

Venv dùng chung numpy/scipy/pytest đã cài sẵn ở Python hệ thống (`--system-site-packages`), vì tải từ PyPI trên máy này hay bị đứt:

```powershell
python -m venv --system-site-packages C:\Codes\real2sim\.venv
```

Nếu Python hệ thống chưa có các gói này: `C:\Codes\real2sim\.venv\Scripts\python.exe -m pip install numpy scipy pytest`.

**esmini** (giấy phép MPL-2.0): tải `esmini-demo_Windows.zip` của bản v3.9.0 ở https://github.com/esmini/esmini/releases (130 809 894 byte; bản demo có sẵn mẫu 3D xe và người), rồi giải nén vào `C:\Codes\real2sim\tools\`. Chương trình tự tìm `tools\esmini-demo\bin\esmini.exe`. Thiếu esmini thì app báo rõ và vẫn xem được dữ liệu, chỉ không xử lý được.

**Dữ liệu nuScenes** (đặt dưới `C:\Codes\real2sim\data\nuscenes\`; app tự nhận bản mini ở đây):

- `v1.0-mini\*.json`: các bảng của nuScenes mini. Chúng nằm trong khoảng 20 MB đầu của file công khai https://www.nuscenes.org/data/v1.0-mini.tgz (4,17 GB), nên không cần tải cả file:
  `curl.exe -r 0-20000000 -o head.tgz https://www.nuscenes.org/data/v1.0-mini.tgz` rồi `tar.exe -xzf head.tgz -C data\nuscenes v1.0-mini` (tar sẽ báo "Truncated" cho phần ảnh phía sau, bỏ qua được).
- `maps\expansion\*.json`: nuScenes map expansion v1.3 (cần tài khoản nuScenes để tải). Chỉ cần thư mục `expansion\` trong zip. Thiếu bản đồ thì kịch bản không có mạng đường (chương trình báo rõ).

## Dòng lệnh

Nguồn mặc định là nuScenes mini trong `data\nuscenes`. Đổi nguồn bằng `--dataroot DIR --version V`, hoặc `--csv THƯ_MỤC_HOẶC_FILE`. Kết quả nằm ở `out\<mã nguồn>\<cảnh>\`, ví dụ `out\nuscenes-mini\scene-0061\`.

```powershell
cd C:\Codes\real2sim
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m real2sim scenes
.venv\Scripts\python.exe -m real2sim replay --scene scene-0061
.venv\Scripts\python.exe -m real2sim events --scene scene-0061
.venv\Scripts\python.exe -m real2sim report
.venv\Scripts\python.exe -m real2sim --csv duong\den\thu-muc replay --scene ten-canh
.venv\Scripts\python.exe -m real2sim export-csv --scene scene-0061 --to scene-0061.csv
```

- **`replay`** (chỉ số 1): chạy cả ba cách dựng (`exact`, `baseline`, `pilot`) và in bảng so sánh ADE. Kết quả gồm `tracks_gt.json`, và với mỗi cách: `<cảnh>.xosc`, `.xodr`, `esmini_log.csv`, `metrics.json`. Mã thoát: 0 là chạy xong, 1 là esmini lỗi, 2 là không tìm thấy esmini (vẫn ghi `.xosc`).
- **`events`** (chỉ số 2, cũng là việc nút "Xử lý" trong app làm sau chỉ số 1): một xe phía trước phanh (2, 4, 6 hoặc 8 m/s²; xe buýt và xe tải tối đa 5 m/s²) tới dừng, dừng 3 s, hoặc xuống nửa tốc độ. `baseline`: không ai phản ứng; `pilot`: các xe phía sau, kể cả xe ghi hình, phản ứng như người lái (chậm 1 s). Thường dưới 3 phút một cảnh. Kết quả ở `events\<method>\`:
  - `report.json`: mọi biến thể, kèm lý do bị loại, mức phanh từng xe đã dùng, việc xe ghi hình phải làm, và khối `run` (commit, phiên bản esmini, cấu hình);
  - `xosc\`: các biến thể hiếm, ở dạng đầy đủ kèm `.xodr`.
- **`variants`**: cách sinh biến thể cũ (dời thời gian và đổi tốc độ cả quỹ đạo, không ai phản ứng). Chỉ giữ để so sánh; app không dùng nữa. Lý do bỏ: [docs/thiet-ke-kich-ban-hanh-vi.md](docs/thiet-ke-kich-ban-hanh-vi.md).
- Mỗi lượt chạy ghi vào thư mục tạm `<…>.new` và chỉ thay kết quả cũ khi chạy xong. Lượt chạy lỗi thì kết quả cũ được giữ, và log lỗi nằm trong thư mục `.new`.
- **`holdout`** (kiểm chéo chỉ số 1): giấu một nửa mốc nhãn, dựng lại, đo trên mốc bị giấu; kèm độ êm (gia tốc lớn nhất) của từng cách. Ghi `holdout.json` cho mỗi cảnh. Vài giây, không cần esmini.
- **`events --reaction 0.7 --out out/sensitivity/r0.7`**: lượt độ nhạy với thời gian phản xạ khác.
- **`report`**: gộp mọi cảnh đã chạy của nguồn thành `summary.md` và `summary.json`: chỉ số 1, kiểm chéo, chỉ số 2, độ nhạy (đọc `out/sensitivity/r*/`), phụ lục cách cũ; cảnh báo nếu các kết quả đến từ nhiều lượt chạy khác nhau.
- **`export-csv`**: ghi cảnh ra định dạng CSV của real2sim.

Xem kịch bản trong cửa sổ esmini (thêm `--camera_mode top` để nhìn từ trên xuống):

```powershell
tools\esmini-demo\bin\esmini.exe --window 60 60 1280 720 --ground_plane on --traj_filter 0 --osc out\nuscenes-mini\scene-0061\pilot\scene-0061.xosc
```

## Trạng thái

| Phần | Trạng thái |
|---|---|
| Dựng lại quỹ đạo: `exact` / `baseline` (một tốc độ) / `pilot` (làm mượt, tốc độ theo mốc 2 s nối PCHIP, ghim vật đứng yên) | xong, có test |
| Viết `.xosc` (OpenSCENARIO 1.1) và `.xodr` (đường từ map expansion, hoặc file `.xodr` của nguồn CSV) | xong, có test; 10/10 cảnh nạp trong esmini không cảnh báo |
| Chỉ số 1: phát lại bằng esmini, tính sai số | 10 cảnh: ADE nhóm chuyển động baseline 1,771 m → pilot 0,098 m (exact 0,000 m). Kiểm chéo trên mốc nhãn bị giấu: baseline 1,983 → pilot 0,133 m; nối thẳng 0,091 m nhưng 81% vật thể giật quá 4 m/s² (pilot 16%). [Mục 7, 7.1](docs/gia-dinh-va-chi-so.md) |
| Chỉ số 2 (giai đoạn 1): xe phía trước phanh hoặc giảm tốc, các xe phía sau phản ứng như người lái; một bộ kiểm hợp lệ chung cho baseline và pilot | 10 cảnh (14/10/2026): hợp lệ baseline (không ai phản ứng) 225/777 (29,0%) → pilot (có phản ứng) 591/777 (76,1%); pilot có 18 biến thể "suýt chạm" trong 6 lần phanh (baseline 4). Độ nhạy theo phản xạ 0,7 / 1 / 1,5 s: pilot 78,1 / 76,1 / 63,4% hợp lệ (vững), ca hiếm 0 / 18 / 41 (không vững). [Mục 8](docs/gia-dinh-va-chi-so.md) |
| Chỉ số 2, cách cũ (dời thời gian, đổi tốc độ cả quỹ đạo, không ai phản ứng) | giữ để so sánh: 10 cảnh (13/10/2026) hợp lệ 46,4% → 57,9%, nhưng biến thể trông giả, nên đã thay. [Mục 8.4](docs/gia-dinh-va-chi-so.md) |
| Nguồn dữ liệu: nuScenes (mọi phiên bản), file CSV (+ `.xodr`) | xong, có test; CSV xuất từ scene-0061 cho cùng kết quả với nuScenes |
| Ứng dụng: thêm nguồn, xử lý chạy nền có tiến độ, xem 2D/3D, chỉ số, chi tiết vật thể | xong, có test cho máy chủ |
| App cho người dùng (chế độ đơn giản và kỹ thuật): tự tạo tình huống, kết luận bằng lời thường, kiểm lại bằng esmini và tải gói kịch bản; biểu đồ, không gian tham số, kiểm tra hợp lệ chi tiết, truy vết | xong (14/10/2026), có test cho máy chủ; đã thử trên trình duyệt |
| Tạo biến thể bằng tay trong app, xuất bộ kịch bản | chưa làm |

## Hệ toạ độ và quy ước

- **nuScenes:** trục x hướng đông, y hướng bắc, đơn vị mét. Gốc là vị trí xe ghi hình ở khung đầu; thời gian 0 là khung đầu. Điểm vị trí của xe ghi hình là tâm cầu sau (tâm hộp lệch lên trước 1,39 m); của vật thể khác là tâm hộp.
- **CSV:** giữ nguyên toạ độ của file; mọi vị trí là tâm hộp (xem [định dạng CSV](docs/dinh-dang-csv.md)).
- **esmini và cầu sau:** esmini coi điểm vị trí là tâm cầu sau và tự dời hộp xe nếu cầu sau lệch, nên kịch bản luôn đặt cầu sau đúng điểm vị trí.
- **Thời gian có mặt:** mỗi vật thể chỉ có mặt trong kịch bản khi có dữ liệu. Nó xuất hiện 0,1 s trước mốc đầu (`AddEntityAction`) và biến mất 0,1 s sau mốc cuối (`DeleteEntityAction`). Sai số và va chạm chỉ tính trong khoảng thời gian đó.
