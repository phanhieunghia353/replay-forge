# Thiết kế lại: kịch bản theo hành vi, chân thật

> **Trạng thái (13/10/2026):** chủ dự án duyệt **giai đoạn 1** và cách so sánh chỉ số 2 (mục 5). Các giai đoạn sau làm từng bước, mỗi bước dừng cho chủ dự án xem.
>
> **Lịch sử:**
> - Bản nháp đầu đề xuất "mọi vật thể do người lái mô phỏng điều khiển". Một lượt soát độc lập phản biện; từng ý được kiểm lại bằng code và dữ liệu (`tools/reviews/2026-10-13/`).
> - Bản nháp có lỗi cấu trúc, nên được thay bằng bản này. Các lỗi chính ở mục 2.

## 0. Yêu cầu

Chủ dự án, sau khi xem app và ảnh động:
- **Phê bình:** "mọi thứ chạy đều đều trông rất giả", "vật thể cứ tự dưng xuất hiện", "lựa chọn tốc độ chẳng có gì khác biệt", "bỏ mặc việc va chạm với xe ngay trước nó", "mọi thứ code cứng với các tình huống này".
- **Yêu cầu:** kịch bản **chân thật, có dừng và giảm tốc độ, mô phỏng sát đời thật nhất; kể cả khi thay đổi vẫn phải tuân theo vật lý và cách xử lý của con người.**

## 1. Lỗi gốc của cách cũ (đã đo)

| # | Phê bình | Nguyên nhân gốc | Bằng chứng |
|---|---|---|---|
| 1 | Chạy đều đều, đổi tốc độ chẳng khác gì | Biến thể = nhân cả hồ sơ tốc độ của một vật thể với một hệ số, từ đầu tới cuối cảnh; không có "sự kiện" | 44 biến thể của `car_008` (scene-0061) chỉ là 1 sự kiện |
| 2 | Bỏ mặc xe ngay trước nó | Mọi vật thể phát lại cứng, không ai phản ứng; luật hợp lệ chỉ loại khi hai hộp chồng hẳn lên nhau | `scene-0757`: biến thể "hợp lệ" có lúc cách xe khác < 0,5 m ở 26% số ca (xe thật 12%), < 0,2 m ở 12% |
| 3 | Tự dưng xuất hiện | Vật thể chỉ tồn tại khi nuScenes có nhãn, mà có nhãn hay không tuỳ cảm biến thấy hay không | Xe bắt đầu có nhãn ở cách xe ghi hình 18–100+ m (trung vị 63 m) |
| 4 | Code cứng | Biến thể chỉ là tua lại quỹ đạo đã ghi, không mô tả được sự kiện mới; nhiều ngưỡng chọn khi nhìn chính 10 cảnh | |

**Số liệu người thật trong 10 cảnh mini** (từ quỹ đạo đã làm mượt; nhãn 2 Hz nên không đo được lúc bắt đầu phanh hay độ giật):

| | Tốc độ trung vị | Tăng tốc p95 | Giảm tốc p95 / p99 | Giảm tốc lớn nhất | Có dừng rồi chạy |
|---|---|---|---|---|---|
| Xe (140 quỹ đạo) | 7,5 m/s | 1,3 m/s² | 1,4 / 2,8 m/s² | 8,3 m/s² (chưa kiểm là thật hay do nhãn) | 22 |
| Người đi bộ (152) | 1,3 m/s | 0,2 m/s² | 0,2 / 0,4 m/s² | 1,2 m/s² | 0 |

## 2. Bản nháp đầu sai ở đâu (đã kiểm)

