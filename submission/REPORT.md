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
<<QC v1 a/b, kết luận, vì sao R-021 phải xem lại hoặc train lại.>>

## 4. Hash chứng minh gì, không chứng minh gì?
<<>>

## 5. Truy vết
<<Tiêu chí tầng a/b, vì sao lấy guideline theo job.>>

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
<<>>
