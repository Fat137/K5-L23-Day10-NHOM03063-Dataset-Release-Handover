# Bảo mật khi làm việc

Gắn với lô `lab250_6aa6b3a10f32` (v1, đang HOLD) và lô bàn giao `lab250_6aa6b3a10f32_v2`.

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp

Không chép. Lô gồm 250 ảnh có người thật, nhãn và thông tin job (người gán, người kiểm), nên chỉ được nằm trên máy và kho của dự án. USB dễ mất, không mã hoá và không ai ghi lại được ai đã cầm dữ liệu. Gửi qua email cá nhân cũng là đưa dữ liệu ra khỏi hệ thống công ty. Nhờ người khác làm hộ bằng tài khoản của mình thì log sẽ ghi sai người làm. Cách đúng: dừng ở mốc hiện tại, ghi lại tiến độ (ví dụ đang xem tới ảnh nào trong hàng đợi review), hôm sau làm tiếp trên máy công ty. Nếu thật sự cần làm từ xa thì xin trưởng nhóm cấp quyền truy cập từ xa (VPN, máy ảo của dự án).

## 2. Năm việc: được hay không

- **Mở job được giao trên máy công ty:** được. Đúng người, đúng quyền, đúng máy, có log.
- **Chụp màn hình gửi người quen:** không. Ảnh chụp màn hình vẫn là dữ liệu dự án (mặt người, nhãn), gửi ra ngoài là lộ dữ liệu, không thu hồi được.
- **Chép lô ra USB:** không. Lý do như ca USB ở trên: dữ liệu rời khỏi hệ thống, không kiểm soát được.
- **Dán nhãn thật lên chatbot:** không với dữ liệu thật của dự án, vì nội dung gửi lên dịch vụ bên ngoài có thể bị lưu lại. Trong lab này ảnh COCO là dữ liệu công khai nên được hỏi, nhưng phải ghi vào `prompts.md`.
- **Đưa tài khoản CVAT cho đồng nghiệp:** không. Mỗi người một tài khoản để truy vết ai gán, ai sửa. Dùng chung thì `jobs.csv`, rework queue và lineage ghi sai người, và khi có ticket như ticket `cup` của lô này sẽ không biết báo ai.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ

Lô của nhóm có ảnh mặt người nhìn rõ, ví dụ `000000004395` (cận cảnh nam thanh niên áo sơ mi trắng, thắt cà vạt, mặt nhìn thẳng ngang) và `000000001296` (cận cảnh cô gái cầm điện thoại, mặt rõ, phía sau có đám đông). Khi thấy ảnh như vậy mà guideline yêu cầu làm mờ: chuyển lô sang **Hold** (không Release, không giao tiếp), ghi tên ảnh và báo người phụ trách dữ liệu/bảo mật của dự án. Không tự làm mờ hay xoá ảnh, vì sửa hoặc xoá file sẽ làm đổi hash và manifest, mất dấu vết trong lineage, và quyết định xử lý dữ liệu cá nhân (làm mờ, xoá, hay xin lại đồng ý) là việc của người phụ trách, phải làm theo quy trình rồi tạo một bản phát hành mới có ghi parent.