1. **Cho người lái mô phỏng điều khiển mọi xe thì "không đổi gì" không còn giống cảnh thật.** Tốc độ đã ghi vốn đã gồm việc bám xe và nhường đường; mô hình làm lại việc đó lần nữa. Ví dụ tính tay: hai xe chạy đều 7,5 m/s cách 20 m, mô hình IDM vẫn bắt xe sau phanh 0,45 m/s².
2. **Kế hoạch tốc độ theo vị trí làm xe dừng mãi** ở chỗ nó đã dừng trong bản ghi.
3. **Đường đi cố định + đổi thời điểm** làm xe chen làn có thể dừng giữa hai làn.
4. **File phát lại cứng không giữ độ êm.** esmini 3.9.0 giữ tốc độ không đổi trên mỗi đoạn giữa hai điểm, nên ở mỗi điểm tốc độ nhảy bậc. Đo ở `car_008`: gia tốc tính từ log esmini lên tới 1,39 m/s², quỹ đạo đưa vào chỉ 0,68 m/s².
5. **Vùng quan tâm di chuyển theo xe ghi hình** làm biến mất những xe vẫn còn tồn tại, ví dụ xe đỗ hay xe ngay phía trước một xe khác.
6. **Người đi bộ và xe có thể nhường nhau mãi.** Khe hở 3 s không đủ: qua 7 m đường với tốc độ 1,3 m/s mất 5,4 s.
7. **"Phải phanh gấp" đo từ lựa chọn của mô hình** không phải là mức phanh tối thiểu cần thiết.
8. **Sai về dữ liệu:**
   - bản đồ nuScenes **có** liên kết làn (2.846 mục ở boston-seaport), 775 vạch dừng có loại (đèn, biển dừng, vạch qua đường) và 307 vị trí đèn; chỉ không có màu đèn theo thời gian;
   - nuScenes **có** nhãn trạng thái: xe đỗ / đang chạy / đang dừng; người đi / đứng / ngồi; xe đạp có hoặc không người.

## 3. Nguyên tắc

- **Không đổi gì thì đúng như thật, bằng cách xây dựng:** mọi vật thể không bị ảnh hưởng **phát lại** chuyển động `pilot` của nó (đã đo: ADE 0,098 m). Xe ghi hình phát lại bản ghi.
- **Chỉ những ai bị ảnh hưởng mới phản ứng**, và phản ứng như người: có thời gian phản xạ, giữ khoảng cách, phanh và tăng tốc trong giới hạn.
- **Cái gì chưa mô phỏng được thì nói "chưa hỗ trợ" và không đếm**, không làm ra cảnh giả.
- **Mọi ngưỡng chốt trước khi chạy**; số liệu chọn trên chính 10 cảnh này được ghi là "thăm dò".

## 4. Giai đoạn 1: xe phía trước giảm tốc hoặc dừng, xe phía sau phản ứng

### 4.1. Vai trò

| Vai | Ai | Chuyển động |
|---|---|---|
| Xe gây sự kiện | một xe đang chạy (> 3 m/s), có ít nhất một xe bám theo nó | sự kiện có tham số (mục 4.3), sau đó quay về chuyển động của mình nhưng trễ đi |
| Xe phản ứng | xe bám theo xe gây sự kiện, xe bám theo những xe đó, và cứ thế lan ra sau; có thể gồm xe ghi hình | phát lại cho tới khi "thấy" xe trước khác đi, rồi lái như người (mục 4.4) |
| Xe đỗ | nhãn `vehicle.parked` chiếm đa số, hoặc đứng yên | đứng yên |
| Mọi vật thể khác (kể cả người đi bộ) | | phát lại `pilot`, là vật cản cố định với những người phản ứng |

**"Bám theo" nghĩa là** tại thời điểm đó, xe B là vật thể gần nhất **phía trước** xe A trên **hành lang đường đi** của A:
- khoảng lệch ngang tới đường đi của A nhỏ hơn nửa tổng bề rộng hai xe cộng 0,5 m;
- hướng chạy lệch nhau dưới 30°;
- cách nhau (từ cản trước của A tới cản sau của B) không quá 60 m.

Quan hệ phải giữ ít nhất 1 s mới được tính; đổi xe trước cần qua một ngưỡng trễ, để không nhảy qua lại liên tục. Hành lang chỉ xét đoạn đường đi gần vị trí hiện tại, để khỏi chiếu nhầm sang nhánh khác.

### 4.2. Đồng hồ "kế hoạch" của mỗi xe

Mỗi xe có chuyển động danh nghĩa `s_kh(t)`: quãng đường đã đi dọc đường đi của nó, lấy từ `pilot` (riêng xe ghi hình là bản ghi). Khi bị chậm lại, xe giữ một **đồng hồ kế hoạch τ**: "lúc này tôi đang ở giai đoạn nào của chuyển động gốc".
- Chưa bị ảnh hưởng: τ = t, và xe ở đúng `s_kh(t)`.
- Đang ở trên một đoạn chạy của kế hoạch: τ là thời điểm mà `s_kh(τ)` bằng vị trí hiện tại.
- Tới một **chỗ dừng của kế hoạch** (bản ghi đứng yên ≥ 1 s ở vị trí s*, từ τ₁ tới τ₂): xe dừng tại s*, rồi τ chạy theo giờ từ τ₁ tới τ₂. Tức là **giữ đúng thời gian chờ**; giờ đi trễ đúng bằng độ trễ của xe.
  - Đây là một giả định (coi như chờ một khoảng cố định). Giai đoạn 2 sẽ dùng loại vạch dừng của bản đồ (đèn hay biển dừng) để làm đúng hơn.
