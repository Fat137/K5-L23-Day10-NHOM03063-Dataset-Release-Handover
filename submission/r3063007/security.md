# Bảo mật khi làm việc

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp
Tuyệt đối không được sao chép dữ liệu của lô ra USB cá nhân, không gửi dữ liệu qua email cá nhân và không nhờ người ngoài làm giúp. Việc sao chép dữ liệu nội bộ ra thiết bị cá nhân hoặc gửi ra môi trường ngoài vi phạm nghiêm trọng thỏa thuận bảo mật thông tin (NDA), tiềm ẩn rủi ro lộ lọt dữ liệu dự án và vi phạm quy định pháp lý về bảo vệ dữ liệu khách hàng. Thay vào đó, nếu cần làm việc ngoài giờ, nhân viên phải xin phê duyệt làm việc từ xa thông qua hạ tầng an toàn của công ty (VPN nội bộ, Remote Desktop/VDI được bảo mật). Nếu không được cấp quyền, nhân viên cần báo cáo trung thực với Team Lead/Project Manager để bàn giao tiến độ, phân bổ thêm nhân lực hoặc xin gia hạn mốc giao hàng sang ngày làm việc kế tiếp.

## 2. Năm việc: được hay không
1. Mở job được giao trên máy công ty: ĐƯỢC. Đây là thiết bị do công ty quản lý, đã được cài đặt các phần mềm bảo mật, tường lửa và chính sách kiểm soát an toàn thông tin theo tiêu chuẩn doanh nghiệp.
2. Chụp màn hình gửi người quen: KHÔNG ĐƯỢC. Đây là hành vi tiết lộ dữ liệu nội bộ và quy trình dự án chưa công bố ra bên ngoài, vi phạm trực tiếp cam kết bảo mật NDA và đạo đức nghề nghiệp.
3. Chép lô ra USB: KHÔNG ĐƯỢC. Thiết bị lưu trữ cá nhân không được mã hóa, không có nhật ký kiểm toán (audit log), rất dễ thất lạc hoặc chứa mã độc lây nhiễm vào hệ thống mạng nội bộ.
4. Dán nhãn thật lên chatbot: KHÔNG ĐƯỢC. Việc đưa dữ liệu thật của dự án lên các chatbot AI công cộng (như ChatGPT, Claude web) có thể khiến dữ liệu bị lưu trữ trên máy chủ bên thứ ba và dùng để tái huấn luyện mô hình công cộng, gây rò rỉ dữ liệu bảo mật.
5. Đưa tài khoản CVAT cho đồng nghiệp: KHÔNG ĐƯỢC. Mỗi tài khoản gán nhãn được định danh cá nhân để phục vụ truy vết trách nhiệm và quản lý chất lượng (lineage/audit trail). Việc chia sẻ tài khoản làm mất tính minh bạch trong truy vết ai đã gán, ai đã kiểm duyệt và vi phạm chính sách an ninh tài khoản.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ
Kết luận: Trạng thái của lô dữ liệu là HOLD và lập tức báo cáo người phụ trách (Team Lead/Data Manager và bộ phận phụ trách Privacy). Nhân viên QC và annotator tuyệt đối không được tự ý can thiệp làm mờ thủ công hoặc tự ý xóa ảnh khỏi lô. Lý do: tự làm mờ bằng công cụ ngoài có thể làm biến dạng cấu trúc pixel, làm sai lệch nhãn bounding box và mask panoptic đã đồng bộ, đồng thời việc tự xóa ảnh sẽ làm phá vỡ cấu trúc cảnh (scene) và phân bố dữ liệu train/val. Quy trình chuẩn là HOLD lô và chuyển lại cho bộ phận tiền xử lý thu thập dữ liệu để chạy pipeline làm mờ tự động đạt chuẩn khử định danh (anonymization) theo quy định bảo vệ quyền riêng tư.
Trong lô dữ liệu của nhóm, ví dụ các ảnh có chứa mặt người nhìn rõ cần được rà soát và kiểm soát là ảnh 000000000785 và ảnh 000000000139.
