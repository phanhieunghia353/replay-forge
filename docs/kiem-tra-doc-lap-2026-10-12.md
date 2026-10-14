# Kiểm tra độc lập ngày 12/10/2026

Trước khi đổi tiêu chí "tình huống hiếm" và chạy lại toàn bộ, toàn dự án được soát theo hai hướng, rồi đối chiếu:

- **Tự soát:** lượt soát của chính bên viết code, làm **không xem** kết quả của lượt soát kia. Danh sách được ghi ra file trước khi đối chiếu.
- **Soát độc lập:** một lượt soát riêng, chỉ đọc, chạy trong thư mục trống.
  - **Được gửi:** toàn bộ code, test và tài liệu (51 file, khoảng 320 nghìn ký tự, có số dòng) cùng bảng kết quả 10 cảnh.
  - **Không gửi:** dữ liệu nuScenes, three.js, các file kết quả lớn.

Trước đó cùng ngày, lượt soát độc lập đã soát riêng bản nháp tiêu chí "hiếm" (mục 10 của [gia-dinh-va-chi-so.md](gia-dinh-va-chi-so.md)). Các ý của lượt đó tóm tắt ở mục 5.

Mọi phát hiện có thể làm sai số liệu đều được **kiểm lại bằng dữ liệu thật** trong `out/nuscenes-mini/` trước khi ghi vào đây.

## 1. Lỗi làm sai số liệu đã báo cáo

| # | Lỗi | Phát hiện bởi | Kiểm chứng | Ảnh hưởng |
|---|---|---|---|---|
| 1.1 | Khi chấm chỉ số 2, **xe ghi hình cũng bị dựng lại theo từng cách** (`reconstruct()` áp lên mọi quỹ đạo, `pipeline.variants_scene`), trái với tài liệu ("xe ghi hình chạy đúng như bản ghi") | Soát độc lập | `scene-0061`, lúc 10 s: xe ghi hình thật ở (−12,63; −61,57), bản pilot ở (−12,65; −61,57), **bản baseline ở (−14,44; −45,40), lệch khoảng 16 m** | Số tình huống hiếm của **baseline (449) sai**, vì khoảng cách và TTC được đo tới một xe ghi hình không có thật. Pilot gần như không bị ảnh hưởng. So sánh baseline → pilot ở chỉ số 2 chưa công bằng. Số hợp lệ của baseline ít bị ảnh hưởng, vì chồng hộp với xe ghi hình không làm mất hợp lệ |
| 1.2 | **Đếm trùng:** cùng một xe với các mức tốc độ hoặc độ dời gần nhau được đếm thành nhiều tình huống hiếm | Tự soát | 494 biến thể hiếm (pilot) chỉ đến từ **15 cặp cảnh–xe**. Riêng `scene-1100/car_005` có 59 biến thể | Con số "494" phóng đại độ đa dạng |
| 1.3 | **Mốc "cảnh gốc" chưa chuẩn:** (a) thời điểm được miễn va chạm lấy từ bản **đã dựng lại** của từng cách, nên một chồng hộp do chính bước dựng lại gây ra cũng được miễn; (b) "4 tình huống hiếm trong cảnh gốc" đếm theo cặp xe đủ điều kiện biến đổi, còn biến thể đếm theo file, hai đơn vị khác nhau | Soát độc lập (a, b), tự soát (b) | Đọc code `pipeline.py`, `variants.py`; số 4 đến từ 3 cảnh | So sánh "gốc và biến thể" chưa cùng thước đo |
| 1.4 | **Vật thể có mặt sai thời điểm:** trong file `.xosc`, mọi vật thể có mặt từ giây 0 tới hết cảnh. Chúng đứng yên ở vị trí đầu tiên trước khi xuất hiện thật, và ở vị trí cuối sau khi đi khỏi. Biến thể kết thúc sớm cũng đứng lại giữa đường | Tự soát | Đọc `xosc.py`. Phần đo đã che lỗi này bằng cách chỉ xét thời gian vật thể có dữ liệu | Không đổi số đo, nhưng **file giao cho khách hàng có vật cản không có thật**, và xe tự lái khi chạy thử sẽ phản ứng với chúng. File chạy esmini 3.9.0 có chứa `AddEntityAction`, `DeleteEntityAction`, `VisibilityAction`, nên có thể sửa (cần thử) |