- **Tốc độ mong muốn** = `v_kh(τ)`, tức tốc độ của chuyển động gốc ở giai đoạn tương ứng. Xe không bao giờ cố đuổi cho kịp giờ cũ.
- Khi xe đã theo đúng kế hoạch với một độ trễ không đổi (lệch vị trí < 0,1 m, lệch tốc độ < 0,1 m/s trong 2 s) và không còn bị xe trước cản, xe **quay lại phát lại** chuyển động gốc trễ đi đúng độ trễ đó: `s(t) = s_kh(t − Δ)`.

### 4.3. Sự kiện (tham số chốt trước khi chạy)

Xe gây sự kiện, từ thời điểm t₀:
1. **Bắt đầu phanh êm:** gia tốc giảm dần với độ giật j = 10 m/s³ (giả định, sẽ báo độ nhạy) tới mức giảm tốc **a_sk**.
2. **Giảm tốc** tới tốc độ đích: **dừng hẳn**, hoặc **còn 50%** tốc độ lúc t₀.
3. **Nếu dừng:** đứng **D** giây. Khoảng chờ tính từ lúc thật sự đứng yên.
4. **Chạy lại:** tăng tốc êm (1,5 m/s², độ giật 3 m/s³) cho tới tốc độ kế hoạch, rồi theo đồng hồ kế hoạch như mục 4.2.

| Tham số | Các giá trị | Ghi chú |
|---|---|---|
| t₀ | mỗi 2 s trong lúc xe chạy > 3 m/s và có xe bám theo | |
| a_sk | 2, 4, 6, 8 m/s² | dữ liệu thật: p99 2,8 m/s². Mức 6–8 là phanh khẩn cấp, chính là chỗ tạo tình huống hiếm; báo riêng số biến thể dùng mức này |
| Đích | dừng hẳn; còn 50% | |
| D (khi dừng) | 0, 3 s | |

Mỗi xe gây sự kiện có tối đa (số mốc t₀) × 4 × 3 biến thể. Phải đủ thời gian trong cảnh: còn ít nhất 4 s sau khi sự kiện kết thúc, không thì không chạy.

### 4.4. Người lái phản ứng

- **Phát hiện:** xe phản ứng nhận ra xe trước "khác đi" khi xe trước lệch khỏi chuyển động gốc của nó: chậm hơn 0,3 m/s, hoặc tụt sau 0,2 m. Cả hai điều kiện đều có thể là do xe trước của nó cũng đang phản ứng.
- **Phản xạ:** sau **τ_r = 1,0 s** kể từ lúc phát hiện, người lái chuyển sang tự lái (nhất quán với tiêu chí hiếm v2). Trong lúc phản xạ, xe vẫn đi theo kế hoạch.
- **Tự lái:** mô hình bám xe **IDM** (Treiber và cộng sự, 2000), dùng trạng thái hiện tại của xe trước:

  gia tốc = a·[1 − (v/v₀)⁴ − (s*/g)²],  với s* = s₀ + v·T + v·Δv / (2·√(a·b))

  - `g`: khoảng cách cản trước tới cản sau, đo dọc đường đi;
  - `v₀`: tốc độ mong muốn = `v_kh(τ)`, tối thiểu 1 m/s; chỗ dừng của kế hoạch được xử lý như một vật cản đứng yên ảo tại s*;
  - a = 1,5 m/s², b = 2,0 m/s².
- **Tham số riêng của từng xe**, đo từ chính bản ghi của nó (để xe bám sát trong thật thì cũng bám sát trong mô phỏng):
  - `T` = trung vị thời gian bám theo (khoảng cách ÷ tốc độ) khi xe đó đang bám ổn định ở > 3 m/s, kẹp trong 0,6–2,5 s; không có dữ liệu thì 1,2 s;
  - `s₀` = khoảng cách nhỏ nhất khi cả hai đứng, kẹp trong 1,0–3,0 m; không có dữ liệu thì 2,0 m.
