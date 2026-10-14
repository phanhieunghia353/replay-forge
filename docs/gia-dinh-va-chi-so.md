# Giả định và định nghĩa chỉ số — đề N3-09B

> Đề thi không cho phép hỏi lại ban tổ chức, nên chỗ nào đề chưa nói rõ, đội tự định nghĩa theo cách phổ biến và ghi lại ở đây. Mục nào ghi **(đề xuất)** là chưa chốt.
>
> Cập nhật: 13/10/2026, sau khi sửa các lỗi của [tài liệu soát độc lập](kiem-tra-doc-lap-2026-10-12.md) và chạy lại cả 10 cảnh bằng tiêu chí "hiếm" phiên bản 2 (mục 10).

> **Về các mã commit trong tài liệu này** (ví dụ `d74cd6a`, `91eaca1`, `923feef`): đó là lịch sử phát triển trước khi repo được công khai; bản công khai bắt đầu từ một commit gộp. Phần code tạo ra các số liệu của chỉ số 1, kiểm chéo và chỉ số 2 (dựng quỹ đạo, xuất kịch bản, esmini, mô phỏng hành vi, kiểm hợp lệ) không đổi giữa các mã đó và commit công khai đầu tiên, nên chạy lại bằng commit công khai cho ra cùng số.

## 1. Đề bài

- **Mã đề:** N3-09B "Xuất cảnh thật thành kịch bản mô phỏng" (chủ đề 09 · Real2Sim).
- **Dữ liệu:** nuScenes; mô phỏng bằng esmini hoặc CARLA.
- **Yêu cầu:** chuyển quỹ đạo của các vật thể đã gán nhãn thành kịch bản OpenSCENARIO, rồi sinh biến thể đổi tốc độ và khoảng cách để tạo tình huống hiếm.
- **Chỉ số:** sai số quỹ đạo khi phát lại; số kịch bản hợp lệ sinh được. Mỗi chỉ số đo hai lần, baseline → pilot, trên cùng dữ liệu.

## 2. Dữ liệu và công cụ

| Thứ | Phiên bản | Ghi chú |
|---|---|---|
| nuScenes | v1.0-mini (10 scene) | Chỉ dùng các bảng JSON: hộp nhãn 3D ở các khung hình chính (khoảng 2 lần mỗi giây), mã theo dõi vật thể `instance_token`, vị trí xe ghi hình `ego_pose`. Giấy phép CC BY-NC-SA 4.0, chỉ dùng phi thương mại. |
| nuScenes map expansion | v1.3 | Bản đồ làn đường, được chuyển sang OpenDRIVE (xem mục 2.1) và dùng để kiểm xe có nằm trên đường không. |
| esmini | v3.9.0 | Giấy phép MPL-2.0. Chạy không mở cửa sổ (`--headless`), bước thời gian cố định 0,05 s (`--fixed_timestep`), tắt bộ gộp điểm (`--traj_filter 0`), ghi log vị trí từng vật thể (`--csv_logger`). |
| OpenSCENARIO | XML 1.1 | Mỗi vật thể chuyển động chạy theo một hành động `FollowTrajectoryAction`, đường đi dạng `Polyline` gồm các điểm có gắn thời gian, thời gian tính tuyệt đối theo giờ mô phỏng (`absolute`), chế độ bám `position`. |

**Những điểm của esmini 3.9.0 đã phát hiện và xử lý.** Mỗi điểm đều đã được đo lại sau khi sửa.

1. **Tự dời hộp xe:** esmini coi điểm vị trí là tâm cầu sau. Nếu cầu sau không nằm đúng điểm vị trí, esmini tự dời hộp xe. Cách xử lý: luôn đặt cầu sau tại điểm vị trí (xem mục 3).
2. **Khởi hành trễ một bước:** hành động được kích hoạt theo giờ sẽ bắt đầu chậm đúng một bước (0,05 s). Với thời gian tính "từ lúc khởi hành" (`relative`), cả quỹ đạo bị trễ theo.
   - Đo ở scene-1077: xe chạy 13–18 m/s lệch trung bình 0,56–0,77 m. Đọc log lùi 0,05 s thì sai số chỉ còn 0,004–0,032 m.
   - Cách xử lý: dùng thời gian tuyệt đối (`absolute`). Sai số `exact` của scene-1077 giảm từ 0,292 m xuống 0,001 m.
3. **Gộp điểm gần nhau:** mặc định `--traj_filter 0.1` gộp các điểm trên đường đi nằm gần nhau dưới 0,1 m. Xe chạy dưới khoảng 1 m/s (các điểm cách nhau 0,1 s) vì thế bị đứng khựng vài bước rồi nhảy, gây gia tốc giả tới 11,7 m/s².
   - Cách xử lý: tắt bằng `--traj_filter 0`. Gia tốc của `car_038` (scene-0916) trong esmini giảm từ 11,7 xuống 2,2 m/s², khớp với quỹ đạo dựng lại.
4. **Bộ lái `followReference`:** esmini chỉ tự tạo xe dẫn đường cho xe đầu tiên dùng bộ lái này (xem mục 6).

### 2.1. Mạng đường OpenDRIVE từ bản đồ nuScenes

**Nguồn dữ liệu:** mỗi làn (`lane`) và mỗi đoạn nối trong giao lộ (`lane_connector`) của map expansion có sẵn đường tâm trong bảng `arcline_path_3`. Đường tâm được lưu thành chuỗi phần tử. Mỗi phần tử gồm:
- tư thế đầu (x, y, hướng);
- một chuỗi ba chữ trong {L, S, R} (L là cung tròn rẽ trái, S là đoạn thẳng, R là cung tròn rẽ phải);
- một bán kính;
- ba độ dài, mỗi độ dài ứng với một chữ.

**Kiểm chứng cách đọc:** cộng dồn ba đoạn của mỗi phần tử rồi so với tư thế cuối mà bản đồ ghi sẵn. Đã thử trên toàn bộ 10.703 phần tử của 4 bản đồ: lệch vị trí tối đa 2,6·10⁻¹² m, lệch hướng tối đa 5·10⁻¹⁴ độ.

**Cách chuyển sang OpenDRIVE:**
- Mỗi làn hoặc đoạn nối thành **một con đường OpenDRIVE**. Trục đường là đường tâm làn, ghép từ các đoạn `<line>` (thẳng) và `<arc>` (cung tròn) giống hệt dữ liệu gốc.
- Mỗi con đường có một làn xe (`-1`), được căn giữa trên trục bằng `laneOffset` = nửa độ rộng làn.
- **Độ rộng làn** = diện tích đa giác của làn ÷ chiều dài đường tâm, rồi kẹp trong khoảng 2,5–5,0 m (đề xuất).
- **Phạm vi:** chỉ lấy các làn có điểm đầu hoặc điểm cuối nằm trong hình chữ nhật bao quanh mọi quỹ đạo của scene, nới rộng thêm 30 m mỗi phía.
- **Vạch kẻ:** làn thường có vạch trắng hai bên. Đoạn nối trong giao lộ không có vạch, giống đường thật.
- **Chưa ghi:** liên kết giữa các làn và cấu trúc giao lộ (`junction`). File bản đồ dùng để esmini vẽ mặt đường và làn xe, chưa dùng để tìm đường.

**Kết quả:**
- 10/10 scene nạp bản đồ trong esmini với mã thoát 0, không có cảnh báo hay lỗi nào. Mỗi scene có 38–170 con đường.
- Sai số phát lại `exact` không đổi khi có bản đồ (≤ 0,001 m).
- Các kịch bản hiếm được giữ lại (lượt 13/10/2026: baseline 118, pilot 94) đi kèm file `<scene>_map.xodr` và được phát lại đầy đủ có đường: 0 lỗi.

**Kiểm "xe nằm trên đường"** dùng các đa giác `drivable_area` (vùng xe chạy được) của bản đồ:
- **Bản đồ khớp vị trí:** xe ghi hình nằm 100% trong vùng xe chạy được ở cả 10 scene.
- **Một số xe có phần đường đi nằm ngoài vùng này**, ví dụ:
  - xe máy ở scene-0796 (9%) và scene-1100 (0–61%);
  - xe buýt ở scene-0757 và scene-1100 (70–76%), nhiều khả năng đang tấp vào trạm;
  - xe đạp, xe tải và xe con khi đi vào lối rẽ.

  Không xe nào nằm trong bãi đỗ (`carpark_area`). Biến thể đi trên **cùng đường đi** đã ghi nên không đi ra chỗ mới. Tuy vậy, tỷ lệ thời gian nằm trên đường của biến thể **không nhất thiết bằng** của xe thật: biến thể có thể bị cắt bớt một đoạn, hoặc đi nhanh chậm khác nhau ở từng đoạn. Tỷ lệ này chỉ được **báo cáo cho xe thật**, không dùng để loại biến thể. Người đi bộ không tính, vì họ đi trên vỉa hè.

## 3. Hệ toạ độ và quy ước

- **Toạ độ của cảnh:** trục x hướng đông, trục y hướng bắc, đơn vị mét. Gốc toạ độ là vị trí xe ghi hình ở khung hình chính đầu tiên. Thời điểm 0 là khung hình chính đầu tiên.
- **Điểm vị trí của vật thể đã gán nhãn** là tâm hộp nhãn.
- **Điểm vị trí của xe ghi hình** là tâm cầu sau, theo đúng quy ước nuScenes. Tâm hộp của xe nằm lệch lên trước 1,39 m.
- **Cách esmini hiểu điểm vị trí:** esmini luôn coi điểm vị trí là tâm cầu sau, và sẽ tự dời hộp xe nếu cầu sau không nằm đúng điểm đó. Vì vậy trong kịch bản, cầu sau luôn được đặt tại điểm vị trí. Với vật thể đã gán nhãn, đó là một "cầu sau danh nghĩa" đặt tại tâm hộp, để hộp xe nằm đúng chỗ của nhãn. Đã kiểm bằng log esmini: vị trí tâm hộp ra 0 m với vật thể và 1,39 m với xe ghi hình.
- **Thời gian xuất hiện:** vật thể chỉ có mặt trong kịch bản khi có nhãn. Nó xuất hiện 0,1 s trước nhãn đầu (`AddEntityAction`) và biến mất 0,1 s sau nhãn cuối (`DeleteEntityAction`). Sai số chỉ tính trong khoảng thời gian vật thể có nhãn.
  - Trước 12/10/2026, vật thể có mặt từ giây 0 tới hết cảnh: đứng yên ở vị trí đầu trước khi có nhãn, và ở vị trí cuối sau khi hết nhãn. File giao đi vì vậy có "vật cản ma".
  - Đã kiểm trên esmini 3.9.0: sai số `exact` không đổi ở cả 10 cảnh, đến từng vật thể.

## 4. Ba cách dựng kịch bản

| Cách | Đường đi | Tốc độ | Vai trò |
|---|---|---|---|
| `exact` | Đi qua đúng các điểm nhãn thô | Suy từ thời điểm của từng điểm | Bắt lỗi chương trình. Sai số phải xấp xỉ 0. **Không dùng làm chỉ số** (xem mục 6). |
| `baseline` | Nối thẳng các điểm nhãn thô, giữ nguyên độ rung | **Một** tốc độ không đổi trong suốt thời gian vật thể có nhãn | Bản đơn giản ban đầu |
| `pilot` | Vật thể đứng yên được ghim tại vị trí trung bình. Vật thể chuyển động có đường đi được làm mượt. | Thay đổi theo từng đoạn **2 s** | Bản cải tiến |

Chi tiết của `pilot`:

- **Vật thể đứng yên:** nếu mọi vị trí đều cách vị trí trung bình dưới **max(1,0 m; ¼ chiều dài vật)** (đề xuất), vật thể được coi là đứng yên, vị trí rung chỉ do nhãn. Khi đó nó được đặt cố định tại vị trí trung bình, hướng lấy theo hướng trung bình.
  - **Vì sao ngưỡng tăng theo kích thước:** vật càng lớn thì người gán nhãn đặt hộp càng kém chính xác.
  - **Ví dụ đã gặp:** xe tải `truck_006` trong scene-0061 dài 6 m, đỗ yên suốt 14 s. Giữa giây 13,65 và 14,55, hộp nhãn của nó nhảy 0,8 m (người gán nhãn chỉnh lại hộp), nên tổng độ lệch lên 1,05 m. Với ngưỡng cố định 1,0 m, xe này bị coi là đang chạy, gia tốc tính ra lên tới 10,75 m/s².