## 2. Lỗi trong code chưa gây sai số liệu (đã kiểm) nhưng phải sửa

| # | Lỗi | Phát hiện bởi | Kiểm chứng trên kết quả hiện có |
|---|---|---|---|
| 2.1 | Chấm điểm vẫn chạy khi log esmini thiếu vật thể hoặc thiếu thời gian (nội suy bị kẹp ở biên, giá trị NaN có thể lọt qua phép so sánh `>`) | Soát độc lập | 0/30 file `metrics.json` thiếu vật thể |
| 2.2 | Kịch bản giữ lại mà phát lại đầy đủ thất bại thì vẫn tính là hợp lệ và hiếm. Mã thoát 0 mà không có log vẫn được đếm vào `kept_xosc` | Soát độc lập | 943 = 943 file trên đĩa; 0 ca thất bại |
| 2.3 | "Suýt va chạm" (`ego_collision = False`) có thể thực ra đã chạm xe ghi hình, nếu lần chạm rơi vào đúng thời điểm được miễn | Soát độc lập | 0/224 ca có khoảng cách 0 |
| 2.4 | Chạy lại thì xoá kết quả cũ **trước** khi kết quả mới thành công; log lỗi bị dọn mất | Soát độc lập | Đọc `pipeline.py` |
| 2.5 | Lệnh `report` chỉ thấy cảnh có `tracks_gt.json`, mà file này chỉ do `replay` ghi; cảnh chỉ chạy `variants` sẽ bị bỏ sót | Soát độc lập | Đọc `report.py` |
| 2.6 | Không ghi cấu hình của lượt chạy (phiên bản code, đầu vào, tham số), nên báo cáo có thể gộp kết quả của các lượt khác nhau | Soát độc lập | Đọc `report.py`, `api.py` |
| 2.7 | Mã nguồn CSV có thể trùng: gỡ rồi thêm lại cùng tên thì ghi đè `data/imported/<mã>/` nhưng giữ kết quả cũ | Soát độc lập | Đọc `registry.py` |
| 2.8 | Kiểm tra CSV còn lỏng: hai tên cảnh trùng nhau sau khi bỏ dấu hoặc khác nhau chỉ ở chữ hoa/thường thì ghi đè nhau; loại vật thể bất kỳ có dấu chấm (`spaceship.fake`) vẫn qua | Soát độc lập | Đọc `sources.py` |
| 2.9 | Xe ghi hình nhập từ CSV luôn dùng chiều dài cơ sở của Renault Zoe | Tự soát | Đọc `xosc.py` |

## 3. Phương pháp và cách nói trong tài liệu

