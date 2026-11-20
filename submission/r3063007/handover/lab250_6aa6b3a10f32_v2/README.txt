Release: lab250_6aa6b3a10f32_v2
Parent: lab250_6aa6b3a10f32
Số ảnh: 239
Số nhãn: 1644
Guideline: v1.2 (J01-J03), v1.3 (J04-J10)
QC v1: 20/250 = 8,0%
Kết luận v1: Hold — 20 ảnh/cảnh lỗi trên 250 ảnh = 8,0%, vượt ngưỡng 2% nên không Release; R-021 đã train trên v1 phải xem lại hoặc train lại
Kết luận v2: Release — sản phẩm detection: tách 11 ảnh lỗi nhãn detection/thiếu file sang rework_queue, sửa 2 hash, 1 guideline, 1 cảnh rò split; nhãn detection còn lại giữ nguyên như v1
Ghi chú: Hash: 000000014226, 000000017714 đã mở ảnh kiểm, ảnh còn nguyên, ghi sha256 mới trong manifest.csv. Guideline: 000000023751 ghi lại theo guideline của job trong truyvet.csv. Split: scene_233: 000000003501 (val 4, train 1) -> val (cả cảnh về split đa số). Rework giao lại người gán/người kiểm của job: A01/Q01 (1 ảnh), A01/Q02 (1 ảnh), A02/Q02 (1 ảnh), A03/Q01 (3 ảnh), A03/Q03 (1 ảnh), A04/Q02 (2 ảnh), A05/Q03 (2 ảnh). Lỗi chỉ ở panoptic, ảnh ở lại v2 vì nhãn detection đúng, báo team panoptic: 000000007386 (thing_overlap), 000000009590 (instance_merge), 000000020553 (instance_merge), 000000022705 (category_swap), 000000025139 (thing_overlap).
