# Tool Crawler Trip

Ứng dụng Electron dành cho người không rành kỹ thuật: dán URL trang danh sách Trip.com, chọn số lượng/ngôn ngữ, cào và tải CSV. Ứng dụng chỉ lấy ba nhóm dữ liệu `DESCRIPTION`, `POLICY`, `SURROUNDING`; không lấy phòng, giá, ảnh, tiện nghi hay đánh giá và không dùng PostgreSQL.

## Cài lần đầu trên Windows

Cần cài sẵn:

- Google Chrome.
- Python 3.11 trở lên, có chọn **Add Python to PATH** khi cài.
- Node.js 20 trở lên nếu chạy mã nguồn hoặc tự tạo installer.

Mở PowerShell tại thư mục dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm install
```

Không chạy `playwright install`: app dùng `channel="chrome"`, tức Chrome có sẵn trên máy, không tải Chromium riêng.

## Chạy

```powershell
.\.venv\Scripts\Activate.ps1
npm start
```

Khi chạy mã nguồn, Electron tự ưu tiên Python tại `.venv` của chính project này,
không dùng nhầm virtualenv của repo khác đang được IDE kích hoạt.

Lần đầu, chọn ngôn ngữ rồi bấm **Lấy lại cookie**. Chrome mở trong 45 giây; đăng nhập Trip.com nếu cần và giữ cửa sổ mở đến khi app báo xong. Sau đó:

1. Mở trang kết quả danh sách khách sạn trên Trip.com và sao chép nguyên URL.
2. Dán URL, nhập số lượng, chọn `vi`/`en`, bấm **Cào**.
3. Theo dõi tiến độ và log. Khi xong, bấm **Xuất CSV**.
4. Với mỗi file CSV, có thể **Xem trước**, **Mở** bằng Excel/ứng dụng CSV mặc định
   hoặc **Tải về**. Nút **Mở thư mục** đưa thẳng tới thư mục chứa kết quả.

Raw được lưu tại `output/details/raw`; CSV ở `output/csv`. Khi chạy bản cài đặt, các thư mục này nằm trong thư mục dữ liệu người dùng của ứng dụng để luôn có quyền ghi.

Lịch sử 50 tác vụ gần nhất và log tương ứng được lưu tại
`output/lich_su_tac_vu.json`. Bấm **Xem log** để xem lại sau khi đóng/mở app;
bấm **Xóa lịch sử** chỉ xóa nhật ký tác vụ, không xóa raw hoặc CSV.

Khi dán URL, app thống kê dữ liệu đã có của đúng thành phố theo từng ngôn ngữ.
Nếu chạy lại, khách sạn đã có đủ trang chi tiết và surrounding được ghi
`ĐÃ CÓ · bỏ qua`; raw cũ thiếu surrounding hoặc chưa hoàn chỉnh sẽ tự được cào
lại. App cũng gộp ID từ danh sách mới với các checkpoint danh sách cũ, nhờ đó
có thể lấy thêm khách sạn khi Trip.com thay đổi nhóm gợi ý giữa các lượt. Vì vậy
có thể tiếp tục một lượt dở dang mà không tốn request cho dữ liệu đã đủ.

Sau lần đầu bấm **Tải về**, file CSV được đánh dấu **Đã tải** và nút tải được ẩn,
chỉ còn xem trước/mở file. Trạng thái này nằm trong
`output/trang_thai_tai_csv.json` và không làm thay đổi nội dung CSV.

Khu vực **Thành phố đã cào** tổng hợp trực tiếp từ raw và checkpoint: tổng số
khách sạn, số VI/EN hoàn chỉnh, số ID đã biết và lần cập nhật gần nhất. Nút
**Cào tiếp** tự điền lại URL thành phố và chuyển ô số lượng sang **số khách sạn
muốn cào thêm**. Ví dụ đã có 20, nhập thêm 20 thì mục tiêu mới là 40; chỉ ID
chưa hoàn chỉnh được gửi sang bước cào chi tiết. Nếu Trip.com chưa trả ID mới,
tác vụ kết thúc với trạng thái **Chưa đủ** thay vì báo thành công 100% sai.

## Tạo installer Windows

```powershell
python -m pip install -r requirements-build.txt
npm run build
```

Lệnh build đóng gói backend Python bằng PyInstaller rồi tạo installer NSIS trong `dist/`. Máy người dùng cài installer chỉ cần Google Chrome, không cần Python hay Node.js. Các yêu cầu Python/Node.js chỉ dành cho máy phát triển và máy tạo installer.

## Khi cookie hết hạn hoặc bị chặn

- Nếu log báo chưa có cookie, bị chuyển sang đăng nhập, thiếu `hotelDetailResponse`, hãy bấm **Lấy lại cookie** và đăng nhập lại.
- Nếu log báo **BỊ CHẶN**, app dừng ngay. Không bấm chạy liên tục; nghỉ vài giờ rồi thử lại với cookie hợp lệ.
- Nếu log có `ResultId=201`, Trip.com chỉ trả trạng thái mà không trả danh sách khách sạn. App giữ dữ liệu cũ và dừng; lấy lại cookie không bảo đảm xử lý được trường hợp giới hạn API danh sách này.
- App không giải CAPTCHA, không xoay IP, không đổi vân tay và không bỏ delay. Nếu Chrome hiện CAPTCHA, tự hoàn tất trong cửa sổ Chrome; nếu vẫn bị chặn thì dừng.
- Dữ liệu đã cào xong trước khi dừng vẫn nằm trong thư mục raw và vẫn có thể xuất CSV.

## CSV

File dùng UTF-8 có BOM để mở bằng Excel và có đúng 7 cột:

```text
row_uuid, property_id, type, section_type, lang, field, value
```

Logic xuất nằm trong `src/xuat_csv.py`, được giữ theo bản đã đối chiếu với SQL cũ.