- **Giới hạn:**
  - giảm tốc tối đa 8 m/s²; xe buýt, xe tải 5 m/s² (mục 4.10);
  - độ giật tối đa 10 m/s³ khi phanh gấp, 3 m/s³ khi chạy bình thường (giả định); đang tăng tốc mà cần phanh thì nhả ga ngay, phanh tăng dần từ 0 (mục 4.10);
  - tốc độ không âm; dừng được tính chính xác trong một bước, không để xe trượt quá chỗ dừng hay lùi lại.
- **Cập nhật đồng thời:** mọi xe tính gia tốc từ cùng một trạng thái ở bước trước, nên thứ tự duyệt không ảnh hưởng kết quả. Bước 0,05 s, bằng bước của esmini; kiểm lại một số ca với 0,025 s.
- **Xe ghi hình** dùng đúng mô hình này, với chuyển động gốc là bản ghi. Đó là người lái tham chiếu.

### 4.5. Chưa hỗ trợ (loại, có ghi lý do, không đếm)

- Một xe phản ứng (bị trễ) chồng hộp với một vật thể **không phản ứng**, ví dụ xe cắt ngang ở giao lộ hay người đi bộ: tương tác này nằm ngoài giai đoạn 1.
- Xe gây sự kiện hay xe phản ứng đi hết đường đi đã ghi trước khi cảnh kết thúc: không bịa thêm đoạn đường, cũng không cho biến mất giữa đường.
- Sự kiện cần đánh lái hoặc đổi làn mới tránh được.

### 4.6. Hợp lệ (bộ kiểm chung, chốt trước, dùng cho cả baseline lẫn pilot)

1. esmini phát lại file xuất ra: mã thoát 0, log đủ mọi vật thể trong thời gian có mặt.
2. **Vật lý** của mọi xe có chuyển động khác bản gốc:
   - tốc độ ≤ giới hạn theo loại;
   - tăng tốc ≤ 4 m/s², giảm tốc ≤ 8 m/s² (đo trên chuyển động mô phỏng).
   - Độ giật và gia tốc đo trên **log esmini** được báo riêng, không dùng để loại, vì esmini làm tốc độ nhảy bậc (mục 2.4).
3. **Không chồng hộp** giữa hai vật thể bất kỳ không phải xe ghi hình.
   - Kiểm mỗi 0,05 s; khi hai hộp cách nhau < 2 m thì kiểm dày hơn, mỗi 0,01 s.
   - Chồng hộp có sẵn trong bản ghi chỉ được miễn **đúng khoảng thời gian đó, với đúng cặp đó**, không sâu hơn bản ghi quá 0,1 m.
4. **Không bám sát phi lý:** giữa hai xe không phải xe ghi hình, khoảng cách cản < 0,5 m khi xe sau đang chạy > 3 m/s, kéo dài quá 0,5 s, thì không hợp lệ.
   - Luật này loại đúng hiện tượng "dính đuôi" mà cách cũ cho qua, nhưng không loại những khoảnh khắc ngắn.
5. Không thuộc các trường hợp "chưa hỗ trợ" ở mục 4.5.

### 4.7. Tình huống hiếm (đo trên xe ghi hình)

Thứ tự ưu tiên khi một biến thể thuộc nhiều nhóm: va chạm → phải phanh gấp → sát → phanh nhẹ → xa.

| Nhóm | Điều kiện | Hiếm có giá trị? |
|---|---|---|
| Va chạm với người lái tham chiếu | xe ghi hình chồng hộp với vật thể khác dù đã phản ứng như mục 4.4 | không, báo riêng. Không có nghĩa "không thể tránh", vì người lái tham chiếu chỉ biết phanh |
| Phải phanh gấp | mức phanh **tối thiểu cần thiết** > 3,4 m/s² (tính riêng như tiêu chí v2: lưới 0,2–8,0 m/s², bắt đầu phanh sau thời gian phản xạ) | có |
| Sát | không chạm, nhưng có lúc cách < 1 m hoặc TTC < 1,5 s | có |
| Phanh nhẹ | xe ghi hình phải phản ứng, mức tối thiểu cần ≤ 3,4 m/s² | không |
| Xa | xe ghi hình không cần phản ứng | không |

