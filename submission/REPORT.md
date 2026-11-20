# Báo cáo nhóm 03063

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall), `score_findings.py` làm tròn một chữ số: seed 3063007 sau khi review **1.0 / 1.0 / 1.0**. Các seed thử 11, 22 và lô dạng đề ẩn (seed 777) chỉ dùng để đo validator luật: rule ≈ 1.0.
- Số ứng viên trên lô sạch (`--no-faults`): **0**; hàng đợi đã review trên seed luyện tập: **10 ảnh** (9 confirmed, 1 rejected). Xem ghi chú về phiên bản `crosscheck` ở cuối mục 1.
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): một cặp box–segment cùng lớp được coi là "khớp" khi box chứa ≥ 98% pixel segment và IoU ≥ 0,8 (box ≥ 400 px) hoặc ≥ 0,5 (box nhỏ), đo trên lô sạch kết hợp tự gài lỗi bằng `tools/tu_gai_loi.py` (chi tiết bên dưới).

### Validator luật
- F1 lỗi luật ≈ 1.0 trên seed 3063007, 11, 22 và lô dạng đề ẩn (`--opaque`, seed 777). Lô sạch: 0 lỗi luật.
- Ngưỡng và khoảng an toàn (đo trên các ảnh không bị báo của 4 lô):
  - `bbox_out_of_bounds`: cho phép 0,5 px sai số làm tròn. Box tự nhiên tràn mép 0 px.
  - `duplicate_box`: cùng lớp, kích thước lệch ≤ 0,5 px, tâm lệch ≤ 3 px. Cặp box cùng lớp tự nhiên gần nhau nhất lệch kích thước 2,1 px, nên không bị báo nhầm. Không dùng IoU vì cặp tự nhiên có thể chồng nhau tới IoU ~0,66.
  - `thing_overlap`: báo khi `area` khai lớn hơn số pixel đếm được trong mask. Ở segment tự nhiên hai số này luôn bằng nhau.
  - `wrong_hash`: tính lại sha256 trên bytes của ảnh, nhãn và mask rồi so với manifest, không chỉ kiểm định dạng 64 ký tự.

### Đối chiếu detection ↔ panoptic (`validator/crosscheck.py`)
- Số ứng viên trên lô sạch (`runs/clean`, 50 ảnh calib, `--no-faults`): **0**. Bản hiện tại cho hàng đợi 13 ảnh trên seed luyện tập 3063007 (bbox_drift 3, class_swap/category_swap 4, instance_merge 4, missing_box 2); trên các seed thử 11, 22, 33, 44 và lô dạng đề ẩn (`--opaque`, seed 777): 11–14 ảnh.
- Cách ghép: box với segment **cùng tên lớp** (`classes.txt` ↔ `categories`), đo bằng IoU bbox và tỉ lệ **pixel của segment nằm trong box** (đếm trên mask), không chỉ IoU bbox.
- Cách chọn ngưỡng (không dùng `_private`):
  1. Đo trên lô sạch: cả 435 box tự nhiên đều chứa 100% pixel của segment cùng lớp; IoU bbox dưới 0,8 chỉ gặp ở box tí hon (< 160 pixel). Từ đó: một cặp "khớp" khi box chứa ≥ 98% pixel segment và IoU ≥ 0,8 (box ≥ 400 pixel) hoặc ≥ 0,5 (box nhỏ).
  2. Tự gài lỗi lên lô sạch bằng `tools/tu_gai_loi.py` (script của nhóm, tự ghi đáp án): mức lỗi như lô luyện tập bắt được 78/80 lỗi, mức khó hơn (box lệch 5–15%, vật nhỏ hơn) bắt được 56/60, **0 ảnh báo thừa**. Các ca sót là box gần như không bị dịch (IoU vẫn 0,81–0,97).
  3. Ứng viên `missing_box` trên lô luyện tập lặp lại ở cùng ảnh qua mọi seed (000000000872, 000000001818, 000000012748): segment không có box riêng nhưng có box cùng lớp gần trùng (IoU ≥ 0,72). Đây là cặp vật cùng lớp mà lô giao đã bỏ bớt box trùng, không phải lỗi gài, nên thêm luật bỏ qua (IoU ≥ 0,7).
