# Định dạng CSV để đưa dữ liệu của bạn vào real2sim

Muốn dùng real2sim với dữ liệu lái xe của riêng mình (không phải nuScenes), bạn xuất quỹ đạo các vật thể ra **một file CSV** theo mẫu dưới đây. Sau đó thêm vào app bằng **"+ Thêm" → File CSV**, hoặc chạy bằng dòng lệnh với `--csv`.

File mẫu: [`real2sim/app/static/examples/tracks-vi-du.csv`](../real2sim/app/static/examples/tracks-vi-du.csv). Đây là một cảnh tự dựng, gồm xe ghi hình, xe chạy trước rồi phanh, xe ngược chiều, người đi bộ băng qua đường, xe đỗ và nón giao thông. Trong app, hộp thoại "Thêm" có đường dẫn tải file này.

## Cột bắt buộc

Mỗi dòng là **một vật thể tại một thời điểm**:

| Cột | Ý nghĩa | Ví dụ |
|---|---|---|
| `scene` | Tên cảnh. Một file có thể chứa nhiều cảnh. | `nga-tu-1` |
| `time_s` | Thời điểm, tính bằng giây. Mốc 0 tuỳ ý: chương trình tự lấy thời điểm nhỏ nhất của cảnh làm 0. | `12.5` |
| `object_id` | Mã vật thể, giữ nguyên suốt cảnh. **Xe ghi hình phải có mã `ego`.** | `xe_truoc`, `1234` |
| `category` | Loại vật thể (xem bảng dưới) | `car` |
| `x_m`, `y_m` | Vị trí **tâm hộp** vật thể, tính bằng mét | `35.20`, `-3.40` |
| `yaw_rad` | Hướng đầu xe, tính bằng radian, ngược chiều kim đồng hồ tính từ trục x | `1.5708` |
| `length_m`, `width_m`, `height_m` | Kích thước hộp, tính bằng mét | `4.5`, `1.9`, `1.6` |

**Quy ước toạ độ:**
- Dùng một hệ toạ độ phẳng bất kỳ, đơn vị mét, trục x và y vuông góc, ví dụ x hướng đông và y hướng bắc. Chương trình **giữ nguyên** toạ độ của bạn, không dời gốc.
- Nếu có file đường OpenDRIVE, file đó phải cùng hệ toạ độ với file CSV.
- Chiều cao (z) không dùng.
- Kích thước có thể khác nhau giữa các dòng; chương trình lấy trung vị của từng vật thể.
- Tần số lấy mẫu tuỳ ý (2 lần/giây như nuScenes, 10 lần/giây…) và không cần đều. Vật thể chỉ xuất hiện một lần được coi là đứng yên.

## Loại vật thể (`category`)

| Giá trị | Nghĩa |
|---|---|
| `car` | Xe con |
| `truck` | Xe tải |
| `bus` | Xe buýt |
| `trailer` | Rơ-moóc |
| `construction` | Xe công trình |
| `emergency` | Xe ưu tiên |
| `motorcycle` | Xe máy |
| `bicycle` | Xe đạp |
| `pedestrian` | Người đi bộ |
| `animal` | Động vật |
| `barrier` | Rào chắn |
| `cone` | Nón giao thông |
| `object` | Vật cản khác |

Tên loại đầy đủ theo nuScenes (ví dụ `vehicle.bus.bendy`) cũng được chấp nhận. Cột `category` của xe ghi hình (`ego`) không được dùng.

## File đường OpenDRIVE (tuỳ chọn)

Nếu có bản đồ đường dạng OpenDRIVE (`.xodr`) cho một cảnh, đặt tên file là **`<tên cảnh>.xodr`**:
- trong app: chọn file ở ô "File đường OpenDRIVE";
- ở dòng lệnh: đặt file cạnh `tracks.csv`.

esmini sẽ vẽ và dùng đường này khi phát lại. Hiện khung xem trong app **chưa vẽ** được đường từ file `.xodr`; nó chỉ vẽ bản đồ của nuScenes.

## Kiểm tra lỗi

Khi thêm file, chương trình kiểm và báo lỗi theo số dòng, tối đa 20 lỗi một lần. Ví dụ:
- `Thiếu cột: yaw_rad, ...`
- `Dòng 15: cột 'x_m' không phải số ('abc')`
- `Dòng 22: loại vật thể 'spaceship' không hợp lệ`
- `Cảnh 'nga-tu-1': cần vật thể 'ego' (xe ghi hình) với ít nhất 2 dòng.`
- `Cảnh 'nga-tu-1', vật thể 'xe_7': có hai dòng cùng thời điểm.`

File bị lỗi sẽ **không** được thêm. Sửa rồi thêm lại.

## Dùng bằng dòng lệnh

```powershell
.venv\Scripts\python.exe -m real2sim --csv duong\den\thu-muc scenes
.venv\Scripts\python.exe -m real2sim --csv duong\den\thu-muc replay --scene nga-tu-1
.venv\Scripts\python.exe -m real2sim --csv duong\den\thu-muc variants --scene nga-tu-1
```

`--csv` nhận thư mục chứa `tracks.csv` (và các file `.xodr`), hoặc đường dẫn tới chính file CSV. Kết quả nằm ở `out\<tên thư mục>\<cảnh>\`.

Muốn xem một cảnh nuScenes thật ở dạng CSV:

```powershell
.venv\Scripts\python.exe -m real2sim export-csv --scene scene-0061 --to scene-0061.csv
```

Đã kiểm chứng: chạy `scene-0061` từ file CSV xuất ra cho **cùng bảng sai số** với khi chạy trực tiếp từ nuScenes.

## Lưu ý về kết quả

- **Chất lượng nhãn quyết định chất lượng kịch bản.** Bản pilot làm mượt được độ rung nhỏ của nhãn. Nhưng nếu dữ liệu đầu vào nhảy vị trí lớn hay mất mốc thời gian dài, biến thể có thể bị loại vì gia tốc phi lý.
- **Xe ghi hình được phát lại đúng như dữ liệu.** Trong kiểm thử thật, vị trí của nó sẽ do phần mềm lái xe cần kiểm tra điều khiển.