| # | Vấn đề | Phát hiện bởi | Hướng sửa |
|---|---|---|---|
| 3.1 | "Đường ống không có lỗi" là nói quá. Sai số `exact` ≈ 0 chỉ chứng minh vị trí và thời gian xuất ra khớp **tại các mốc nhãn** | Soát độc lập | Sửa câu chữ |
| 3.2 | Sai số pilot đo trên **chính dữ liệu dùng để dựng nó**; các lựa chọn thiết kế (mốc 2 s, làm mượt, ngưỡng) cũng chọn trên cùng 10 cảnh. Chưa có kiểm tra trên phần dữ liệu để riêng | Cả hai lượt | Thêm kiểm tra giữ lại một phần mốc nhãn, hoặc thử trên cảnh mới |
| 3.3 | Script thử nghiệm so sánh bốn cách đo (mục 6 của tài liệu chỉ số) chưa nằm trong repo | Soát độc lập | Đưa vào repo, chạy lại được |
| 3.4 | "Tỷ lệ nằm trên đường của biến thể bằng đúng xe thật" là sai, vì biến thể có thể bị cắt bớt và trọng số thời gian thay đổi | Soát độc lập | Sửa câu chữ, hoặc đo riêng cho biến thể |
| 3.5 | Xe đạp (3) và xe máy (7) **đã được biến đổi**, nhưng dùng ngưỡng của ô tô (8 m/s², 40 m/s). Tài liệu chỉ nói "xe" | Tự soát | Ghi rõ; cân nhắc ngưỡng riêng |
| 3.6 | Điều kiện hợp lệ chỉ xét **vật thể bị biến đổi**. Vật thể giữ nguyên có thể có chuyển động phi lý do nhãn, mà kịch bản vẫn được tính hợp lệ | Soát độc lập | Gọi đúng tên ("hợp lệ với vật thể bị biến đổi"), hoặc kiểm một lần cho cả cảnh |
| 3.7 | Va chạm và TTC kiểm theo bước 0,1 s, nên có thể sót lần chạm rất ngắn (người đi bộ mảnh, tốc độ tương đối lớn) | Soát độc lập | Kiểm độ hội tụ với bước nhỏ hơn |
| 3.8 | Quỹ đạo ngắn mà có chuyển động thật vẫn có thể bị coi là "đứng yên" (ví dụ người đi 0,7 m trong 0,5 s) | Soát độc lập | Thêm bằng chứng theo thời gian; báo độ nhạy |
| 3.9 | Vật thể **xoay tại chỗ** bị mất góc quay: `is_static` bỏ qua hướng, và bước loại điểm trùng theo quãng đường bỏ mất thay đổi hướng khi xe đứng | Soát độc lập | Phân biệt "đứng yên vị trí" với "đứng yên hoàn toàn" |
| 3.10 | Test đi vòng qua CSV mới thử xe ghi hình chạy thẳng | Soát độc lập | Thêm ca rẽ, lùi, hướng nhiễu |
| 3.11 | Phần điều phối (`variants_scene`, chạy lại thất bại, log thiếu) chưa có test; chưa có test chạy esmini thật (bỏ qua khi máy không có esmini) để giữ các sửa lỗi esmini | Cả hai lượt | Thêm test |

## 4. Ứng dụng

| # | Lỗi | Phát hiện bởi |
|---|---|---|
| 4.1 | Mở cảnh mới lúc đang ở góc 3D thì khung từ trên xuống bị đặt tỷ lệ 0 (do nó đang ẩn), quay lại thì hỏng | Soát độc lập |
| 4.2 | Đổi nguồn dữ liệu nhanh: danh sách cảnh trả về muộn có thể đè lên nguồn mới | Soát độc lập |
| 4.3 | App vẽ quỹ đạo dựng lại (đầu vào của esmini), không vẽ log esmini. Cách làm này chấp nhận được vì hai thứ khớp tới khoảng 0,001 m, nhưng cần ghi rõ | Tự soát |

## 5. Lượt soát trước: bản nháp tiêu chí "hiếm" (mục 10)

Lượt soát độc lập chỉ ra, lượt tự soát đồng ý. Mục 10 phải sửa trước khi viết code:

- **Bảng mức độ tự mâu thuẫn:** "suýt va chạm" có mức phanh cần bằng 0, nên rơi cả vào ô "bình thường". Cần tách hai câu hỏi:
  - (a) nếu xe ghi hình không phản ứng thì xảy ra gì: xa, sát, hay đâm;
  - (b) chỉ khi đâm: cần phanh bao nhiêu.