- Thứ tự xét mỗi ảnh: khác lớp → gộp instance → box lệch → thiếu box; mỗi ảnh tối đa một ứng viên (mỗi ảnh mang nhiều nhất một lỗi), các dấu hiệu khác ghi thêm vào `detail`.
- **Phiên bản dùng để review:** hàng đợi đã review (10 ảnh ở seed luyện tập, 10 ảnh ở đề ẩn, nằm trong `candidates.json`) sinh từ bản `crosscheck` đầu tiên, chỉ ghép bằng IoU bbox. Bản hiện tại trong repo (đo bằng pixel mask, như mô tả ở trên) giữ đủ 10 ảnh đó và tìm thêm 3 ảnh ở seed luyện tập, 13 ảnh ở đề ẩn. Trên bộ tự gài lỗi, bản đầu bắt 68/80 và 49/60, bản hiện tại bắt 78/80 và 56/60; cả hai đều 0 báo thừa. Nhóm không review các ứng viên thêm, nên chúng không có trong `candidates.json` và `errors.json` đã nộp.
- **Ví dụ lệch tự nhiên đã `rejected`:** `000000004134` (bbox_drift): vật trong box là lưng ghế màu đen, nhưng cả detection và panoptic cùng ghi `person`. Đây là sai sẵn của nhãn gốc COCO (hai nguồn giống nhau), không phải lỗi gài; box chỉ rộng hơn segment ở mép trái, ba cạnh còn lại khít, không bị dịch.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Thử trên seed 11, 22, 33, 44 và lô 777: lấy lỗi luật cộng **toàn bộ ứng viên** làm `errors.json` mà không xem ảnh, F1 của nhóm lỗi gán nhãn chỉ khoảng **0,4–0,5**. Hai lý do:
1. **Hướng đổi lớp không biết trước.** Khi box và segment trùng chỗ mà khác lớp, ứng viên chỉ nói "hai nguồn bất đồng". Nếu ghi bừa `class_swap` thì ca nào thật ra là `category_swap` thành **một báo thừa + một bỏ sót** cùng lúc. Chỉ nhìn ảnh mới biết bên nào ghi đúng vật.
2. **Lệch tự nhiên của COCO** (vật bị che, cặp box trùng đã bị bỏ bớt) cũng thành ứng viên. F1 là trung bình điều hoà của precision và recall, nên mỗi báo thừa kéo precision xuống, trừ điểm như một lỗi bỏ sót.

Vì vậy nhóm giữ hàng đợi nhỏ (≈13 ảnh) để xem hết, và chỉ đưa vào `errors.json` các dòng `confirmed` sau khi xem ảnh.

