# Thiết kế giao diện cho người dùng (chốt 14/10/2026)

Chủ dự án đã duyệt qua ba bản phác. Tài liệu này ghi lại bản chốt, để làm theo và để kiểm khi làm xong.

## 1. Vì sao làm lại

Giao diện cũ là màn hình xem kết quả của người làm ra tool:
- không có nút tạo kịch bản, chỉ xem được lưới biến thể tool tự sinh;
- dùng thuật ngữ nội bộ (pilot / baseline, ADE, nhóm hợp lệ), người ngoài không biết bấm gì;
- không tải được file `.xosc`, mà đó là sản phẩm của đề.

## 2. Ai dùng

| Người dùng | Cần gì | Chế độ |
|---|---|---|
| Ban giám khảo, giám đốc dự án | Hiểu tool làm gì trong vài phút, thử một tình huống, thấy kết luận rõ | **Đơn giản** (mặc định) |
| Kỹ thuật viên kiểm thử của công ty xe tự lái | Tin được dữ liệu, hiểu chuyện gì xảy ra, biết giả định, tìm ranh giới nguy hiểm, biết vì sao được nhận hay bị loại, tải file chạy đúng và tái tạo được | **Kỹ thuật** |

Hai chế độ dùng chung một màn hình và cùng dữ liệu. Chuyển bằng nút ở góc trên phải. Chế độ kỹ thuật **thêm** thông tin, không thay cách làm.

## 3. Bố cục chung

- **Thanh trên:** chọn nguồn dữ liệu và cảnh, ba bước (Chọn xe → Chỉnh cách phanh → Xem và tải), nút chuyển chế độ. Ở chế độ kỹ thuật có thêm cảnh báo chất lượng nhãn của cảnh và nhãn truy vết (commit, phiên bản esmini).
- **Giữa:** khung xem cảnh (từ trên xuống, có thể chuyển 3D) và thanh thời gian.
- **Cột phải:** tạo tình huống, kết quả, nút tải.
- **Ngăn dưới** (chỉ ở chế độ kỹ thuật): 7 tab, mục 5.
- Nơi thêm nguồn dữ liệu và chạy xử lý cả cảnh (nút "Xử lý") vẫn giữ, gom vào một hộp "Dữ liệu" mở từ thanh trên.

## 4. Chế độ đơn giản

1. **Chọn xe:** cảnh thật phát lại. Chỉ những xe **chọn được** (đang có xe khác chạy phía sau, đủ nhanh, còn đủ dữ liệu) có viền hồng. Bấm vào xe đó để chọn.
2. **Chỉnh cách phanh:** lúc nào (kéo thanh thời gian), mạnh cỡ nào (nhẹ 2 / vừa 4 / gấp 6 m/s²; xe buýt, xe tải tối đa 5), rồi làm gì (dừng hẳn / dừng 3 s / chậm lại còn nửa tốc độ). Bấm **"Tạo tình huống"**.
3. **Xem và tải:** các xe phía sau phản ứng ngay trên khung xem. Kết luận là một câu:
   - dùng được: "Dùng được · suýt chạm. Xe của bạn phanh 3,6 m/s², dừng cách 0,9 m.";
   - không dùng được: lý do bằng lời thường, kèm gợi ý ("Xe buýt phía sau không thể dừng kịp. Thử phanh nhẹ hơn hoặc chọn lúc khác.").
   - Nút **Phát lại** và **Tải .xosc**. Trước khi cho tải, tool chạy esmini kiểm lại.
- Tab **"Tự tìm ca hiếm"**: các ca đáng chú ý nhất trong kết quả đã xử lý của cảnh, mỗi ca có "Xem"; một nút tải tất cả.
- Xe ghi hình gọi là **"xe của bạn"** (xe tự lái đang được thử).

## 5. Chế độ kỹ thuật

Thiết kế theo các câu kỹ thuật viên sẽ hỏi.