- **Làm mượt đường đi:** mỗi trục toạ độ được làm mượt bằng hàm `scipy.interpolate.make_smoothing_spline`. Hàm này tự chọn mức làm mượt theo dữ liệu (phương pháp kiểm định chéo tổng quát, GCV), nên không phải tự chỉnh tay. Vật thể có dưới 5 điểm nhãn thì không làm mượt được (giới hạn của scipy), khi đó nối thẳng các điểm.
- **Hướng xe:**
  - Khi vật đi nhanh hơn 0,5 m/s, hướng lấy theo hướng chuyển động.
  - Nếu hướng chuyển động ngược với hướng của hộp nhãn (xe đang lùi), hướng xe giữ theo hộp, không quay ngược lại.
  - Khi vật đi chậm hơn, hướng lấy theo hướng của hộp nhãn đã làm mượt.
- **Hồ sơ tốc độ:** cứ mỗi 2 s đặt một mốc. Tại mỗi mốc giữ đúng quãng đường đã đi theo đường đã làm mượt. Giữa hai mốc, quãng đường được nối bằng đường cong bậc ba đơn điệu (PCHIP), nên tốc độ thay đổi liền mạch và không bao giờ âm. Bản đầu từng nối thẳng giữa hai mốc; khi đó tốc độ nhảy bậc tại mỗi mốc, gia tốc tính ra phi lý và biến thể bị loại oan, nên đã bỏ.
- **Điểm trên đường đi:** cứ 0,1 s một điểm.

**Hạn chế đã biết của luật "đứng yên"** (tài liệu soát, mục 3.8–3.9):
- Một quỹ đạo ngắn mà có chuyển động thật vẫn có thể bị coi là đứng yên. Ví dụ: người đi 0,7 m trong 0,5 s vẫn nằm dưới ngưỡng 1,0 m.
- Luật chỉ xét vị trí, bỏ qua hướng, nên một vật **xoay tại chỗ** bị ghim với một hướng trung bình. Bước bỏ điểm trùng theo quãng đường (khi dựng lại) cũng làm mất thay đổi hướng lúc xe đứng.
- Chưa đo những trường hợp này xảy ra bao nhiêu lần trong 10 cảnh.

**Vì sao tốc độ phải tóm thành vài con số:** các con số này chính là chỗ sẽ chỉnh khi sinh biến thể (nhân tốc độ lên, đổi thời điểm xuất phát…). Vì vậy sai số phát lại của bản tóm gọn cho biết các thông số đó giữ lại được bao nhiêu phần chuyển động thật.

## 5. Chỉ số 1: sai số quỹ đạo khi phát lại

**Cách đo:** chạy kịch bản bằng esmini, đọc vị trí và hướng của từng vật thể trong log, nội suy theo thời gian, rồi so với **nhãn gốc thô** tại các khung hình chính nằm trong khoảng vật thể có nhãn.

| Đại lượng | Định nghĩa |
|---|---|
| ADE (m) | Khoảng cách trung bình (trên mặt phẳng) giữa vị trí mô phỏng và vị trí nhãn |
| FDE (m) | Khoảng cách tại khung hình chính cuối cùng |
| max (m) | Khoảng cách lớn nhất |
| yaw (độ) | Sai số hướng trung bình (giá trị tuyệt đối) |
| v RMSE (m/s) | Căn trung bình bình phương sai lệch giữa tốc độ mô phỏng (lấy ở điểm giữa mỗi quãng) và tốc độ suy từ hai nhãn liên tiếp |

**Cách gộp:** lấy trung bình theo từng vật thể, chia nhóm: tất cả / chuyển động / đứng yên / xe / người / vật cản. Nhóm "chuyển động" và "đứng yên" được xác định trên **nhãn gốc**, theo ngưỡng 1,0 m ở mục 4, và dùng chung cho cả ba cách dựng.

**Con số chính (đề xuất):** ADE của nhóm **chuyển động**.

**Mức sàn do nhãn rung:** bản thân nhãn đã rung, nên mọi cách đo "so với nhãn" đều có một mức sàn gần bằng độ rung đó. Một bản dựng loại bỏ được độ rung (ví dụ ghim vật đứng yên tại vị trí trung bình) vẫn sẽ cho sai số khác 0 khi so với nhãn, dù nó gần sự thật hơn. Vì thế với nhóm đứng yên, so baseline với pilot **không** nói lên cách nào tốt hơn.

## 6. Vì sao chọn cách đo này

Đội đã thử bốn cách định nghĩa "sai số phát lại" trên một cảnh giả biết chính xác quỹ đạo thật:

- **Cảnh giả:** 3 xe (rẽ trái rồi dừng; chuyển làn rồi giảm tốc; đỗ yên).
- **Nhãn giả:** lấy mẫu 2 lần mỗi giây, cộng rung ngẫu nhiên phân phối chuẩn, với độ lệch 5, 15 và 30 cm cho vị trí và 2° cho hướng.
- **Số lần lặp:** 10 lần cho mỗi mức rung, tổng 120 lượt chạy esmini, tất cả mã thoát 0.

Cách đo tốt phải xếp hạng thô → cải tiến **cùng chiều** với sai số so với sự thật. Kết quả ở mức rung 15 cm (ADE trung bình 3 xe, mét):

| Cách đo | So với nhãn: thô → cải tiến | So với sự thật: thô → cải tiến | Kết luận |
|---|---|---|---|
| Chép từng điểm, so tại điểm nhãn | 0,004 → 0,133 | 0,155 → 0,102 | Xếp **ngược chiều**, loại |
| Giấu một nửa số điểm rồi đoán lại | 0,260 → 0,222 | 0,192 → 0,136 | Đúng chiều nhưng chênh ít, không cần tới mô phỏng |
| Tài xế ảo của esmini (`FollowReferenceController`) bám theo đường đi | 0,609 → 0,506 | 0,588 → 0,458 | Đúng chiều, nhưng sai số chủ yếu do bộ lái của esmini: còn khoảng 0,45 m ngay cả khi nhãn chỉ rung 5 cm |
| **Tóm gọn thành vài thông số** (cách được chọn) | 5,27 → 0,24 | 5,46 → 0,20 | Đúng chiều ở cả 3 mức rung, gắn trực tiếp với việc sinh biến thể |

Hai mức rung còn lại cho cùng kết luận. Bản trước có đề xuất dùng tài xế ảo để kiểm tra biến thể có chạy được không trong chỉ số 2; đề xuất này **chưa làm**, chỉ số 2 hiện không dùng tài xế ảo.

**Giới hạn của thử nghiệm:**
- Cảnh giả chỉ có 3 xe, không có người đi bộ, không có bản đồ đường.
- Độ rung giả định là ngẫu nhiên và độc lập giữa các điểm, trong khi nhãn thật có thể rung theo kiểu khác.
- Script thử nghiệm hiện chưa nằm trong repo.

**Ghi chú về esmini:** esmini 3.9.0 chỉ tự tạo "xe dẫn đường" cho xe đầu tiên có bộ lái `followReference`; các xe sau báo lỗi "No valid reference entity and no ghost". Cách vòng qua: tự tạo cho mỗi xe một xe dẫn đường riêng chạy đúng quỹ đạo, rồi trỏ tới nó qua tham số `ReferenceEntity`.

## 7. Kết quả chỉ số 1 trên 10 scene nuScenes mini

Ngày chạy: 09/10/2026, chạy lại ngày 13/10/2026 (commit `923feef`, esmini v3.9.0) sau các sửa của tài liệu soát. Số liệu hai lần chạy giống hệt nhau, vì các sửa không đụng tới cách dựng quỹ đạo. Mọi lượt esmini đều thoát với mã 0, và log có đủ mọi vật thể trong suốt thời gian có nhãn. Bảng tổng được sinh bằng lệnh `report` (file `out/nuscenes-mini/summary.md`).

ADE của nhóm chuyển động, tính bằng mét, so với nhãn gốc:

| scene | số vật thể chuyển động | exact | baseline | pilot |
|---|---|---|---|---|
| scene-0061 | 48 | 0,000 | 0,769 | 0,042 |
| scene-0103 | 43 | 0,000 | 1,191 | 0,061 |
| scene-0553 | 26 | 0,000 | 4,111 | 0,098 |
| scene-0655 | 11 | 0,001 | 1,154 | 0,091 |
| scene-0757 | 20 | 0,001 | 2,660 | 0,062 |
| scene-0796 | 36 | 0,000 | 1,850 | 0,133 |
| scene-0916 | 12 | 0,000 | 1,650 | 0,062 |
| scene-1077 | 55 | 0,001 | 1,722 | 0,231 |
| scene-1094 | 61 | 0,000 | 1,550 | 0,058 |
| scene-1100 | 23 | 0,000 | 2,471 | 0,068 |
| **Tất cả** (trung bình theo vật thể) | **335** | **0,000** | **1,771** | **0,098** |

- `exact` ra 0,000–0,001 m (trung bình), lớn nhất 0,033 m ở một vật thể. Điều này chứng minh vị trí và thời gian xuất ra esmini rồi đọc lại khớp **tại các mốc nhãn**: không lệch trục, không trễ, không mất vật thể. Nó **không** chứng minh toàn bộ chương trình không có lỗi; ví dụ phần chấm biến thể có những lỗi riêng mà tài liệu soát đã tìm ra. Kết quả này có được sau khi đã xử lý hai điểm của esmini nêu ở mục 2: khởi hành trễ một bước, và gộp điểm gần nhau.
- Pilot giảm ADE khoảng **18 lần** so với baseline, và tốt hơn ở cả 10/10 scene.
- **Kiểm chéo trên mốc nhãn bị giấu:** mục 7.1. Các lựa chọn của pilot (mốc tốc độ 2 s, cách làm mượt, ngưỡng đứng yên) vẫn được chọn khi nhìn chính 10 cảnh này; kiểm chéo giấu nhãn chứ không giấu cảnh.
- `scene-1077` có sai số pilot cao nhất (0,231 m). Đây là cảnh đêm trên đường lớn, các xe đã kiểm chạy 13–18 m/s. Nhiều khả năng mốc tốc độ 2 s bỏ sót nhiều chi tiết hơn khi xe chạy nhanh. Đây là giả thuyết, chưa kiểm chứng.
- Với nhóm đứng yên, pilot có thể ra cao hơn baseline. Đây là do mức sàn nhãn rung đã nêu ở mục 5, không có nghĩa pilot kém hơn.

### 7.1. Kiểm chéo: sai số trên mốc nhãn bị giấu (14/10/2026)

Câu hỏi: 0,098 m của pilot đo **trên chính các mốc nhãn đã dùng để dựng quỹ đạo**. Liệu pilot có đúng **giữa** các nhãn, hay chỉ khớp những điểm đã biết?

**Cách làm** (lệnh `holdout`, file `real2sim/holdout.py`, commit `91eaca1`):
- với mỗi vật thể chuyển động có từ 5 mốc nhãn, giấu một nửa số mốc (mốc thứ 2, 4, 6…; giữ mốc đầu và cuối);
- dựng lại cả ba cách từ nửa còn lại, đo khoảng cách trên nửa bị giấu;
- không chạy esmini: phát lại chỉ làm lệch khoảng 0,001 m (sai số `exact` ở trên), nhỏ hơn nhiều so với các khác biệt đo ở đây.
- Ở bảng này, `exact` nghĩa là **nối thẳng** giữa các nhãn còn lại.

| | nối thẳng (exact) | baseline | pilot |
|---|---|---|---|
| ADE trên mốc bị giấu, 321 vật thể (m) | 0,091 | 1,983 | **0,133** |
| ADE trên mốc đã dùng (mục 7, để so) | 0,000 | 1,771 | 0,098 |