Báo kèm mức phanh mà người lái tham chiếu **đã dùng**. Nó có thể lớn hơn mức tối thiểu cần thiết.

**Đếm theo cuộc chạm trán:** xe gây sự kiện × khung thời gian t₀ × đích (dừng / 50%). Mỗi cuộc chạm trán báo số biến thể và khoảng kết quả (mức phanh, khoảng cách nhỏ nhất), để "44 biến thể = 1 sự kiện" hiện rõ.

### 4.8. Xuất OpenSCENARIO

- Mỗi biến thể hợp lệ thành một file `.xosc` cụ thể: mọi vật thể đi theo quỹ đạo, với điểm mỗi 0,05 s cho các xe có chuyển động khác bản gốc.
- `ParameterDeclarations` ghi loại sự kiện và giá trị tham số. Đây chỉ là **thông tin truy lại**: đổi giá trị trong file không làm thay đổi chuyển động. Muốn đổi thì sinh lại bằng tool.
- Kèm một file mô tả (JSON) cho mỗi cảnh: các cuộc chạm trán, tham số, kết quả, và trạng thái hợp lệ của từng biến thể.
- **Giới hạn:** trong file giao đi, các xe khác là quỹ đạo đã tính sẵn, nên không phản ứng nếu phần mềm của khách hàng lái khác người lái tham chiếu.

### 4.9. Điều chỉnh khi làm thật (13/10/2026, thử trên `scene-0061` và `scene-0757`)

Mỗi điều chỉnh dưới đây sửa một lỗi tìm thấy khi chạy thật, có số liệu kèm theo.

1. **"Xe phía trước" xét theo hình hộp, không theo tâm.** Một xe buýt dài 13,8 m đang rẽ chắn ngang đường, tâm lệch 6 m sang bên, nên không được nhận ra; `car_007` đâm vào. Giờ xét các điểm trên viền hộp nằm trong dải đường đi.
2. **Vật đi song song không phải xe phía trước.** Một xe đạp chạy bên cạnh `car_009` được coi là xe trước, nên `car_009` không thấy chiếc xe tải phanh ngay trước mặt. Giờ chỉ tính vật nằm hẳn phía trước mũi xe.
3. **Nhìn được hai xe phía trước** (như thấy đèn phanh qua xe trước), khi quyết định có phản ứng hay không. Phần tính phanh vẫn theo xe gần nhất.
4. **IDM cải tiến** (Kesting, Treiber, Helbing 2010) thay cho IDM gốc. IDM gốc làm xe ghi hình phanh 6 m/s² trong khi tối thiểu chỉ cần 1,8 m/s²; bản cải tiến cho 2,5–3,6 m/s².
5. **Khi không bị cản, người lái bám theo kế hoạch** (gia tốc kế hoạch + phản hồi tốc độ), và chỉ quay về chạy trễ khi tốc độ khớp tới 0,05 m/s. Trước đó, lúc chuyển chế độ tốc độ nhảy bậc, tạo gia tốc giả 4 m/s².
6. **Xe xuất hiện khi phía trước đã thay đổi:** nó phản ứng ngay lúc xuất hiện, vì ngoài đời nó đã ở đó và đã thấy. Nếu vẫn đâm trong 2 s đầu thì tính là **"chưa hỗ trợ (xe vừa xuất hiện)"**, cho cả baseline lẫn pilot.
   - Ở `scene-0757`, các xe trong hàng lần lượt đi vào tầm cảm biến từ phía sau, ngay chỗ xe trước đang bị chậm. Đây là nguyên nhân loại lớn nhất ở cảnh này, và giai đoạn 2 phải giải quyết.