- **Tìm mức phanh cần bằng chia đôi khoảng là sai:** ở giao lộ, khả năng tránh được không tăng đều theo mức phanh. Dùng lưới (ví dụ bước 0,25 m/s²). Tốc độ khi phanh phải liền mạch: `v(t) = min(v_ghi(t), v_bắt đầu − a·(t − t_phanh))`.
- **Định nghĩa rõ các trường hợp biên:** TTC đã dưới ngưỡng ngay khi vật thể xuất hiện, va chạm xảy ra trước khi kịp phản xạ, xe ghi hình đang đứng.
- **Tránh vật thể "hiện ra ngay trước mũi xe"** do cắt bớt: bắt buộc vật thể có mặt đủ lâu trước lúc xung đột.
- **Báo cáo minh bạch:** chuỗi tổ hợp → viết ra → hợp lệ → nguy hiểm; tiêu chí cũ và mới đặt cạnh nhau; độ nhạy của ngưỡng; tách lý do loại vì hình học và vì động lực học.
- **Phân loại xung đột đơn giản hơn:** loại vật thể × vị trí tương đối. Không khẳng định hành vi như "chen làn" khi chưa đo.
- **Nguồn ngưỡng đã kiểm:**
  - 3,4 m/s² đi kèm 2,5 s phản xạ là giả định AASHTO cho tầm nhìn dừng xe (FHWA-HRT-04-091, chú thích bảng 11);
  - TTC 1,5 s là mặc định của SSAM (FHWA-HRT-08-051, chương 2).
  - Các ngưỡng khác là giả định của đội.

**Điểm hai bên khác nhau:**
- Lượt soát độc lập khuyên **hoãn** phần đo mức phanh cần vì phức tạp. lượt tự soát đề xuất **giữ**, vì đây là câu trả lời cho câu hỏi "chồng hộp với xe ghi hình có nghĩa gì", nhưng làm bản đơn giản và ghi rõ là "chính sách phanh để sàng lọc".
- Ca "phanh hết sức vẫn không tránh được": lượt soát độc lập muốn giữ và gắn nhãn; bản nháp muốn loại. Đề xuất cách lai: **giữ và báo cáo thành nhóm riêng, không cộng vào con số "hiếm có giá trị"**. Chờ chủ dự án quyết.

## 6. Những gì cả hai bên đều thấy đúng, không đổi

- Cầu sau đặt tại điểm vị trí, thời gian tuyệt đối, `--traj_filter 0`.
- `exact` chỉ dùng để bắt lỗi, tách khỏi so sánh baseline với pilot.
- Miễn va chạm theo đúng thời điểm (sửa mốc tham chiếu, không quay lại miễn cả cặp).
- Lưới thông số cố định; không bịa chuyển động ngoài đường đi đã ghi.
- Trung bình theo vật thể; nhóm "chuyển động/đứng yên" xác định trên nhãn gốc.
- Phát lại rút gọn (chỉ xe bị biến đổi và xe ghi hình) là cách tối ưu hợp lý. Cần kiểm một lần rằng kết quả giống phát lại đầy đủ.

## 7. Kế hoạch sửa (chủ dự án duyệt hướng ngày 12/10/2026)

1. **Sửa nhóm 1 và 2** (số liệu phụ thuộc vào các sửa này), mỗi sửa kèm test:
   - xe ghi hình chạy đúng bản ghi cho cả hai cách;
   - mốc so sánh lấy theo dữ liệu thật;
   - đếm theo sự kiện khác nhau (cảnh × vật thể × kiểu xung đột) bên cạnh số file;
   - vật thể chỉ có mặt trong thời gian có dữ liệu (thử `AddEntityAction`/`DeleteEntityAction` trên esmini);
   - báo lỗi khi log thiếu dữ liệu, và đưa lỗi phát lại đầy đủ vào kết quả;
   - mỗi lượt chạy ghi vào thư mục mới, kèm cấu hình và phiên bản code;
   - `variants` cũng ghi `tracks_gt.json`.