**Độ êm** của quỹ đạo dựng từ toàn bộ nhãn: gia tốc lớn nhất (phân vị 99, lấy mẫu 0,05 s) của từng vật thể chuyển động:

| | nối thẳng (exact) | baseline | pilot |
|---|---|---|---|
| trung vị (m/s²) | 7,42 | 0,07 | 0,83 |
| tỷ lệ vật thể vượt 4 m/s² | 81% | 2% | 16% |

**Diễn giải:**
- Pilot **không chỉ khớp điểm đã biết**: trên mốc bị giấu sai số tăng từ 0,098 lên 0,133 m, vẫn nhỏ hơn baseline 15 lần, và tốt hơn baseline ở cả 10/10 cảnh.
- **Nối thẳng giữa các nhãn khớp vị trí tốt hơn pilot một chút** (0,091 so với 0,133 m). Nhưng nhãn bị rung, nên nối thẳng tạo gia tốc giả: 81% số vật thể có lúc tăng tốc hoặc phanh quá 4 m/s², so với 16% ở pilot. Kịch bản phát lại kiểu nối thẳng nhìn giật cục và không dùng làm gốc để sinh biến thể được (chỉ số 2 kiểm giới hạn vật lý).
- Vì vậy pilot là đánh đổi có chủ ý: mất khoảng **4 cm** độ khớp vị trí để được chuyển động **hợp vật lý** và gọn (tốc độ mỗi 2 s).
- `scene-1077` vẫn tệ nhất (0,298 m trên mốc bị giấu), khớp với giả thuyết ở mục 7: xe chạy nhanh, mốc 2 s bỏ sót chi tiết.

## 8. Chỉ số 2: số kịch bản hợp lệ sinh được