7. **Miễn chồng hộp có sẵn trong nhãn theo vị trí tương đối, không theo giờ:** cùng cặp, lệch dọc < 1,5 m, lệch ngang < 0,75 m, không sâu hơn quá 0,1 m. Khi một xe bị trễ, chồng hộp do nhãn (`car_006` chạy song song xe buýt) xảy ra muộn hơn 0,1 s. Luật theo giờ coi đó là va chạm; luật theo vị trí thì không. Vụ đâm đuôi (lệch ngang gần 0) vẫn không được miễn.
8. **Xe gây sự kiện phải còn dữ liệu ít nhất 4 s sau t₀**, và biến mất ở cuối đường đi đã ghi. `car_006` hết dữ liệu ở 5,8 s mà sự kiện bắt đầu ở 5,0 s; nó bị giữ cứng ở điểm cuối, tạo gia tốc giả 33 m/s².
9. **Kiểm vật lý tính từ vị trí x, y thật** (trung bình tốc độ qua 0,2 s), nên bắt được mọi bước nhảy vị trí.
10. **Độ êm trong esmini:** điểm quỹ đạo mỗi 0,05 s. Gia tốc lớn nhất đo trên log esmini (bỏ 0,2 s ở hai đầu quỹ đạo) là 8,0 m/s², bằng mô phỏng. Trước khi bỏ hai đầu, số đo bị nhiễu vì esmini giữ vật thể đứng ở điểm cuối cho tới khi kịch bản dừng.
11. **"Sát" chỉ tính khi mới:** phải gần hơn chính cặp đó trong bản ghi ít nhất 0,1 m (hoặc 0,1 s TTC).
12. **Phát hiện phụ:** bản `pilot` (mốc tốc độ 2 s) **rút ngắn thời gian dừng**. Trong một cảnh dựng tay, xe dừng 3 s chỉ còn 1,55 s dưới 0,3 m/s. Việc này liên quan đến bằng chứng cho "mốc 2 giây" ở bước 5 của kế hoạch cũ.

### 4.10. Kiểm trên 8 cảnh chưa từng thấy, và sửa sau đó (14/10/2026)

**Kiểm:** chạy nguyên code (commit `cd648d6`) trên 8 cảnh không dùng khi chỉnh luật. Pilot hợp lệ 490/649 (75,5%), baseline 153/649 (23,6%). Cảnh `scene-0655` và `scene-0916` không có biến thể nào, vì trong đó không có xe nào chạy sau một xe khác, ngoài xe ghi hình. Lộ ra ba vấn đề:

1. **Nhả ga trước khi phanh.** Khi bắt đầu phản ứng, xe giữ nguyên gia tốc đang có trong bản ghi (xe buýt `bus_002` ở `scene-0553`: +4 m/s²), rồi giảm dần với độ giật phanh, mất 1,2 s mới chuyển sang phanh. Người thật nhả ga ngay. Giờ cần phanh khi đang tăng tốc thì gia tốc về 0 ngay, rồi phanh tăng dần như cũ.
   - Chẩn đoán đầu tiên ("xe phía trước được xác định theo bản ghi gốc") là **sai**: code vốn đã tìm xe phía trước theo vị trí trong mô phỏng.
2. **Giới hạn phanh theo loại xe.** Xe buýt, xe tải, xe công trình, rơ-moóc phanh tối đa 5 m/s² (xe con 8 m/s²). Lưới sự kiện bỏ các mức phanh lớn hơn giới hạn của chính xe gây sự kiện.
3. **Nhãn gốc lỗi được ghi đúng tên.** Nhãn của `truck_002` (`scene-0553`) tụt từ 10 m/s xuống 2 m/s trong 0,5 s. Lỗi vật lý trùng chỗ (trong 5 m dọc đường đi) với lỗi trong chính chuyển động gốc của xe đó thì ghi là `label_error`. Biến thể **vẫn bị loại**, vì kịch bản xuất ra sẽ chứa chuyển động đó.
4. **Nhập làn không tính là đâm đuôi.** Hai xe lệch hướng quá 30° trong 3 s trước khi chạm (ví dụ `car_006` rẽ từ đường bên vào làn ở `scene-0103`) thì ghi là "chưa hỗ trợ" (nhập làn, cắt ngang), không phải va chạm khi bám đuôi.

**Sau khi sửa, 10 cảnh:** pilot hợp lệ 591/777 (76,1%), baseline 225/777 (29,0%). Pilot có 26 biến thể "suýt chạm" trong 10 lần phanh, baseline có 4. (Sau đó luật "suýt chạm" được sửa để không tính xe đi song song ở làn bên: còn 18 trong 6 lần phanh; xem `docs/gia-dinh-va-chi-so.md`, mục 8.4.)

Lý do loại ở pilot:
- 74: xe vừa đi vào khung hình đúng chỗ tình huống;
- 63: nhãn gốc lỗi;
- 40: nhập làn, cắt ngang hoặc người đi bộ;
- 33: các xe khác đâm nhau;
- 3: bám sát;
- 1: sai vật lý.