## 3. Quyết định và lineage
- QC v1: **20/250 = 8,0%** ảnh/cảnh lỗi theo `errors.json` cuối (11 lỗi luật + 9 lỗi gán nhãn đã `confirmed`). Mỗi ảnh tối đa một lỗi, mỗi `scene_leak` tính một đơn vị. Trên ngưỡng 2% của Day 7 nên v1 **Hold**. Riêng lỗi luật (11/250 = 4,4%) đã vượt ngưỡng.
- Lineage: `decision HOLD` cho `lab250_6aa6b3a10f32`; `lineage.py impact` in `R-021: affected=True action=review_or_retrain`; `release lab250_6aa6b3a10f32_v2 --parent lab250_6aa6b3a10f32`. `check_handover.py` H14 PASS.
- Vì sao R-021 phải xem lại hoặc train lại: R-021 đã học từ nhãn v1, trong đó có box tràn mép, box lặp, class_id sai và các box gán nhầm lớp hoặc lệch. Đổi dataset sang v2 **không làm model quên** những gì đã học. Phải đánh giá lại R-021 trên dữ liệu đã sửa; nếu lỗi ảnh hưởng tới lớp quan trọng (ví dụ lớp `cup` mà ticket của team AI báo) thì train lại trên v2.
- Lô v2: **239 ảnh, 1644 nhãn**. **11 ảnh** lỗi nhãn detection chuyển sang `rework_queue.csv` (lỗi luật: `bbox_out_of_bounds` 2, `duplicate_box` 2, `invalid_class` 1; lỗi gán nhãn đã confirmed: `bbox_drift` 3, `missing_box` 2, `class_swap` 1), giao đúng người gán/người kiểm theo `jobs.csv`. Sửa ngay trong v2: 2 ảnh `wrong_hash` (đã mở ảnh kiểm, còn nguyên nên chỉ ghi hash mới), 1 ảnh `guideline_mismatch` (guideline theo job), 1 cảnh rò split (`scene_233`, ảnh `000000003501` về `val` theo split đa số 4/5). 5 ảnh chỉ lỗi panoptic ở lại v2 vì nhãn detection vẫn đúng (`thing_overlap` 2, `instance_merge` 2, `category_swap` 1), ghi trong Ghi chú của `README.txt` để báo team panoptic. `check_handover.py`: 17/17 PASS.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Chứng minh:** file đang có giống **từng byte** với file lúc lập manifest: không ai sửa, không hỏng khi chép, đúng là file đã bàn giao. `.sha256` của zip v2 cho phép bất kỳ ai đóng gói lại và kiểm cùng một mã (H15). `release_id` là hash của manifest và metadata v1, nên sửa v1 sẽ bị phát hiện ngay (H1).
- **Không chứng minh:** nhãn đúng, box đúng vật, lớp đúng, ảnh đúng nội dung, hay quyết định QC đúng. Một box lệch vẫn có hash hợp lệ. Hai ca `wrong_hash` của lô (`000000014226`, `000000017714`) là ví dụ ngược lại: ảnh vẫn nguyên, chỉ dòng hash trong manifest sai, nên phải **mở ảnh xem** trước khi kết luận. Cả hai đã mở: ảnh mở được, nội dung bình thường (người đeo tai nghe trên tàu; bàn có cốc cà phê và đĩa bánh), nên giữ ảnh và ghi hash mới.
- **Vì sao không ghi đè v1:** R-021 và lineage trỏ tới `lab250_6aa6b3a10f32`. Ghi đè thì mất bằng chứng model đã học từ dữ liệu nào, không tính được tác động và không so được v1 với v2. Bản sửa luôn là lô mới có `parent`.

## 5. Truy vết
- Ticket (`incoming/ticket.md`): team AI báo model bỏ sót `cup` bị che hoặc ở mép ảnh, thấy rõ ở scene_143 và scene_372. Changelog: v1.3 bắt buộc gán box cho `cup` bị che trên 50% hoặc cắt ở mép; v1.2 cho phép bỏ qua.
- Tiêu chí (`tools/trace_query.py`, đọc ticket và changelog, không ghi cứng tên lớp hay scene):
  - Job theo guideline **cũ** lấy từ `jobs.csv` (J01–J03 ghi v1.2), **không** lấy `guideline_version` ghi ở từng ảnh, vì metadata ảnh có thể sai (chính là lỗi `guideline_mismatch`; lô có một ảnh như vậy, `000000023751`).
  - "Có lớp bị đổi quy tắc" = có ít nhất một box detection lớp `cup` trong `labels/`.
  - `tier_a`: ảnh thỏa điều kiện trên và thuộc scene_143 hoặc scene_372 → **4 ảnh**.
  - `tier_b`: ảnh thỏa điều kiện nhưng ở scene khác, chưa ai báo → **3 ảnh**.
  - `notify`: người gán + người kiểm của các job chứa ảnh tầng a và b → **A02, Q02**.
- Ý nghĩa: tầng a là chỗ team AI đã thấy, mở lại trước. Tầng b là chỗ có cùng nguy cơ (gán theo luật cũ nên có thể bỏ `cup` bị che) mà chưa ai kiểm. Chỉ sửa tầng a thì model vẫn học sai từ tầng b.
- Đã thử trên seed 3063007, 11, 22, 33 và lô dạng đề ẩn (seed 777): truy vết F1 ≈ 1.0 ở cả `tier_a`, `tier_b`, `notify` (`score_findings.py`).

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
- Không thấy bug làm sai kết quả trong `scripts/`.
- Điểm dễ vấp: `scripts/merge_review.py` và `scripts/check_handover.py` đọc CSV bằng `utf-8` (không bỏ BOM). File review lưu từ Excel có BOM ở đầu và bị **mất số 0 đầu tên ảnh** (`000000004134` → `4134`), nên ảnh không khớp với `candidates.json`. Nhóm sửa CSV bằng trình soạn thảo văn bản, và `tools/gop_review.py` tự bỏ BOM, báo ảnh ứng viên chưa ai xem.