> Từ 13/10/2026 chỉ số 2 đo trên cách sinh biến thể **theo hành vi** ([thiết kế](thiet-ke-kich-ban-hanh-vi.md), giai đoạn 1). Cách cũ (dời thời gian, đổi tốc độ cả quỹ đạo) được giữ ở [Phụ lục A](#phụ-lục-a-chỉ-số-2-theo-cách-cũ-đã-thay) để so sánh.

### 8.1. Sinh biến thể

Mỗi biến thể là **một xe phía trước phanh**, đúng như chữ "đổi tốc độ và khoảng cách" của đề: tốc độ của xe đó giảm, khoảng cách tới các xe phía sau thu hẹp.

- **Xe được chọn:** xe đang chạy (≥ 3 m/s), không phải xe ghi hình, đang có một xe khác chạy theo sau (ít nhất 1 s trong khoảng −0,5 … +3 s quanh lúc phanh), và còn dữ liệu ít nhất 4 s sau lúc phanh.
- **Lưới cố định, chốt trước khi chạy** (không ngẫu nhiên, chạy lại luôn ra cùng kết quả):
  - lúc bắt đầu phanh: mỗi 2 s (1, 3, 5, … s);
  - mức phanh: 2, 4, 6, 8 m/s² (xe buýt, xe tải tối đa 5 m/s², nên chỉ 2 và 4);
  - đích: dừng hẳn; dừng 3 s rồi đi tiếp; xuống nửa tốc độ.
  - Bỏ biến thể nếu cảnh hết trước khi sự kiện kết thúc cộng 4 s.
- **Xe phanh** tăng dần lực phanh (độ giật tối đa 10 m/s³), rồi tăng tốc lại về kế hoạch của nó (tối đa 1,5 m/s²).
- **Xe không bị ảnh hưởng** chạy đúng bản dựng `pilot` của nó; xe ghi hình chạy đúng bản ghi cho tới khi phải phản ứng.

### 8.2. Baseline và pilot

| | Baseline | Pilot |
|---|---|---|
| Xe phanh | phanh như lưới | phanh như lưới |
| Các xe phía sau, kể cả xe ghi hình | **không phản ứng**: chạy đúng bản ghi | **phản ứng như người lái**: thấy xe trước chậm lại, sau 1 s phản xạ thì tự lái theo mô hình IDM cải tiến (Kesting, Treiber, Helbing 2010), giữ khoảng cách T và s₀ đo từ chính bản ghi của từng xe; phanh tối đa 8 m/s² (xe buýt, xe tải 5) |
| Danh sách biến thể, bộ kiểm hợp lệ | như nhau | như nhau |

**Vì sao baseline là "không phản ứng":** đó là cách sinh biến thể ngây thơ nhất và phổ biến nhất: đổi chuyển động của một vật thể, các vật thể khác phát lại nguyên bản ghi. Cách cũ của chính dự án (Phụ lục A) cũng là kiểu này. Chỉ số 2 vì vậy đo **cái giá của việc không mô phỏng phản ứng**: bao nhiêu biến thể trở thành phi lý (xe sau đâm xuyên xe trước). Baseline này dễ bị vượt, và điều đó được nói rõ ở đây, không giấu.

### 8.3. Điều kiện hợp lệ

Một biến thể **hợp lệ** khi qua **cả 7** điều kiện. Các điều kiện xét mọi xe có chuyển động khác bản gốc.

1. **esmini** phát lại file xuất ra: mã thoát 0, log có đủ mọi vật thể trong thời gian có mặt.
2. **Vật lý:** tăng tốc ≤ 4 m/s²; phanh ≤ giới hạn của loại xe + 0,2 m/s²; tốc độ ≤ 40 m/s. Đo từ chính vị trí x, y (trung bình 0,2 s), nên bắt được mọi bước nhảy.
3. **Nhãn gốc không lỗi:** nếu chỗ vi phạm vật lý trùng (trong 5 m dọc đường đi) với chỗ chính nhãn gốc của xe đó đã phi lý, lý do ghi là "nhãn gốc lỗi". Biến thể **vẫn bị loại**, vì kịch bản sẽ chứa chuyển động đó.
4. **Không xe nào đâm nhau**, trừ khi một trong hai là xe ghi hình. Chồng hộp có sẵn trong bản ghi (cùng cặp, cùng vị trí tương đối: lệch dọc < 1,5 m, lệch ngang < 0,75 m, sâu hơn không quá 0,1 m) được miễn.
5. **Không bám sát phi lý:** khoảng cách cản < 0,5 m khi xe sau chạy > 3 m/s, kéo dài quá 0,5 s.
6. **Chưa hỗ trợ: nhập làn, cắt ngang, người đi bộ.** Va chạm giữa hai xe lệch hướng quá 30° trong 3 s trước khi chạm, hoặc với người đi bộ, vật cản: tương tác này chưa được mô phỏng, nên biến thể bị loại chứ không đoán.
7. **Chưa hỗ trợ: xe vừa vào khung hình.** Va chạm trong 2 s đầu sau khi một trong hai xe mới có dữ liệu: không biết trước đó nó ở đâu.

Chồng hộp với **xe ghi hình** không làm mất hợp lệ ở baseline: đó là tình huống phần mềm lái xe phải tự xử lý (nhóm "xe ghi hình đâm").

### 8.4. Cách đếm

- **Biến thể hợp lệ / biến thể thử:** con số chính của chỉ số 2.
- **Lần phanh** = một xe phanh ở một thời điểm, gộp các mức phanh và đích của nó. Báo số lần phanh có ít nhất một biến thể hợp lệ, để thấy 12 biến thể có thể chỉ là một tình huống.
- **Tình huống hiếm** (đo trên xe ghi hình; ngưỡng giữ từ tiêu chí phiên bản 2, mục 10):
  - **suýt chạm:** hoặc một xe **trên đường đi của xe ghi hình** (phía trước hay phía sau, hai hộp chồng nhau theo chiều ngang, tức cùng làn) có lúc cách < 1 m; hoặc, ở bất kỳ phía nào, TTC < 1,5 s. Phải gần hơn chính cặp xe đó trong bản ghi ít nhất 0,1 m (hoặc 0,1 s). Báo cáo ghi xe nào, ở phía nào, và vế nào khớp.
    - Xe **đi song song ở làn bên** không tính theo khoảng cách, dù sát: đó là giao thông bình thường. Trước 14/10/2026 vế khoảng cách tính ở mọi phía; chủ dự án phát hiện 8/26 ca hiếm ở `scene-0796` là xe của làn bên (car_013, bị chậm lại do phản ứng) đi song song cách 0,7–0,9 m, TTC vô cùng, xe ghi hình nhiều khi không phải làm gì. Luật đã sửa (commit `d74cd6a`).
  - **phải phanh gấp:** mức phanh tối thiểu để tránh > 3,4 m/s² (AASHTO), tính sau 1 s phản xạ;
  - không hiếm: "phanh nhẹ là đủ", "không ảnh hưởng".

### 8.5. Kết quả trên 10 scene nuScenes mini

**Lượt chạy:** 14/10/2026, commit `d74cd6a` (luật "suýt chạm" đã sửa, mục 8.4), esmini v3.9.0. Cả 10 cảnh, cả hai cách trong một lượt. Số kịch bản hợp lệ giống hệt hai lượt trước (`f4ce096`, `342ef05`); chỉ số ca hiếm đổi (26 → 18) do sửa luật. Bảng tổng sinh bằng lệnh `report` (`out/nuscenes-mini/summary.md`).

| scene | biến thể | baseline hợp lệ | pilot hợp lệ | lần phanh có biến thể hợp lệ (baseline / pilot, trên tổng) | hiếm baseline | hiếm pilot |
|---|---|---|---|---|---|---|
| scene-0061 | 91 | 70 (76,9%) | 75 (82,4%) | 12 / 20 trên 20 | 3 | 12 (4 lần phanh) |
| scene-0103 | 24 | 9 (37,5%) | 15 (62,5%) | 2 / 4 trên 4 | 1 | 0 |
| scene-0553 | 131 | 5 (3,8%) | 80 (61,1%) | 4 / 26 trên 36 | 0 | 0 |
| scene-0655 | 0 | – | – | – | – | – |
| scene-0757 | 71 | 10 (14,1%) | 44 (62,0%) | 5 / 9 trên 18 | 0 | 0 |
| scene-0796 | 48 | 14 (29,2%) | 27 (56,2%) | 5 / 10 trên 13 | 0 | 0 |
| scene-0916 | 0 | – | – | – | – | – |
| scene-1077 | 243 | 40 (16,5%) | 181 (74,5%) | 15 / 44 trên 50 | 0 | 6 (2 lần phanh) |
| scene-1094 | 50 | 36 (72,0%) | 50 (100%) | 10 / 10 trên 10 | 0 | 0 |
| scene-1100 | 119 | 41 (34,5%) | 119 (100%) | 16 / 23 trên 23 | 0 | 0 |
| **Tổng** | **777** | **225 (29,0%)** | **591 (76,1%)** | **69 / 146 trên 174** | **4** | **18 (6 lần phanh)** |

`scene-0655` và `scene-0916` không có biến thể nào: trong hai cảnh này không xe nào chạy sau một xe khác, ngoài xe ghi hình.

**Lý do bị loại** (một biến thể có thể có nhiều lý do):

| lý do | baseline | pilot |
|---|---|---|
| các xe khác đâm nhau | 488 | 33 |
| xe vừa vào khung hình đúng chỗ tình huống (chưa mô phỏng) | 68 | 74 |
| nhập làn, cắt ngang, người đi bộ (chưa mô phỏng) | 51 | 40 |
| nhãn gốc lỗi | 3 | 63 |
| bám sát phi lý | 10 | 3 |
| sai vật lý | 0 | 1 |

**Biến thể hợp lệ theo việc xe ghi hình phải làm:**

| nhóm | baseline | pilot |
|---|---|---|
| phải phanh gấp | 0 | 0 |
| **suýt chạm** | 4 | 18 |
| phanh nhẹ là đủ | 0 | 59 |
| không ảnh hưởng | 105 | 514 |
| xe ghi hình đâm (không ai phản ứng) | 116 | 0 |

**Diễn giải:**
- **Chỉ số 2, baseline → pilot: 225 → 591 kịch bản hợp lệ (29,0% → 76,1%)**, cùng 777 biến thể. Pilot tốt hơn ở cả 8/8 cảnh có biến thể. Tính theo lần phanh: 69 → 146 trên 174 lần phanh có ít nhất một biến thể dùng được.
- Khác biệt chính: "các xe khác đâm nhau" giảm từ 488 xuống 33. Baseline để xe sau chạy xuyên qua xe trước; pilot cho xe sau phanh.
- **33 vụ đâm còn lại của pilot là đâm thật về vật lý**: xe sau đã phanh hết mức của nó mà không kịp, vì bám quá sát trong bản ghi (ví dụ `car_010` cách 2 m ở 8,5 m/s) hoặc vì là xe buýt (tối đa 5 m/s²). Ngoài đời các vụ đó cũng sẽ xảy ra; chúng bị loại vì kịch bản có va chạm giữa các xe khác không dùng để thử xe tự lái được.
- Pilot có nhiều "nhãn gốc lỗi" hơn (3 → 63) vì nó thay đổi nhiều xe hơn, nên nhiều xe đi qua chỗ nhãn bị lỗi hơn. Đây là lỗi của dữ liệu, tool báo ra chứ không giấu.
- **116 biến thể hợp lệ của baseline là xe ghi hình đâm**: theo định nghĩa (mục 8.3), va chạm với xe ghi hình là tình huống cho phần mềm lái xe tự xử lý nên vẫn hợp lệ. Không tính chúng thì baseline còn 109 (14,0%).
- Ca hiếm: 4 → 18 biến thể, trong 4 → 6 lần phanh; tất cả thuộc nhóm "suýt chạm", và cả 18 đều là xe ghi hình chạy ngay sau xe phanh, phải phanh 2,5–5 m/s² (`scene-0061`: `car_008`; `scene-1077`: `car_013`). Trước khi sửa luật (mục 8.4) con số là 26: 8 ca ở `scene-0796` là xe làn bên đi song song, đã bỏ. Nhóm "phải phanh gấp" trống: trong 10 cảnh phố chậm này, xe ghi hình chưa bao giờ cần phanh quá 3,4 m/s². Con số ca hiếm **phụ thuộc nhiều vào giả định phản xạ**, xem 8.6.
- **Cách cũ** (Phụ lục A) cho 46,4% → 57,9%, nhưng đếm trên lưới khác, bộ kiểm khác, và biến thể của nó trông giả (xe chạy xuyên nhau, không ai phản ứng). Hai bảng không so trực tiếp được.


### 8.6. Độ nhạy

Chạy lại toàn bộ 10 cảnh với thời gian phản xạ của người lái (cả xe khác lẫn xe ghi hình) là 0,7 s và 1,5 s, giữ nguyên mọi thứ khác (lệnh `events --reaction`, kết quả ở `out/sensitivity/`).

| phản xạ | baseline hợp lệ | pilot hợp lệ | hiếm baseline | hiếm pilot |
|---|---|---|---|---|
| 0,7 s | 225 (29,0%) | 607 (78,1%) | 4 | 0 |
| **1,0 s** (đã chọn) | 225 (29,0%) | 591 (76,1%) | 4 | 18 |
| 1,5 s | 225 (29,0%) | 493 (63,4%) | 4 | 41 |

- **Kết luận chính đứng vững:** với mọi giá trị phản xạ, pilot sinh nhiều kịch bản hợp lệ hơn baseline nhiều (63–78% so với 29%). Phản xạ càng chậm thì càng nhiều xe sau không kịp dừng, nên tỷ lệ pilot giảm dần.
- **Số ca hiếm không vững:** 0 / 18 / 41. Phản xạ chậm thì xe ghi hình tới gần hơn trước khi phanh, nên nhiều ca "suýt chạm" hơn; với người lái phản xạ nhanh (0,7 s) thì không còn ca nào. Vì vậy khi trình bày, **không** nói "tool tạo được 18 ca hiếm" mà không kèm giả định: phải nói "18 ca hiếm, với người lái phản xạ 1 s; từ 0 tới 41 ca khi phản xạ 0,7 tới 1,5 s".
- Một lần esmini thoát bất thường (mã −1) ở `scene-1100` khi chạy lại sau một lần ngắt phiên; chạy lại thì bình thường. Biến thể nào gặp lỗi esmini bị tính là không hợp lệ (lý do `esmini`), nên một lỗi như vậy chỉ làm số hợp lệ thấp đi, không cao lên.
- Baseline không đổi vì trong baseline không ai phản ứng.


### 8.7. Hạn chế

- Chỉ một kiểu tình huống: xe phía trước phanh. Chưa có chen làn, giao lộ, người đi bộ băng qua.
- Xe chỉ phản ứng theo chiều dọc (phanh, tăng tốc), không đánh lái.
- Tham số người lái (phản xạ 1 s, a, b, độ giật) là giả định có nguồn tham khảo; chỉ T và s₀ đo được từ nhãn 2 Hz.
- File giao đi dùng quỹ đạo tính sẵn theo thời gian: nếu phần mềm lái của khách hàng chạy khác người lái mẫu, các xe khác không phản ứng lại.
- 10 cảnh mini, phần lớn trong phố, xe chạy chậm: chưa có ca "phải phanh gấp".

## 9. Danh sách giả định

| Giả định | Giá trị | Ở đâu |
|---|---|---|
| Kích thước xe ghi hình (Renault Zoe) | 4,084 × 1,730 × 1,562 m | `tracks.EGO_SIZE` |
| Tâm hộp xe ghi hình so với cầu sau | 1,39 m phía trước | `tracks.EGO_BBOX_CENTER_X` |
| Chiều dài cơ sở xe ghi hình | 2,588 m | `tracks.EGO_WHEELBASE` |
| Chiều dài cơ sở của xe đã gán nhãn | 0,6 × chiều dài xe | `tracks.WHEELBASE_RATIO` |
| Ngưỡng coi là đứng yên | max(1,0 m; 0,25 × chiều dài) | `tracks.STATIONARY_EXTENT`, `tracks.STATIONARY_LENGTH_RATIO` |
| Khoảng cách giữa hai mốc tốc độ (pilot) | 2,0 s | `abstraction.KNOT_SPACING` |
| Khoảng cách thời gian giữa các điểm trên đường đi | 0,1 s | `abstraction.DT` |
| Tốc độ tối thiểu để lấy hướng theo chuyển động | 0,5 m/s | `abstraction.MIN_HEADING_SPEED` |
| Bước thời gian của esmini | 0,05 s | tham số `--dt` |
| Lưới hệ số tốc độ | 0,5 … 1,5, bước 0,1 | `variants.SPEED_FACTORS` |
| Lưới độ dời dọc đường đi | −10 … +10 m, bước 2,5 m | `variants.OFFSETS` |
| Khoảng cách sát để tính là hiếm | 1,0 m | `variants.RARE_GAP` |
| Sai lệch thời gian khi miễn va chạm có sẵn trong bản gốc | 0,1 s | `variants.ALLOWED_DT` |
| Thời gian tối thiểu còn lại của một biến thể | 2,0 s | `variants.MIN_VARIANT_SPAN` |
| Tốc độ tối đa | 40 m/s | `variants.MAX_SPEED` |
| Gia tốc tối đa (dọc và ngang) | 8 m/s² | `variants.MAX_ACCEL` |
| Ngưỡng TTC để tính là hiếm | 1,5 s | `variants.RARE_TTC` |
| Phạm vi lấy làn quanh scene | 30 m | `__main__.MAP_MARGIN` |
| Độ rộng làn hợp lệ (kẹp) | 2,5–5,0 m | `nuscenes_map.MIN_LANE_WIDTH`, `MAX_LANE_WIDTH` |
| Khoảng nhìn trước khi tính TTC | 5 s, bước 0,1 s | `safety.TTC_HORIZON`, `safety.TTC_STEP` |
| Thời gian vật thể xuất hiện sớm / biến mất muộn so với dữ liệu | 0,1 s | `xosc.PRESENCE_MARGIN` |
| Sai lệch thời gian cho phép khi kiểm log esmini | 0,001 s | `esmini.LOG_TIME_TOL` |
| *Tiêu chí hiếm phiên bản 2 (mục 10):* | | |
| Lưới dời dọc đường, người đi bộ | −4 … +4 m, bước 1 m | `variants.PEDESTRIAN_OFFSETS` |
| Lưới dời thời gian | −4 … +4 s, bước 1 s, bỏ 0 | `variants.TIME_SHIFTS` |
| Xe đạp: tốc độ, gia tốc tối đa | 12 m/s, 4 m/s² | `variants.BICYCLE_MAX_SPEED`, `BICYCLE_MAX_ACCEL` |
| Người đi bộ: tốc độ, gia tốc tối đa | 3,0 m/s, 3 m/s² | `variants.PEDESTRIAN_MAX_SPEED`, `PEDESTRIAN_MAX_ACCEL` |
| Sát: TTC, khoảng cách | 1,5 s, 1,0 m | `variants.CLOSE_TTC`, `CLOSE_GAP` |
| TTC phát hiện | 3,0 s | `variants.DETECT_TTC` |
| Thời gian phản xạ | 1,0 s | `variants.REACTION` |
| Phanh nhẹ tối đa (AASHTO) | 3,4 m/s² | `variants.COMFORT_DECEL` |
| Phanh gấp tối đa | 8,0 m/s² | `variants.MAX_DECEL` |
| Lưới mức phanh | 0,2 … 8,0 m/s², bước 0,2 | `variants.DECELS`, `DECEL_STEP` |
| Có mặt trước xung đột | 2,0 s | `variants.MIN_PRESENCE` |
| Khoảng cách tối thiểu khi xuất hiện / biến mất giữa cảnh | 20 m (tâm hộp) | `variants.POP_DISTANCE` |
| Coi là có mặt từ đầu / tới cuối cảnh | trong 0,25 s đầu / cuối | `variants.EDGE_TOL` |
| Tốc độ coi là đang đứng khi phanh | 0,5 m/s | `variants.STANDING_SPEED` |
| Các giá trị thử độ nhạy | mục 10.8 | `variants.SENSITIVITY` |
| *Giai đoạn 1: xe phía trước phanh, xe phía sau phản ứng ([thiết kế](thiet-ke-kich-ban-hanh-vi.md), mục 4):* | | |
| Lưới sự kiện | mỗi 2 s; phanh 2, 4, 6, 8 m/s²; dừng, dừng 3 s, nửa tốc độ | `events.EVENT_STEP`, `DECELS`, `TARGETS` |
| Thời gian phản xạ | 1,0 s | `behavior.REACTION` |
| IDM: tăng tốc, phanh thoải mái | 1,5 m/s², 2,0 m/s² | `behavior.IDM_A`, `IDM_B` |
| Phanh gấp tối đa: xe con, xe máy, xe đạp | 8,0 m/s² | `behavior.MAX_DECEL` |
| Phanh gấp tối đa: xe buýt, xe tải, xe công trình, rơ-moóc | 5,0 m/s² (FMVSS 121: xe tải dừng từ 60 mph trong 250 ft, trung bình khoảng 4,7 m/s²) | `behavior.HEAVY_MAX_DECEL` |
| Độ giật: khi phanh, khi chạy thường | 10 m/s³, 3 m/s³; cần phanh khi đang tăng tốc thì nhả ga ngay rồi mới đạp phanh | `behavior.JERK_BRAKE`, `JERK_NORMAL` |
| Hợp lệ: tăng tốc tối đa, vượt mức phanh cho phép | 4 m/s², 0,2 m/s² | `events.MAX_ACCEL`, `DECEL_SLACK` |
| Lỗi vật lý trùng chỗ lỗi trong nhãn gốc thì ghi là "nhãn gốc lỗi" | trong 5 m dọc đường đi | `events.LABEL_REACH` |
| Hai xe lệch hướng quá 30° trong khoảng này trước khi chạm là nhập làn / cắt ngang, không phải bám đuôi | 3 s | `events.MERGE_LOOKBACK` |

---

## 10. ĐÃ DUYỆT: bộ tiêu chí "tình huống hiếm" phiên bản 2

> Mục này được viết cho **cách sinh biến thể cũ** (Phụ lục A). Chỉ số 2 hiện tại (mục 8) dùng lại các ngưỡng "suýt chạm" (1 m, 1,5 s), "phải phanh gấp" (3,4 m/s²) và phản xạ 1 s, nhưng đo trên người lái mẫu có phản ứng; các phần về dời thời gian, người đi bộ, `pop_in` không còn áp dụng.

> **Trạng thái:** chủ dự án duyệt ngày 12/10/2026 (mục 10.12). Đã đưa vào code và chạy trên cả 10 cảnh ngày 13/10/2026; kết quả ở mục 8.4. Bản này sửa bản nháp đầu theo mục 5 của [tài liệu soát](kiem-tra-doc-lap-2026-10-12.md), và theo quyết định của chủ dự án cùng ngày: ca "phanh hết sức vẫn không tránh được" được **giữ thành nhóm riêng, không cộng vào con số chính**.
>
> Sau khi được duyệt, mục này thay mục 8.3. Mọi ngưỡng được chốt **trước** khi chạy lại, và áp như nhau cho baseline, pilot và bản ghi thật. Những điểm cần chủ dự án duyệt được gom ở mục 10.12.

### 10.1. Vì sao cần làm lại

Tiêu chí hiện tại (mục 8.3) gọi một biến thể là hiếm khi TTC < 1,5 s hoặc hai hộp cách nhau < 1,0 m. Nó gộp chung những ca rất khác nhau. Ví dụ ở `scene-0061`: cả 40 biến thể hiếm của pilot đều là xe `car_008` chạy trước xe ghi hình, chậm lại, rồi bị xe ghi hình (chạy theo bản ghi, không phanh) tông vào đuôi. Câu hỏi đáng hỏi là: **một tài xế bình thường có tránh được không, và phải phanh mạnh cỡ nào?**
- Nếu phanh nhẹ là đủ: đó là chuyện thường ngày, không hiếm.
- Nếu phải phanh gấp: đó là bài thi có giá trị cho xe tự lái.
- Nếu phanh hết sức vẫn không tránh được (ví dụ bị tông từ phía sau): dùng làm bài thi thì không công bằng, nhưng vẫn là thông tin có ích.

Ngoài ra:
- **Đếm trùng:** 40 file ở trên chỉ là **1 sự kiện**. Từ 12/10/2026 báo cáo đã đếm theo sự kiện (mục 8.3).
- **Ít kiểu tình huống:** chỉ xe bị biến đổi, và chỉ dời tối đa ±10 m. Vì vậy gần như mọi ca hiếm là "xe phía trước chậm lại".

### 10.2. Vai trò

- **Xe được kiểm tra** là xe ghi hình. Trong kiểm thử thật, nó do phần mềm lái xe điều khiển. Trong đánh giá này:
  - nó chạy theo **đường đi và tốc độ đã ghi**, giống nhau cho baseline và pilot;
  - để trả lời "có tránh được không", ta giả định một **tài xế tham chiếu** chỉ biết phanh, không đánh lái (mục 10.4b).
- **Diễn viên** là vật thể bị biến đổi trong một biến thể. Mọi vật thể khác chạy lại đúng như bản ghi (đã dựng lại theo baseline hoặc pilot).

### 10.3. Cách tạo biến thể (mở rộng)

Mỗi biến thể đổi đúng **một diễn viên**, theo một trong hai họ lưới.

**Họ A: tốc độ × dời dọc đường** (như hiện nay)

| Thông số | Ý nghĩa | Lưới |
|---|---|---|
| Hệ số tốc độ `k` | đi nhanh hoặc chậm hơn trên cùng đường đi | 0,5 … 1,5, bước 0,1 |
| Dời dọc đường `d` | xuất phát lùi hoặc tiến trên chính đường đi của nó | xe: −10 … +10 m, bước 2,5 m; **người đi bộ: −4 … +4 m, bước 1 m** |

Bỏ tổ hợp không đổi gì (`k = 1`, `d = 0`), còn 98 biến thể cho mỗi diễn viên. Lưới dời của người đi bộ hẹp hơn vì họ thường chỉ đi vài mét trong cảnh. Dời ±10 m thì gần như mọi biến thể bị cắt hết.

**Họ B: dời thời gian × tốc độ** (mới)

| Thông số | Ý nghĩa | Lưới |
|---|---|---|
| Dời thời gian `τ` | cả chuyển động của diễn viên xảy ra sớm hơn (`τ < 0`) hoặc muộn hơn (`τ > 0`) `τ` giây | −4 … +4 s, bước 1 s, bỏ 0 |
| Hệ số tốc độ `k` | như họ A | 0,5 … 1,5, bước 0,1 |

Có 8 × 11 = 88 biến thể cho mỗi diễn viên. Ví dụ: một xe cắt ngang giao lộ 3 s sau xe ghi hình. Dời `τ = −3 s` thì nó tới giao lộ cùng lúc với xe ghi hình. Họ A không tạo được ca này, vì dời ±10 m không bù được 3 s.

**Quy tắc chung cho cả hai họ:**
- Vẫn **không bịa chuyển động** ngoài đường đi đã ghi. Phần bị đẩy ra ngoài đường đi, hoặc ra ngoài thời lượng cảnh, thì bị cắt. Còn dưới 2 s thì không viết kịch bản.
- Diễn viên chỉ có mặt trong thời gian có dữ liệu (mục 8.1).
- **Không xuất hiện hay biến mất giữa đường** (quyết định của chủ dự án, 12/10/2026): biến thể **không hợp lệ** nếu diễn viên xuất hiện sau đầu cảnh, hoặc biến mất trước cuối cảnh, khi tâm hộp của nó cách tâm hộp xe ghi hình **dưới 20 m**. Lý do loại là `pop_in` / `pop_out`.
  - Ví dụ chủ dự án phát hiện trên ảnh động: `car_008` chạy 70% tốc độ, lùi 10 m. Lùi trên đường đi làm mất đoạn đầu quỹ đạo, nên xe hiện ra giữa đường ngay trước mũi xe ghi hình.
  - Căn cứ cho mức 20 m, đo trên 10 cảnh mini, với những vật thể bắt đầu hoặc kết thúc có nhãn giữa cảnh:
    - xe bắt đầu có nhãn ở cách xe ghi hình ít nhất 18 m, 97% ở xa hơn 20 m (trung vị 63 m); khi hết nhãn, xe cách ít nhất 24 m;
    - người đi bộ bắt đầu có nhãn ở cách ít nhất 21 m; khi hết nhãn, 8% ở gần hơn 20 m (ví dụ đi vào nhà).
  - Ngoài đời, vật thể "xuất hiện" ở rìa tầm cảm biến, không hiện ra ngay trước mũi xe.
  - Luật áp cho mọi biến thể. Bản ghi thật và bản dựng lại chưa biến đổi cũng được kiểm theo luật này, nhưng chỉ để báo cáo.

**Diễn viên:** mọi vật thể chuyển động có dữ liệu ít nhất 2 s, trừ xe ghi hình. Trên 10 cảnh mini có:

| Loại | Số diễn viên |
|---|---|
| Xe (ô tô, xe tải, xe buýt…) | 142 |
| Xe hai bánh (xe đạp, xe máy) | 10 |
| Người đi bộ (**mới**) | 154 |
| Tổng | 306 (hiện nay 152) |

**Người đi bộ chạm người đi bộ vẫn hợp lệ** (quyết định của chủ dự án, 12/10/2026). Người đi bộ hay đi theo cặp, theo nhóm. Ví dụ ở `scene-0061`, `pedestrian_002` và `pedestrian_019` đi sát vai nhau; cho một người đi muộn 1 s là hộp hai người chạm nhau. Ngoài đời, họ chỉ cần nhường nhau nửa bước.
- Với luật cũ, 2.811 biến thể của cảnh này bị loại chỉ vì lý do đó.
- Người đi bộ chạm **xe** hoặc **vật cản**, hay xe chạm người đi bộ, thì **vẫn loại**.
- Báo cáo đếm riêng số biến thể hợp lệ có "người chạm người".

**Giới hạn vật lý theo loại** (điều kiện hợp lệ, mục 8.2):

| Loại | Tốc độ tối đa | Gia tốc tối đa | Ghi chú |
|---|---|---|---|
| Xe, xe máy | 40 m/s | 8 m/s² | như hiện nay. Xe máy phanh và tăng tốc gần như ô tô, nên dùng chung ngưỡng |
| Xe đạp | 12 m/s (≈ 43 km/h) | 4 m/s² | đề xuất |
| Người đi bộ | 3,0 m/s (chạy chậm) | 3 m/s² | đề xuất |

### 10.4. Hai câu hỏi cho mỗi biến thể hợp lệ

Bản nháp đầu trộn hai câu hỏi vào một bảng nên tự mâu thuẫn. Ví dụ: ca suýt va chạm có mức phanh cần bằng 0, nên rơi vào cả ô "bình thường" lẫn ô "suýt va chạm". Bản này tách thành hai câu hỏi, hỏi lần lượt.

#### (a) Nếu xe ghi hình không phản ứng, chuyện gì xảy ra?

Xe ghi hình chạy đúng bản ghi; đo trên log esmini. Mỗi biến thể hợp lệ rơi vào **đúng một** trong ba trường hợp:

| Kết cục | Điều kiện |
|---|---|
| **Đâm** | hộp diễn viên chồng lên hộp xe ghi hình ở ít nhất một thời điểm **không được miễn**. Thời điểm được miễn là lúc bản ghi thật cũng chồng hộp với cùng diễn viên, lệch tối đa 0,1 s, giống luật ở mục 8.2 |
| **Sát** | không đâm, nhưng TTC nhỏ nhất < 1,5 s hoặc khoảng cách nhỏ nhất < 1,0 m |
| **Xa** | còn lại |

Các ca chỉ chồng hộp ở thời điểm được miễn được xếp vào "sát". Số ca loại này được báo riêng, vì chúng có thể đến từ sai số gán nhãn.

#### (b) Chỉ khi đâm: tài xế tham chiếu phải phanh mạnh cỡ nào?

1. **Lúc phát hiện** `t_pháthiện`: thời điểm đầu tiên mà **một trong hai** cách tính TTC xuống dưới **3,0 s**:
   - **TTC thường:** cả hai giữ nguyên vận tốc, đi thẳng;
   - **TTC theo đường đi:** xe ghi hình giữ nguyên tốc độ **dọc đường đi của chính nó** (tài xế biết đường phía trước), còn diễn viên đi thẳng theo vận tốc hiện tại (tài xế không biết ý định của người khác).

   Nếu nguy hiểm đã có ngay khi diễn viên xuất hiện, `t_pháthiện` là lúc diễn viên xuất hiện. Cả hai cách chỉ dùng thông tin đo được tại thời điểm đó, không biết trước tương lai.
   - **Vì sao cần TTC theo đường đi** (thêm ngày 12/10/2026, sau khi thử `scene-0061`): TTC thường kéo dài chuyển động thành đường thẳng. Khi hai xe cùng vào cua, đường thẳng không cắt nhau, nên TTC = ∞ cho tới khi rất gần. Ví dụ: `car_008` chạy 50% tốc độ, xe ghi hình tiến lại gần đều 4 m/s từ 10 m, nhưng TTC thường vẫn là ∞ tới khi chỉ còn 3,4 m. Ca này bị xếp oan là "không tránh được". Với TTC theo đường đi, ca này được phát hiện khoảng 3,5 s trước va chạm, và chỉ cần phanh 1,2 m/s².
   - **Hai cách đã thử và bỏ:**
     - "Phát hiện chậm nhất 3 s trước va chạm thật": biết trước tương lai. Xe chen làn bất ngờ cũng bị coi như đã thấy trước 3 s, nên các ca bất ngờ biến mất hết.
     - "TTC kiểu radar" (khoảng cách chia tốc độ thu hẹp): báo nhầm khi vượt một xe chậm ở làn bên.
   - Báo cáo ghi rõ mỗi ca được phát hiện theo cách nào (`detected_by`).
2. **Lúc bắt đầu phanh:** `t_phanh = t_pháthiện + 1,0 s` (thời gian phản xạ).
3. **Tốc độ khi phanh với gia tốc `a`:** xe giữ đường đi đã ghi, chỉ chậm lại:

   `v(t) = min( v_ghi(t), v_ghi(t_phanh) − a·(t − t_phanh) )`, không nhỏ hơn 0.

   Công thức này liền mạch tại `t_phanh` và không bao giờ cho xe đi nhanh hơn bản ghi. Ví dụ: nếu trong bản ghi xe vốn đang chậm lại, nó vẫn chậm lại ít nhất như bản ghi.
4. **Tìm mức phanh bằng lưới:** thử `a` = 0,2; 0,4; …; 8,0 m/s² (40 giá trị). `a_cần` là giá trị **nhỏ nhất** mà hộp hai bên không chồng nhau từ `t_phanh` tới hết cảnh.
   - Không dùng chia đôi khoảng, vì ở giao lộ, phanh mạnh hơn chưa chắc tránh được. Ví dụ: phanh nhẹ để diễn viên cắt ngang qua trước thì tránh được, nhưng phanh mạnh lại dừng đúng trên đường đi của diễn viên.
   - Báo kèm: các mức lớn hơn `a_cần` có tránh được hết không. Nếu không, gắn cờ "không đơn điệu".

#### Mức độ của ca đâm

| Mức | Điều kiện | Ý nghĩa |
|---|---|---|
| **Phanh nhẹ là đủ** | `a_cần` ≤ 3,4 m/s² | giảm tốc thoải mái, chuyện thường ngày |
| **Phải phanh gấp** | 3,4 < `a_cần` ≤ 8,0 m/s² | gần giới hạn bám đường khô (≈ 0,8 g) |
| **Không tránh được bằng phanh** | không có `a` ≤ 8,0 m/s² nào tránh được, hoặc một trường hợp biên ở mục 10.5 | ví dụ bị tông từ phía sau, bị đâm ngang khi đang đứng |

### 10.5. Trường hợp biên (định nghĩa trước, không xử lý tuỳ hứng)

| Trường hợp | Xử lý |
|---|---|
| Diễn viên **xuất hiện quá muộn**: có dữ liệu chưa tới **2,0 s** trước lúc nguy hiểm nhất (lần đâm đầu tiên, hoặc lúc TTC nhỏ nhất với ca sát). Hay gặp khi dời làm mất phần đầu quỹ đạo, khiến vật thể "hiện ra ngay trước mũi xe" | Không tính vào "hiếm có giá trị". Đếm riêng là **"xuất hiện quá muộn"** |
| Đâm xảy ra **trước `t_phanh`** (không kịp phản xạ) | "Không tránh được bằng phanh", lý do `phản xạ` |
| Xe ghi hình **đang đứng** (tốc độ ghi < 0,5 m/s) tại `t_phanh` mà vẫn bị đâm | "Không tránh được bằng phanh", lý do `đang đứng`. Phanh không giúp được, và đây là lỗi của diễn viên |
| Phanh làm **đâm muộn hơn** nhưng vẫn đâm (thường là bị tông từ phía sau) | Không có `a` nào tránh được, nên "không tránh được bằng phanh" |
| Đâm nhiều lần, nhiều đoạn | Mốc tính là lần đâm đầu tiên. Một `a` chỉ tính là tránh được khi tránh được **mọi** lần |

### 10.6. Các nhóm kết quả

Mỗi biến thể **hợp lệ** rơi vào đúng một nhóm:

| Nhóm | Điều kiện | Tính vào "hiếm có giá trị"? |
|---|---|---|
| Xa | (a) = xa | Không |
| **Sát** | (a) = sát, diễn viên có mặt đủ lâu | **Có** |
| Phanh nhẹ là đủ | (a) = đâm, `a_cần` ≤ 3,4 | Không |
| **Phải phanh gấp** | (a) = đâm, 3,4 < `a_cần` ≤ 8,0, diễn viên có mặt đủ lâu | **Có** |
| Không tránh được bằng phanh | (a) = đâm, không `a` nào ≤ 8,0 tránh được, hoặc trường hợp biên | **Không**. Báo cáo thành **nhóm riêng**, có nhãn lý do (theo quyết định của chủ dự án ngày 12/10/2026) |
| Xuất hiện quá muộn | sát hoặc đâm, nhưng diễn viên có mặt < 2,0 s trước lúc nguy hiểm nhất | Không. Báo cáo riêng |

**Con số chính của "tạo tình huống hiếm"** = số **sự kiện** (mục 10.7) thuộc nhóm "sát" hoặc "phải phanh gấp", mà bản ghi thật **không có**. Số file đi kèm để tham khảo.

### 10.7. Kiểu xung đột và sự kiện

Bản nháp đầu đặt tên theo hành vi ("chen làn", "bám đuôi"…). Những tên đó khẳng định một hành vi mà ta chưa đo, nên bị bỏ. Thay vào đó, kiểu xung đột chỉ gồm hai thứ **đo trực tiếp được**:
- **loại diễn viên:** xe, xe hai bánh, người đi bộ;
- **phía của xe ghi hình** mà diễn viên ở vào lúc nguy hiểm nhất: trước, sau, trái, phải (cách chia đã dùng từ 12/10/2026, mục 8.3).

Ví dụ: "xe, phía trước" là ca `car_008` ở `scene-0061`; "người đi bộ, bên phải" là người băng qua đường từ lề phải.

**Sự kiện** = cảnh × diễn viên × kiểu xung đột. Mọi con số "hiếm" được báo theo **cả số file lẫn số sự kiện**.

### 10.8. Chỉ số 2 sau khi đổi: báo cáo gì

Cho baseline và pilot, trên cùng lưới, và cho bản ghi thật:

1. **Chuỗi lọc:** tổ hợp → viết ra (còn ≥ 2 s) → hợp lệ → sát / đâm → nhóm ở mục 10.6. Mỗi bước ghi số còn lại.
   - Lý do loại tách hai loại: **hình học** (chồng hộp với vật khác, bị cắt quá ngắn) và **động lực học** (vượt tốc độ hoặc gia tốc).
2. **Chỉ số 2 chính** ("số kịch bản hợp lệ sinh được"): số hợp lệ / số viết ra, như hiện nay.
3. **Tình huống hiếm:** theo nhóm (mục 10.6) × kiểu xung đột (mục 10.7), theo số file và số sự kiện.
   - So với bản ghi thật cùng đơn vị sự kiện.
   - Nhóm "không tránh được bằng phanh" và "xuất hiện quá muộn" báo riêng.
4. **Tiêu chí cũ đặt cạnh tiêu chí mới** trong cùng bảng, để thấy con số đổi vì đâu.
5. **Độ nhạy của ngưỡng:** đổi **từng ngưỡng một** (giữ các ngưỡng khác), đếm lại số sự kiện "hiếm có giá trị":

   | Ngưỡng | Các giá trị thử |
   |---|---|
   | Thời gian phản xạ | 0,5 / **1,0** / 1,5 / 2,5 s |
   | TTC phát hiện | 2,0 / **3,0** / 4,0 s |
   | Phanh nhẹ | 2,5 / **3,4** / 4,5 m/s² |
   | Phanh gấp tối đa | 6,0 / 7,0 / **8,0** m/s² |
   | Sát: TTC | 1,0 / **1,5** / 2,0 s |
   | Sát: khoảng cách | 0,5 / **1,0** / 1,5 m |
   | Có mặt trước xung đột | 1,0 / **2,0** / 3,0 s |

   Bước này chỉ tính lại hình học trên log đã có, không cần chạy thêm esmini.

### 10.9. Ngưỡng và nguồn

| Ngưỡng | Giá trị | Nguồn |
|---|---|---|
| Giảm tốc thoải mái (phanh nhẹ) | 3,4 m/s² | AASHTO, dùng cho tầm nhìn dừng xe (FHWA-HRT-04-091, chú thích bảng 11). Đã kiểm |
| Thời gian phản xạ | 1,0 s | **Giả định của đội** (tài xế tỉnh táo, đang chú ý). AASHTO dùng 2,5 s cho thiết kế đường, là trường hợp xấu, cùng nguồn trên. Mức 2,5 s nằm trong bảng độ nhạy |
| Sát: TTC | 1,5 s | Mặc định của SSAM (FHWA-HRT-08-051, chương 2). Đã kiểm |
| Sát: khoảng cách | 1,0 m | Giả định của đội, như hiện nay (mục 8.3) |
| TTC phát hiện | 3,0 s | Giả định của đội |
| Phanh gấp tối đa | 8,0 m/s² | Giả định của đội (≈ 0,8 g, đường khô) |
| Có mặt trước xung đột | 2,0 s | Giả định của đội: 1,0 s phản xạ cộng 1,0 s để phanh |
| Xuất hiện / biến mất giữa cảnh | không gần hơn 20 m | Đo trên dữ liệu thật (mục 10.3); chủ dự án chọn |
| Lưới mức phanh | 0,2 … 8,0 m/s², bước 0,2 | Giả định của đội. Bước chia hết 3,4 và 8,0 |
| Xe đạp | ≤ 12 m/s, ≤ 4 m/s² | Giả định của đội |
| Người đi bộ | ≤ 3,0 m/s, ≤ 3 m/s² | Giả định của đội |
| Dời thời gian | −4 … +4 s, bước 1 s | Giả định của đội |
| Dời dọc đường, người đi bộ | −4 … +4 m, bước 1 m | Giả định của đội |

### 10.10. Giới hạn (nói trước)

- **Tài xế tham chiếu chỉ phanh, không đánh lái.** Một ca "không tránh được bằng phanh" có thể tránh được nếu đánh lái.
- **Khi phanh, chỉ xét va chạm với diễn viên.** Xe phía sau xe ghi hình có thể tông vào nó khi nó phanh; trường hợp này không xét.
- **TTC tính theo giả định "giữ nguyên vận tốc"**. Ở chỗ rẽ nó có thể sai theo cả hai chiều: báo nguy hiểm khi hai xe thật ra đi theo đường cong tách nhau, hoặc bỏ sót nguy hiểm khi hai xe cùng vào cua (ví dụ ở mục 10.4b). Phần phát hiện của tài xế tham chiếu dùng thêm TTC theo đường đi để chặn chiều bỏ sót, nhưng vẫn giả định diễn viên đi thẳng, nên một diễn viên cũng đang vào cua có thể được phát hiện muộn hơn thực tế. Tiêu chí "sát" vẫn dùng TTC này, nhưng có thêm điều kiện khoảng cách < 1 m nên bắt được những lần lướt sát.
- **Va chạm kiểm theo bước 0,1 s.** Người đi bộ mỏng và tốc độ tương đối lớn nên có thể sót lần chạm rất ngắn. Việc kiểm lại trên 1–2 cảnh với bước 0,05 s **chưa làm**.
- **Mọi ngưỡng ngoài hai nguồn trên là giả định của đội.** Bảng độ nhạy cho thấy kết luận phụ thuộc vào chúng tới mức nào.
- **Ngưỡng được chọn trên chính 10 cảnh mini,** chưa có dữ liệu để riêng. Việc kiểm tra trên phần dữ liệu để riêng là bước 5 của kế hoạch.

### 10.11. Chi phí chạy lại

- **Đo thật trên `scene-0061`** (44 diễn viên, 8.184 tổ hợp mỗi cách): khoảng 335–340 s mỗi cách, tức khoảng 11 phút cho cả baseline lẫn pilot. Lượt cũ của cảnh này mất 105 s.
- Mỗi cách (baseline, pilot): 306 diễn viên × (98 + 88) = khoảng **57 nghìn tổ hợp**, gấp khoảng 3,8 lần hiện nay.
- Nhiều tổ hợp bị cắt còn dưới 2 s và không cần chạy esmini, nhất là người đi bộ.
- Phần tính mức phanh và độ nhạy là hình học trên log có sẵn, không cần chạy esmini thêm.
- Ước lượng trước khi chạy: 1–1,5 giờ. **Thực tế ngày 13/10/2026: khoảng 1,9 giờ** tính toán cho 10 cảnh. Cảnh lâu nhất là `scene-1094` (59 diễn viên, 27 phút).

### 10.12. Quyết định của chủ dự án (12/10/2026)

Sau khi xem thử `scene-0061`, chủ dự án quyết thêm hai điểm, đều cùng ngày:
- người đi bộ chạm người đi bộ vẫn hợp lệ;
- vật thể xuất hiện hoặc biến mất giữa đường, cách xe ghi hình dưới 20 m, thì biến thể không hợp lệ (mục 10.3).

Cả năm điểm dưới đây được duyệt. Lời chủ dự án: "phải phanh rất mạnh, suýt sát nữa là gây tai nạn thì sẽ tính là hiếm, còn phanh nhẹ thì nó vẫn nằm trong tính toán của con người rồi". Ngưỡng phanh mạnh được chốt là **trên 3,4 m/s²** (mức có nguồn AASHTO), không phải 5 m/s².

1. **Tách hai câu hỏi** (a) xa / sát / đâm và (b) cần phanh bao nhiêu, cùng các nhóm ở mục 10.6. "Hiếm có giá trị" = sát + phải phanh gấp.
2. **Ca "phanh nhẹ là đủ" không tính là hiếm.**
3. **Ngưỡng ở mục 10.9**, nhất là thời gian phản xạ 1,0 s (thay vì 2,5 s của AASHTO) và phanh gấp tối đa 8,0 m/s².
4. **Thêm người đi bộ và kiểu dời thời gian**, chấp nhận thời gian chạy khoảng 1–1,5 giờ.
5. **Bỏ tên hành vi** ("chen làn", "bám đuôi"…), dùng loại diễn viên × phía.

---

## Phụ lục A. Chỉ số 2 theo cách cũ (đã thay)

> Đây là cách đo chỉ số 2 từ 09/10 tới 13/10/2026: dời thời gian và đổi tốc độ cả quỹ đạo của một vật thể, không ai phản ứng. Chủ dự án đã bác bỏ vì biến thể trông giả. Giữ lại để so sánh và truy vết; số chính thức ở mục 8.

### A.1. Cách sinh biến thể

**Vật thể được chọn để biến đổi ("diễn viên"):** mỗi xe, xe hai bánh và người đi bộ đang chuyển động (không phải xe ghi hình), có nhãn ít nhất 2 s. Trên 10 cảnh mini có 306 diễn viên: 142 xe, 10 xe hai bánh, 154 người đi bộ. Trước 12/10/2026 chỉ biến đổi xe (152 diễn viên).

**Công thức:** giữ nguyên đường đi đã dựng lại của diễn viên, chỉ đổi tiến độ của nó trên đường đi đó:

`s'(t) = hệ số tốc độ × s(t) + độ dời`

Trong đó `s(t)` là quãng đường xe đã đi tới thời điểm `t`.

- **"Đổi tốc độ"** ứng với **hệ số tốc độ**, từ 0,5 đến 1,5, bước 0,1 (11 giá trị).
- **"Đổi khoảng cách"** ứng với **độ dời**, từ −10 đến +10 m, bước 2,5 m (9 giá trị), tính dọc đường đi của chính xe đó. Độ dời dương đưa xe lên trước. Đây là khoảng dời trên đường đi, không phải khoảng hở giữa hai cản xe.

Có 11 × 9 = 99 tổ hợp, bỏ tổ hợp không đổi gì nên còn 98 biến thể cho mỗi diễn viên (họ A). Với người đi bộ, độ dời là −4 … +4 m, bước 1 m. Thêm **họ B: dời thời gian** −4 … +4 s (bước 1 s) × 11 hệ số tốc độ = 88 biến thể. Tổng 186 biến thể mỗi diễn viên; chi tiết ở mục 10.3. Lưới cố định, không dùng số ngẫu nhiên, nên chạy lại luôn ra cùng kết quả. Bản đầu dùng lưới thưa hơn (5 × 5), nhưng bỏ lỡ các ca suýt va chạm.

Chỉ giữ những thời điểm mà xe vẫn nằm trên đoạn đường đi đã ghi (`0 ≤ s' ≤ chiều dài đường đi`), nên **không bịa thêm chuyển động** ra ngoài dữ liệu thật. Nếu phần còn lại ngắn hơn 2 s thì không viết kịch bản. Trường hợp này hay gặp với xe chỉ xuất hiện 2 s, hoặc xe gần như đứng yên.

**Xe ghi hình** chạy đúng như bản ghi, **giống nhau cho cả baseline lẫn pilot** (hàm `variants.method_scene`). Chỉ các vật thể khác được dựng lại theo từng cách. Trong kiểm thử thật, vị trí của xe ghi hình sẽ do phần mềm lái xe cần kiểm tra điều khiển.

> Trước ngày 12/10/2026, code dựng lại cả xe ghi hình theo từng cách. Ở `scene-0061` lúc 10 s, xe ghi hình của baseline lệch khoảng 16 m so với bản ghi, nên số tình huống hiếm của baseline trong bảng cũ là sai (xem [tài liệu soát](kiem-tra-doc-lap-2026-10-12.md), mục 1.1).

**Vật thể chỉ có mặt trong thời gian có dữ liệu.** Trong file `.xosc`, vật thể xuất hiện 0,1 s trước mốc dữ liệu đầu tiên (`AddEntityAction`) và biến mất 0,1 s sau mốc cuối (`DeleteEntityAction`). Biến thể bị cắt ngắn cũng biến mất khi hết dữ liệu, không đứng lại giữa đường. Khoảng 0,1 s là để esmini (bước 0,05 s) ghi được cả mốc đầu lẫn mốc cuối. Đã kiểm trên esmini 3.9.0: sai số `exact` không đổi.

### A.2. Điều kiện hợp lệ

**Cách phát lại để kiểm tra:**
- Mỗi biến thể được esmini phát lại, nhưng chỉ với **xe bị biến đổi và xe ghi hình**.
- Mọi vật thể khác giống hệt kịch bản gốc, nên chuyển động của chúng lấy từ **một** lượt phát lại đầy đủ của kịch bản gốc. Ở chế độ `position`, esmini đặt vật thể đúng chỗ được giao, đã kiểm bằng sai số `exact` ≈ 0.
- Biến thể nào được **giữ làm sản phẩm** (mặc định là các biến thể hiếm) thì được viết thành file `.xosc` đầy đủ mọi vật thể, rồi cho esmini **phát lại toàn bộ thêm một lần**. Nếu lượt này lỗi thì biến thể **không còn hợp lệ** (lý do `full_replay`), và file bị xoá.
- Các biến thể hợp lệ còn lại tái tạo được bất cứ lúc nào, vì lưới cố định: chạy lệnh `variants --keep valid`.

Mọi điều kiện dưới đây tính trên log esmini, chỉ xét trong khoảng thời gian mỗi vật thể có mặt. Ngưỡng do đội đặt, đã chốt ngày 12/10/2026 (mục 9 và 10.9).

**Phạm vi của chữ "hợp lệ":** các điều kiện chỉ xét **diễn viên** (vật thể bị biến đổi). Những vật thể giữ nguyên có thể có chuyển động phi lý do nhãn rung, nhưng không làm biến thể mất hợp lệ. Nói chính xác, chỉ số 2 đếm số kịch bản **hợp lệ đối với vật thể bị biến đổi**.

1. esmini chạy hết kịch bản, mã thoát 0, và **log đủ dữ liệu**: có mọi vật thể, phủ hết khoảng thời gian có dữ liệu của từng vật thể, không có giá trị NaN. Thiếu thì lượt đó bị loại (lý do `log_incomplete`), không chấm tiếp.
2. Tốc độ lớn nhất và độ lớn gia tốc không vượt giới hạn theo loại: xe và xe máy ≤ 40 m/s và ≤ **8 m/s²** (khoảng 0,8 g); xe đạp ≤ 12 m/s và ≤ 4 m/s²; người đi bộ ≤ 3,0 m/s và ≤ 3 m/s². Gia tốc gồm cả gia tốc dọc lẫn gia tốc ngang khi vào cua, tính trên lưới 0,1 s. Trước 12/10/2026, xe đạp và xe máy đã được biến đổi nhưng dùng ngưỡng của ô tô.
3. Hộp của diễn viên không chồng lên hộp của bất kỳ vật thể nào **khác xe ghi hình**. Va chạm giữa hai xe đều không phản ứng (ví dụ xe sau không phanh) là phi lý ngoài đời, nên bị loại. Riêng **người đi bộ chạm người đi bộ** thì không loại (họ tự nhường nhau), mà được đếm riêng (mục 10.3).
   - **Ngoại lệ:** bỏ qua những lần chồng hộp xảy ra **đúng vào thời điểm** (lệch tối đa 0,1 s) mà **bản ghi thật** cũng chồng hộp với cùng vật đó. Hộp nhãn có thể chồng nhau do sai số gán nhãn.
   - Mốc "bản ghi thật" là lượt phát lại `exact` của cảnh, **dùng chung cho baseline và pilot**. Trước 12/10/2026, mốc này lấy từ bản đã dựng lại của từng cách, nên một lần chồng hộp do chính bước dựng lại gây ra cũng được miễn.
   - **Luật cũ và lý do bỏ:** bản đầu miễn **mọi** va chạm với vật đã từng chồng hộp trong bản gốc. Luật này có lợi không công bằng cho baseline. Ví dụ ở scene-0757: nhãn thô rung khiến `car_001` chạm nhẹ vào `truck_002` đang chạy trước, nên baseline được miễn toàn bộ 43 va chạm sau đó giữa hai xe, còn pilot (đã làm mượt) thì không.
4. Diễn viên **không xuất hiện hay biến mất giữa đường**: không hiện ra sau đầu cảnh, hay biến mất trước cuối cảnh, khi cách xe ghi hình dưới 20 m (lý do `pop_in` / `pop_out`, mục 10.3).
5. Chồng lên **xe ghi hình** thì vẫn hợp lệ, nhưng được xếp nhóm theo tiêu chí ở mục 10. Đó là tình huống phần mềm lái xe phải tự tránh.

**Xe có nằm trên mặt đường không:** điều kiện này không được dùng để loại. Biến thể không đi ra chỗ mới ngoài đường đi đã ghi; tỷ lệ nằm trên đường được đo và báo cáo cho xe thật (xem mục 2.1).

### A.3. Độ hiếm, phiên bản 1 (vẫn báo để so sánh)

> Tiêu chí chính từ 12/10/2026 là **phiên bản 2** ở mục 10. Phiên bản 1 dưới đây vẫn được tính và đặt cạnh, để thấy con số đổi vì đâu.

Đo **TTC** (thời gian còn lại trước va chạm): giả sử cả hai xe giữ nguyên vận tốc hiện tại, sau bao lâu thì hai hộp chạm nhau, xét trong tối đa 5 s phía trước. Nếu hai hộp đang chồng nhau thì TTC = 0.

Một biến thể hợp lệ được tính là **hiếm** khi thoả một trong hai điều kiện (đề xuất):
- TTC nhỏ nhất tới xe ghi hình < **1,5 s**;
- **hoặc** khoảng cách sát nhất giữa hai hộp < **1,0 m**.

Cần điều kiện thứ hai vì khi hai xe chạy nối đuôi cùng tốc độ, TTC theo cách tính "giữ nguyên vận tốc" ra vô cùng, dù hai xe chỉ cách nhau dưới 1 m. Ví dụ đã gặp ở scene-0061: biến thể `car_008` cách xe ghi hình 0,89 m mà TTC = ∞.

Báo cáo tách riêng hai loại:
- **suýt va chạm:** hộp của xe bị biến đổi **không lúc nào** chồng lên hộp xe ghi hình (kể cả những thời điểm bản ghi thật cũng chồng hộp);
- **va chạm với xe ghi hình:** có chồng hộp.

**Đếm theo sự kiện.** Nhiều biến thể của cùng một xe thường chỉ là một tình huống (ví dụ `car_008` chạy 50%, 60%, 70% tốc độ đều bị xe ghi hình tông đuôi). Vì vậy, bên cạnh số file, báo cáo đếm **số sự kiện khác nhau**. Một sự kiện là một cặp:
- xe bị biến đổi;
- phía của xe ghi hình mà xe đó ở vào lúc nguy hiểm nhất (TTC nhỏ nhất, rồi khoảng cách nhỏ nhất): trước, sau, trái hoặc phải, chia theo góc 45° và 135° so với hướng xe ghi hình.

Từ phiên bản 2, kiểu xung đột gồm cả loại diễn viên: xe, xe hai bánh, người đi bộ × phía (mục 10.7).

**So với dữ liệu thật, cùng đơn vị:** cùng tiêu chí được áp lên **bản ghi thật** (phát lại `exact`), đếm theo sự kiện. "Sự kiện hiếm mới" là sự kiện hiếm của biến thể mà bản ghi thật không có, tức không cùng xe và cùng phía.

### A.4. Kết quả trên 10 scene nuScenes mini

**Lượt chạy:** 13/10/2026, commit `923feef`, esmini v3.9.0, cả 10 cảnh và cả hai cách trong một lượt. Mọi kết quả ghi khối `run` (commit, phiên bản esmini, cấu hình), và lệnh `report` xác nhận chúng đến từ **một** lượt duy nhất. Tiêu chí hiếm là phiên bản 2 (mục 10).
- Mọi lượt esmini thoát mã 0. Log có đủ mọi vật thể; sai số `exact` vẫn ≤ 0,001 m (trung bình) ở mọi cảnh.
- 306 diễn viên × 186 biến thể = 56.916 tổ hợp cho mỗi cách. Số **viết ra** là số tổ hợp còn đủ 2 s trên đường đi đã ghi.
- 212 kịch bản hiếm có giá trị (baseline 118, pilot 94) được viết thành file đầy đủ và phát lại toàn bộ thêm một lần: **0 lượt lỗi**.
- Thời gian tính toán khoảng 1,9 giờ (lượt cũ khoảng 20 phút, chỉ có xe và họ A).

**Chỉ số 2 và tình huống hiếm theo cảnh.** Cột "hiếm có giá trị" ghi *số file / số sự kiện / số sự kiện mới* (không có trong bản ghi thật). Cột "tiêu chí cũ" ghi *số file / số sự kiện* theo phiên bản 1.

| scene | diễn viên | baseline hợp lệ / viết ra | pilot hợp lệ / viết ra | hiếm có giá trị, baseline | hiếm có giá trị, pilot | bản ghi thật | tiêu chí cũ, baseline | tiêu chí cũ, pilot |
|---|---|---|---|---|---|---|---|---|
| scene-0061 | 44 | 5923/7487 (79,1%) | 6154/7484 (82,2%) | 31 / 3 / 3 | 10 / 3 / 3 | 0 | 71 / 3 | 55 / 3 |
| scene-0103 | 38 | 3262/6574 (49,6%) | 3828/6548 (58,5%) | 1 / 1 / 1 | 0 / 0 / 0 | 0 | 4 / 2 | 11 / 2 |
| scene-0553 | 25 | 1316/4591 (28,7%) | 2079/4575 (45,4%) | 0 / 0 / 0 | 0 / 0 / 0 | 0 | 0 / 0 | 0 / 0 |
| scene-0655 | 10 | 1131/1663 (68,0%) | 1233/1636 (75,4%) | 4 / 1 / 1 | 3 / 2 / 2 | 0 | 26 / 3 | 26 / 4 |
| scene-0757 | 18 | 1286/3186 (40,4%) | 1189/3179 (37,4%) | 0 / 0 / 0 | 19 / 2 / 1 | 1 | 0 / 0 | 20 / 3 |
| scene-0796 | 32 | 2905/5606 (51,8%) | 3482/5581 (62,4%) | 24 / 2 / 2 | 25 / 3 / 3 | 0 | 76 / 5 | 79 / 5 |
| scene-0916 | 10 | 740/1667 (44,4%) | 762/1619 (47,1%) | 0 / 0 / 0 | 0 / 0 / 0 | 0 | 0 / 0 | 6 / 1 |
| scene-1077 | 48 | 2743/7885 (34,8%) | 3402/7880 (43,2%) | 1 / 1 / 1 | 0 / 0 / 0 | 0 | 35 / 1 | 34 / 1 |
| scene-1094 | 59 | 3614/10532 (34,3%) | 6495/10495 (61,9%) | 5 / 2 / 2 | 9 / 2 / 2 | 0 | 62 / 4 | 61 / 4 |
| scene-1100 | 22 | 1682/3886 (43,3%) | 1978/3878 (51,0%) | 52 / 3 / 1 | 28 / 3 / 1 | 2 | 125 / 5 | 50 / 4 |
| **Tổng** | **306** | **24602/53077 (46,4%)** | **30602/52875 (57,9%)** | **118 / 13 / 11** | **94 / 15 / 12** | **3** | 399 / 23 | 342 / 27 |

**Tỷ lệ hợp lệ theo loại diễn viên:**

| loại | baseline | pilot |
|---|---|---|
| xe | 9532/24036 (39,7%) | 11633/23886 (48,7%) |
| xe hai bánh | 975/1751 (55,7%) | 1012/1752 (57,8%) |
| người đi bộ | 14095/27290 (51,6%) | 17957/27237 (65,9%) |

**Lý do loại** (một biến thể có thể có nhiều lý do):

| lý do | baseline | pilot |
|---|---|---|
| vượt gia tốc | 12.331 | 3.743 |
| vượt tốc độ | 31 | 121 |
| chồng hộp với vật khác | 10.498 | 9.325 |
| xuất hiện giữa đường (`pop_in`) | 5.913 | 5.989 |
| biến mất giữa đường (`pop_out`) | 6.780 | 6.821 |
| còn dưới 2 s, không viết ra | 3.839 | 4.041 |

**Các nhóm của tiêu chí phiên bản 2** (số file, trong ngoặc là số sự kiện):

| nhóm | baseline | pilot |
|---|---|---|
| xa | 24.203 (456) | 30.260 (469) |
| **sát** | 118 (13) | 94 (15) |
| phanh nhẹ là đủ | 100 (6) | 111 (5) |
| **phải phanh gấp** | 0 (0) | 0 (0) |
| không tránh được bằng phanh | 46 (3) | 52 (4) |
| xuất hiện quá muộn | 135 (12) | 85 (14) |

Sự kiện hiếm có giá trị mới của pilot, theo kiểu: xe phía trước 4, xe phía sau 3, người đi bộ phía trước 2, người đi bộ bên trái 2, người đi bộ phía sau 1.

**Diễn giải:**
- **Chỉ số 2, baseline → pilot:** số kịch bản hợp lệ tăng từ 24.602 lên **30.602**; tỷ lệ hợp lệ trên số viết ra tăng từ 46,4% lên **57,9%**.
  - Pilot tốt hơn ở **9/10 cảnh**. Riêng `scene-0757` pilot thấp hơn một chút (37,4% so với 40,4%); cảnh này có nhiều xe chạy nối đuôi sát nhau.
  - Khác biệt chính đến từ gia tốc: baseline nối thẳng các nhãn rung nên tạo gia tốc giả, 12.331 biến thể bị loại vì gia tốc; pilot chỉ còn 3.743.
- **"Tạo tình huống hiếm":** cùng tiêu chí, 10 cảnh thật có **3** sự kiện hiếm có giá trị; bộ biến thể pilot tạo thêm **12 sự kiện mới** (baseline 11). Số này nhỏ nên chênh lệch baseline/pilot ở đây không có ý nghĩa thống kê. Đây là số đếm sản phẩm, không phải thước đo chất lượng của cách dựng.
- **Nhóm "phải phanh gấp" trống ở cả 10 cảnh.** Đây là hệ quả của chính tiêu chí, không phải lỗi.
  - Tài xế tham chiếu phát hiện khi TTC < 3 s và phản xạ 1 s. Nếu khoảng cách thu hẹp đều, mức phanh cần khoảng *tốc độ tiếp cận ÷ 4*. Muốn vượt 3,4 m/s² thì hai bên phải lao vào nhau nhanh hơn khoảng 13,6 m/s (≈ 49 km/h), hiếm gặp trong phố.
  - Vì vậy các ca đâm chia thành "phanh nhẹ là đủ" (thay đổi đều, thấy trước được) hoặc "không tránh được / xuất hiện quá muộn" (bất ngờ).
  - Mọi tình huống hiếm có giá trị hiện đều thuộc nhóm "sát". Bảng độ nhạy (bên dưới) cho thấy đổi ngưỡng phanh hay phản xạ cũng không tạo ra ca "phải phanh gấp" nào.
- **So với bảng cũ** (trước 12/10/2026: hợp lệ 56,5% → 65,9%; 494 tình huống hiếm):
  - con số cũ đếm **file**, và 494 file chỉ đến từ 15 cặp cảnh–xe;
  - baseline cũ bị chấm với xe ghi hình lệch tới 16 m;
  - bảng mới có thêm người đi bộ, thêm dời thời gian, và luật "không xuất hiện giữa đường". Riêng luật này loại khoảng 12.700 biến thể mỗi cách, và là lý do lớn nhất khiến tỷ lệ hợp lệ thấp hơn bảng cũ.

**Độ nhạy:** số sự kiện hiếm có giá trị mới khi đổi **từng** ngưỡng, giữ các ngưỡng khác. Chỉ tính lại trên log có sẵn.

| ngưỡng | giá trị thử (in đậm: đã chọn) | baseline | pilot |
|---|---|---|---|
| thời gian phản xạ | 0,5 / **1,0** / 1,5 / 2,5 s | 11 / **11** / 11 / 11 | 12 / **12** / 14 / 13 |
| TTC phát hiện | 2 / **3** / 4 s | 12 / **11** / 11 | 14 / **12** / 12 |
| phanh nhẹ tối đa | 2,5 / **3,4** / 4,5 m/s² | 11 / **11** / 11 | 12 / **12** / 12 |
| phanh gấp tối đa | 6 / 7 / **8** m/s² | 11 / 11 / **11** | 12 / 12 / **12** |
| sát: TTC | 1,0 / **1,5** / 2,0 s | 10 / **11** / 12 | 12 / **12** / 15 |
| sát: khoảng cách | 0,5 / **1,0** / 1,5 m | 7 / **11** / 16 | 5 / **12** / 16 |
| có mặt trước xung đột | 1 / **2** / 3 s | 12 / **11** / 11 | 12 / **12** / 11 |

Kết luận phụ thuộc nhiều nhất vào **ngưỡng khoảng cách của "sát"** (1,0 m, giả định của đội): đổi sang 0,5 m thì pilot còn 5 sự kiện mới, sang 1,5 m thì có 16. Các ngưỡng phanh và phản xạ gần như không làm đổi kết quả.

**Hạn chế:**
- Xe ghi hình không phản ứng, nên "đâm" nghĩa là **tình huống phần mềm lái xe phải tự xử lý**, chưa phải va chạm đã xảy ra. Mức phanh cần thiết là của tài xế tham chiếu chỉ biết phanh (mục 10.4).
- Dữ liệu là 10 cảnh mini, phần lớn trong phố, xe chạy chậm. Chưa có cảnh đường cao tốc, nơi nhóm "phải phanh gấp" có thể xuất hiện.
- Thư mục `out/nuscenes-mini/` chiếm khoảng 680 MB.

**Ảnh động** (scene-0061, pilot), mỗi nhóm một ca, làm bằng `tools/reviews/render_variant.py`. Xanh là xe ghi hình, hồng tím là diễn viên. Các file nằm trong `out/viz/v2/`:
- `close_pedestrian_022.gif`, `close_pedestrian_043.gif`: sát;
- `mild_car_008.gif`: phanh nhẹ là đủ;
- `unavoidable_pedestrian_043.gif`: không tránh được bằng phanh.

Các ảnh trong `out/viz/` (ngoài `v2/`) làm theo tiêu chí cũ, chỉ để tham khảo.