| Câu hỏi | Chỗ trả lời |
|---|---|
| Dữ liệu gốc có tin được không? | Cảnh báo trên thanh trên; tab **Dữ liệu gốc**: từng vật thể, số mốc nhãn, thời gian có mặt, sai số phát lại (chỉ số 1), chỗ nhãn lỗi (nhảy vị trí, tốc độ phi lý). |
| Chính xác điều gì đã xảy ra? | Lớp phủ trên khung xem, bật/tắt từng lớp: bóng vị trí trong bản ghi, mũi tên "ai đang theo ai", khoảng cách và TTC của xe của bạn, mã xe, dải đường đi, vạch dừng và đèn, đo khoảng cách. Thanh thời gian có mốc sự kiện (bắt đầu phanh, từng xe phản ứng, lúc gần nhất, lúc vi phạm) và bước ±0,05 s. |
| Mô hình người lái giả định gì? | Cột phải: tham số sự kiện bằng số chính xác (thời điểm, mức phanh kèm giới hạn của xe, độ giật, đích, thời gian dừng); tham số người lái (phản xạ, IDM a/b, T và s₀ từng xe, đánh dấu **đo từ bản ghi** hay **mặc định**). Nút **"Thử độ nhạy"**: chạy lại với phản xạ 0,7 / 1,0 / 1,5 s, so kết luận. |
| Nguy hiểm tới mức nào, ranh giới ở đâu? | Tab **Biểu đồ**: tốc độ, gia tốc, khoảng cách, TTC theo thời gian, chọn xe, có đường ngưỡng và nét đứt của bản ghi. Tab **Không gian tham số**: lưới mức phanh × thời điểm phanh của một xe, tô theo kết quả, bấm ô để mở; dạng bảng để lọc, sắp xếp. |
| Vì sao được nhận hay bị loại? | Tab **Kiểm tra hợp lệ**: từng điều kiện, ngưỡng, số đo xấu nhất, lúc xảy ra (bấm để nhảy tới), các chồng hộp được miễn. Tab **Các xe**: dải trạng thái theo thời gian (theo bản ghi → phản xạ → tự lái → quay lại kế hoạch), xe phía trước, T và s₀, mức phanh đã dùng so với giới hạn, khoảng cách gần nhất. |
| File xuất ra có chạy đúng, có tái tạo được không? | Tab **Độ khớp esmini**: esmini lệch bao nhiêu so với quỹ đạo định đưa, gia tốc đo trong esmini. Tab **Xuất và truy vết**: `.xosc`, `.xodr`, `trajectories.csv`, `report.json`; lệnh chạy esmini; phiên bản dữ liệu, commit code, bộ ngưỡng. |

**Giới hạn hiện ra trên màn hình, không giấu:** mục "Kích hoạt" ghi rõ file giao đi dùng quỹ đạo tính sẵn theo thời gian. Nếu phần mềm lái của khách hàng chạy khác người lái mẫu, các xe khác không phản ứng lại.

## 6. Dữ liệu cần thêm ở máy chủ

| API | Việc | Dựa trên |
|---|---|---|
| `GET /api/candidates` | xe chọn được và khoảng thời gian chọn được | `events.candidates` (mở rộng: theo xe, theo thời điểm bất kỳ) |
| `POST /api/simulate` | một tình huống bất kỳ (xe, thời điểm, mức phanh, đích, thời gian dừng, phản xạ): quỹ đạo các xe bị đổi, trạng thái từng xe theo thời gian, chuỗi số cho biểu đồ, kết quả kiểm tra chi tiết, mốc sự kiện | `behavior.simulate`, `events.assess` (thêm: lịch sử trạng thái, xe phía trước, chi tiết kiểm tra) |
| `POST /api/export` | chạy esmini kiểm lại rồi trả gói `.zip` | `pipeline.simulate`, `events.outcome_scene`, `write_road` |
| `GET /api/scene` (mở rộng) | chất lượng nhãn từng vật thể, lưới đã xử lý cho bản đồ tham số | báo cáo `events/<method>/report.json`, `metrics.json` |

Mô phỏng một tình huống mất dưới 1 s, nên "Tạo", "Thử độ nhạy" chạy ngay. Chỉ "Tải" mới chạy esmini (vài giây).

## 7. Làm theo thứ tự, mỗi bước kiểm trên trình duyệt

1. Máy chủ: các API ở mục 6, có test.
2. Chế độ đơn giản: chọn xe, tạo, kết luận, tải.
3. Chế độ kỹ thuật: cột phải đầy đủ, lớp phủ, mốc thời gian, 7 tab.
4. Kiểm: test, mở thử trên trình duyệt từng luồng, tải một file `.xosc` và mở bằng esmini; cập nhật README và `kien-truc.md`; commit.

## 8. Trạng thái (14/10/2026)

Đã làm đủ mục 4–6 và thử trên trình duyệt (1440 × 900):
- chọn xe → chỉnh → tạo → kết luận → xuất: scene-0061, `car_008` phanh 6 m/s² lúc 7 s, dừng 3 s: "Dùng được · ca hiếm: suýt chạm"; esmini chạy lại lệch tối đa 0,0001 m; gói `.zip` 235 KB;
- ca không dùng được có lời giải thích: scene-0553, `car_006` phanh 6 m/s² lúc 1 s: "car_010 (xe phía sau) đâm vào car_006 lúc 3,1 s, dù đã phanh 7,0 m/s²…";
- 7 tab của ngăn dưới, chế độ 3D, hộp "Dữ liệu…": không lỗi trên console; vẽ khung xem trung vị 0,4 ms.

Chưa làm: trang tổng quan hai chỉ số cho ban giám khảo (đã đề xuất, chưa chốt); kích hoạt theo khoảng cách thay cho theo thời gian (giới hạn ghi ở mục 5).

**Thêm (14/10/2026, đề xuất của chủ dự án):** dấu "?" cạnh các thông số, nhãn, cột bảng và điều kiện kiểm tra (`help.js`). Mỗi thuật ngữ có đúng một lời giải thích (là gì, đo thế nào, lấy từ đâu), lấy theo `docs/gia-dinh-va-chi-so.md`; mở bằng di chuột, bấm (màn hình cảm ứng) hoặc phím Tab, đóng bằng Escape.
