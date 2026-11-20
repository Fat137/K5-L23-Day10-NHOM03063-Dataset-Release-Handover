# Báo cáo nhóm 03063

## 1. Số liệu luyện tập
- F1 theo seed (rule / cross_check / overall): <<seed: ... / ... / ...>>
- Số ứng viên trên lô sạch (`--no-faults`): <<...>>; hàng đợi trên seed luyện tập: <<... ảnh>>
- Ngưỡng đã chọn và cách chọn (không dùng `_private`): <<...>>

### Validator luật
- F1 lỗi luật ≈ 1.0 trên seed 3063007, 11, 22 và lô dạng đề ẩn (`--opaque`, seed 777). Lô sạch: 0 lỗi luật.
- Ngưỡng và khoảng an toàn (đo trên các ảnh không bị báo của 4 lô):
  - `bbox_out_of_bounds`: cho phép 0,5 px sai số làm tròn. Box tự nhiên tràn mép 0 px.
  - `duplicate_box`: cùng lớp, kích thước lệch ≤ 0,5 px, tâm lệch ≤ 3 px. Cặp box cùng lớp tự nhiên gần nhau nhất lệch kích thước 2,1 px, nên không bị báo nhầm. Không dùng IoU vì cặp tự nhiên có thể chồng nhau tới IoU ~0,66.
  - `thing_overlap`: báo khi `area` khai lớn hơn số pixel đếm được trong mask. Ở segment tự nhiên hai số này luôn bằng nhau.
  - `wrong_hash`: tính lại sha256 trên bytes của ảnh, nhãn và mask rồi so với manifest, không chỉ kiểm định dạng 64 ký tự.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
<<Trả lời bằng số của nhóm.>>

## 3. Quyết định và lineage
- QC v1: **11/250 = 4,4%** ảnh/cảnh lỗi (số tạm tính trên lỗi luật của `rules.json`; **cập nhật lại khi có `errors.json` cuối** gồm cả lỗi gán nhãn đã `confirmed`). Mỗi ảnh tối đa một lỗi, mỗi `scene_leak` tính một đơn vị. Trên ngưỡng 2% của Day 7 nên v1 **Hold**. Chỉ riêng lỗi luật đã vượt ngưỡng, nên kết luận không đổi khi có thêm lỗi gán nhãn.
- Lineage: `decision HOLD` cho `lab250_6aa6b3a10f32`; `lineage.py impact` in `R-021: affected=True action=review_or_retrain`; `release lab250_6aa6b3a10f32_v2 --parent lab250_6aa6b3a10f32`. `check_handover.py` H14 PASS.
- Vì sao R-021 phải xem lại hoặc train lại: R-021 đã học từ nhãn v1, trong đó có box tràn mép, box lặp, class_id sai và các box gán nhầm lớp hoặc lệch. Đổi dataset sang v2 **không làm model quên** những gì đã học. Phải đánh giá lại R-021 trên dữ liệu đã sửa; nếu lỗi ảnh hưởng tới lớp quan trọng (ví dụ lớp `cup` mà ticket của team AI báo) thì train lại trên v2.
- Lô v2 (số theo lần dựng với `errors.json` tạm, cập nhật sau khi có bản cuối): 245 ảnh, 1692 nhãn, 5 ảnh lỗi nhãn detection (`bbox_out_of_bounds` 2, `duplicate_box` 2, `invalid_class` 1) chuyển sang `rework_queue.csv`, giao đúng người gán/người kiểm theo `jobs.csv`. Sửa ngay trong v2: 2 ảnh `wrong_hash` (đã mở ảnh kiểm, còn nguyên nên chỉ ghi hash mới), 1 ảnh `guideline_mismatch` (guideline theo job), 1 cảnh rò split (`scene_233`, ảnh `000000003501` về `val` theo split đa số 4/5). 2 ảnh lỗi `thing_overlap` ở lại v2 vì nhãn detection vẫn đúng, ghi trong Ghi chú của `README.txt` để báo team panoptic.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Chứng minh:** file đang có giống **từng byte** với file lúc lập manifest: không ai sửa, không hỏng khi chép, đúng là file đã bàn giao. `.sha256` của zip v2 cho phép bất kỳ ai đóng gói lại và kiểm cùng một mã (H15). `release_id` là hash của manifest và metadata v1, nên sửa v1 sẽ bị phát hiện ngay (H1).
- **Không chứng minh:** nhãn đúng, box đúng vật, lớp đúng, ảnh đúng nội dung, hay quyết định QC đúng. Một box lệch vẫn có hash hợp lệ. Hai ca `wrong_hash` của lô (`000000014226`, `000000017714`) là ví dụ ngược lại: ảnh vẫn nguyên, chỉ dòng hash trong manifest sai, nên phải **mở ảnh xem** trước khi kết luận. Cả hai đã mở: ảnh mở được, nội dung bình thường (người đeo tai nghe trên tàu; bàn có cốc cà phê và đĩa bánh), nên giữ ảnh và ghi hash mới.
- **Vì sao không ghi đè v1:** R-021 và lineage trỏ tới `lab250_6aa6b3a10f32`. Ghi đè thì mất bằng chứng model đã học từ dữ liệu nào, không tính được tác động và không so được v1 với v2. Bản sửa luôn là lô mới có `parent`.

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
