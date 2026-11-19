# Dùng AI

| # | Ai dùng | Công cụ | Prompt (tóm tắt) | AI sai ở đâu | Nhóm kiểm lại thế nào |
|---|---|---|---|---|---|
| 1 | 03063 | Claude Code | "Đọc bài lab Day-10 và viết validator luật theo giao diện cố định trong GUIDE (chỉ thư viện chuẩn + `scripts/pngutil.py`, chỉ đọc `delivery/`)". Kết quả: `validator/common.py`, `validator/rules.py`, `validator/validate.py`. | Chưa thấy sai trên các lô đã thử. Điểm phải tự kiểm: ngưỡng `duplicate_box` (cùng kích thước ±0,5 px, tâm lệch ≤ 3 px) và `bbox_out_of_bounds` (sai số 0,5 px) do AI đề xuất, không lấy từ đề. | Chạy `score_findings.py` trên seed 3063007, 11, 22 và lô dạng đề ẩn (`--opaque`, seed 777): lỗi luật ≈ 1.0. Lô sạch: 0 lỗi luật. Đo trên các ảnh không bị báo: box tự nhiên tràn mép 0 px; cặp box cùng lớp gần nhau nhất vẫn lệch kích thước 2,1 px (> 0,5); `area` khớp số pixel ở mọi segment. |
| 2 | 03063 | Claude Code | "Viết `tools/gop_review.py` gộp `work/review_*.csv` của 4 người thành `review_log.csv`, không tự quyết verdict". | Chưa thấy sai. | Thử bằng file giả: file có BOM, hai người ghi khác verdict, ghi chú ngắn. Script báo đủ 3 lỗi, file ra không có BOM. |