Hai loại cần nói rõ:
- **33 vụ đâm còn lại đều là đâm thật về vật lý**, không phải lỗi mô hình. Xe sau đã phanh hết mức của nó mà vẫn không kịp, vì nó bám quá sát (`car_010` cách 2 m ở 8,5 m/s) hoặc vì nó là xe buýt mà xe con phía trước phanh 6 m/s².
- **Ca "sai vật lý" duy nhất** là lỗi nhỏ còn lại của mô hình: `truck_002` (`scene-0757`) lùi 0,1 m ở cuối đường đi khi quay lại kế hoạch. Bộ kiểm tra đã bắt được.

## 5. Hai chỉ số

- **Chỉ số 1** (sai số phát lại): giữ nguyên `exact` / `baseline` / `pilot`.
- **Chỉ số 2** (số kịch bản hợp lệ), quyết định của chủ dự án ngày 13/10/2026:
  - **baseline** = cùng bộ sự kiện, nhưng **không ai phản ứng** (xe phía sau phát lại cứng);
  - **pilot** = cùng bộ sự kiện, **có phản ứng** như mục 4.4;
  - cùng danh sách biến thể (chốt trước), cùng bộ kiểm ở mục 4.6;
  - báo: số thử, số chạy được, số hợp lệ, số cuộc chạm trán có ít nhất một biến thể hợp lệ, số tình huống hiếm, lý do loại, thời gian chạy;
  - cách cũ (tua cả quỹ đạo) giữ làm **mốc lịch sử**, không phải baseline.

## 6. Kiểm chứng (điều kiện coi là xong giai đoạn 1)

1. **Không đổi gì:** chạy mô phỏng với "sự kiện rỗng" thì mọi vật thể trùng `pilot` (sai số 0, bằng xây dựng). Có test.
2. **Test tính tay:**
   - xe đuổi theo xe đứng yên dừng cách đúng s₀;
   - phản xạ trễ đúng τ_r;
   - đồng hồ kế hoạch giữ đúng thời gian chờ;
   - dừng trong một bước không trượt quá;
   - kết quả không phụ thuộc thứ tự duyệt.
3. **Hai cảnh thật** (`scene-0757` nhiều xe nối đuôi, `scene-0061` có `car_008` và van): báo số hợp lệ của baseline và pilot, lý do loại, mức phanh đã dùng.
4. **Ảnh động** cho chủ dự án xem: dừng hẳn, giảm 50%, phanh nhẹ, phanh gấp, va chạm với người lái tham chiếu.
5. **Độ êm trên log esmini** của file xuất ra: báo gia tốc và độ giật đo được, so với chuyển động mô phỏng.

## 7. Giới hạn của giai đoạn 1

- Chỉ một loại sự kiện: xe phía trước giảm tốc hoặc dừng. Chưa có người đi bộ, giao lộ, chen làn.
- Xe chỉ phản ứng theo chiều dọc (phanh, tăng tốc), không đánh lái.
- Chưa sửa chuyện vật thể xuất hiện theo tầm cảm biến (giai đoạn 2).
- Thời gian chờ ở chỗ dừng được giữ nguyên, chưa biết đó là đèn hay biển dừng (giai đoạn 2).
- Tham số người lái (a, b, độ giật, τ_r) là giả định có nguồn tham khảo, không đo được từ nhãn 2 Hz. T và s₀ đo được từ bản ghi.

## 8. Các giai đoạn sau

| Giai đoạn | Nội dung | Điểm dừng |
|---|---|---|
| 2 | Dùng liên kết làn, loại vạch dừng (đèn, biển), nhãn trạng thái của nuScenes; vùng hiển thị trên app để thấy quy tắc xuất hiện | ảnh động |
| 3 | Người đi bộ băng qua đường, xe ở giao lộ: vùng xung đột theo hình hộp quét, quyền ưu tiên giữ ổn định, không kẹt nhau | ảnh động |
| 4 | Xe chen làn: kiểm cả xe trước và xe sau ở làn đích, quyết định trước khi vào | ảnh động |
| 5 | Giao diện mới: chọn cuộc chạm trán, kéo tham số, xem ngay, so cảnh gốc với biến thể | chủ dự án dùng thử |