2. **Bộ tiêu chí "hiếm" phiên bản 2** (mục 10, đã sửa theo mục 5), thêm dời thời gian, người đi bộ, ngưỡng riêng cho xe đạp và xe máy.
3. **Thử trên 1–2 cảnh, xem bằng mắt**, rồi **chạy lại 10 cảnh một lần duy nhất**.
4. **Sửa tài liệu (nhóm 3) và app (nhóm 4)**; kiểm tra trên phần dữ liệu để riêng (3.2); đưa script thử nghiệm vào repo (3.3).

## 8. Trạng thái sửa (cập nhật 13/10/2026)

| # | Trạng thái | Ghi chú |
|---|---|---|
| 1.1 | **Đã sửa** | Xe ghi hình chạy đúng bản ghi cho cả hai cách (`variants.method_scene`). Ở `scene-0061`, số hiếm theo tiêu chí cũ của pilot không đổi (40), của baseline từ 37 lên 45 |
| 1.2 | **Đã sửa** | Đếm thêm số sự kiện khác nhau (diễn viên × loại × phía của xe ghi hình) |
| 1.3 | **Đã sửa** | (a) mốc miễn va chạm lấy từ bản ghi thật (`exact`), dùng chung; (b) bản ghi thật được đếm theo sự kiện, cùng đơn vị |
| 1.4 | **Đã sửa** | `AddEntityAction` / `DeleteEntityAction`, thử trên esmini 3.9.0; sai số `exact` không đổi ở cả 10 cảnh. Phải sửa thêm bộ đọc log, vì esmini nối hoặc bỏ khối cột theo vật thể có mặt |
| 2.1–2.6 | **Đã sửa** | Kiểm log chặt; lỗi phát lại đầy đủ làm biến thể mất hợp lệ; "suýt va chạm" theo chồng hộp thật; ghi vào `.new` rồi mới thay; khối `run` trong mọi kết quả; `variants` ghi `tracks_gt.json` |
| 2.7–2.9 | **Đã sửa** | Mã nguồn CSV không trùng thư mục cũ; kiểm loại vật thể và tên cảnh trùng; chiều dài cơ sở của xe ghi hình CSV theo kích thước |
| 3.1, 3.4, 3.6 | **Đã sửa câu chữ** | Trong `gia-dinh-va-chi-so.md` (mục 2.1, 7, 8.2) |
| 3.5 | **Đã sửa** | Ngưỡng riêng cho xe đạp và người đi bộ; xe máy dùng ngưỡng ô tô, có ghi rõ |
| 3.8, 3.9 | **Ghi thành hạn chế** | Mục 4 của `gia-dinh-va-chi-so.md`; chưa đo tần suất |
| 3.11 | **Một phần** | Đã có test điều phối với esmini giả (`tests/test_pipeline.py`); chưa có test chạy esmini thật |
| 3.2, 3.3, 3.7, 3.10 | Chưa làm | Kiểm tra trên dữ liệu để riêng; đưa script bốn cách đo vào repo; kiểm bước 0,05 s; thêm ca rẽ/lùi cho test CSV |
| 4.1, 4.2 | **Đã sửa** | Khung 2D đợi tới khi hiện lại mới tính tỷ lệ; đổi nguồn nhanh thì chỉ lần chọn cuối được dùng |
| 4.3 | **Đã ghi chú** | `docs/kien-truc.md`, mục 3 |
| (thêm) | **Đã làm** | App có danh sách tình huống hiếm và chế độ xem từng biến thể (chủ dự án nhận xét ngày 13/10/2026: app chỉ xem được cảnh gốc) |
| Mục 5 | **Đã làm** | Tiêu chí hiếm phiên bản 2 (mục 10 của `gia-dinh-va-chi-so.md`), chủ dự án duyệt 12/10/2026, chạy trên 10 cảnh 13/10/2026 |
