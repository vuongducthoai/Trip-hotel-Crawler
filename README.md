# Trip Hotel Data (tool_crawler_trip)

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

Cách nhanh: mở thư mục `scripts` và **nhấp đúp `build-installer.cmd`** (máy đã có `.venv`
với PyInstaller và `node_modules` với electron-builder thì không cần cài thêm).
File setup ra ở `dist\Trip Hotel Data Setup <version>.exe`.

Hoặc chạy tay:

```powershell
python -m pip install -r requirements-build.txt
npm run build
```

Lệnh build đóng gói backend Python bằng PyInstaller rồi tạo installer NSIS trong `dist/`. Máy người dùng cài installer chỉ cần Google Chrome, không cần Python hay Node.js. Các yêu cầu Python/Node.js chỉ dành cho máy phát triển và máy tạo installer.

## Thư mục dữ liệu của bản cài

Bản cài (`Trip Hotel Data Setup x.y.z.exe`) lưu `output\` và `browser_profile_*\` tại
**`<thư mục cài đặt>\data\`** (mặc định `C:\Users\<tên>\AppData\Local\Programs\Trip Hotel Data\data`).
Nếu thư mục cài không ghi được (ví dụ cài vào Program Files), app tự rơi về
`%APPDATA%\Trip Hotel Data`. Đường dẫn đang dùng hiện ở chân trang, kèm nút *Mở thư mục*.

Cảnh báo: gỡ cài đặt hoặc cài đè phiên bản mới sẽ xoá thư mục cài, **kể cả `data\`** —
sao lưu `data\output` trước khi cập nhật. Muốn cố định một chỗ khác, đặt biến môi
trường `TOOL_CRAWLER_DATA_DIR=D:\TripHotelData` trước khi mở app.

## Khi cookie hết hạn hoặc bị chặn

- Nếu log báo chưa có cookie, bị chuyển sang đăng nhập, thiếu `hotelDetailResponse`, hãy bấm **Lấy lại cookie** và đăng nhập lại.
- Nếu log báo **BỊ CHẶN**, app dừng ngay. Không bấm chạy liên tục; nghỉ vài giờ rồi thử lại với cookie hợp lệ.
- Nếu log có `ResultId=201`, Trip.com chỉ trả trạng thái mà không trả danh sách khách sạn. App giữ dữ liệu cũ và dừng; lấy lại cookie không bảo đảm xử lý được trường hợp giới hạn API danh sách này.
- App không giải CAPTCHA, không xoay IP, không đổi vân tay và không bỏ delay. Nếu Chrome hiện CAPTCHA, tự hoàn tất trong cửa sổ Chrome; nếu vẫn bị chặn thì dừng.
- Dữ liệu đã cào xong trước khi dừng vẫn nằm trong thư mục raw và vẫn có thể xuất CSV.

### Khi API danh sách bị chặn mềm (ResultId=201)

Chính trang Trip.com trong Chrome cũng không tải thêm được khách sạn, chỉ còn
~12 khách sạn SSR ở trang 1. Từ 27/09/2026 tool tự **gom thêm bằng trang 1 SSR
theo tổ hợp bộ lọc** (`listFilters` trên URL): hạng sao `16~x` × sắp xếp `17~x`
× điểm đánh giá `6~x`, tối đa 96 tổ hợp, mỗi tổ hợp ~12 khách sạn, nghỉ 1–2.5 s
giữa các lần tải. Không gọi `fetchHotelList`. Dừng sớm khi đủ số lượng, khi 12
tổ hợp liên tiếp không ra khách sạn mới, hoặc khi Trip.com ngừng trả SSR.

Biến môi trường: `SSR_SPLIT_ENABLED=false` để tắt; `SSR_SPLIT_MAX_VARIANTS`,
`SSR_SPLIT_MIN_DELAY`, `SSR_SPLIT_MAX_DELAY`, `SSR_SPLIT_STOP_AFTER_EMPTY`.

Giới hạn: bộ lọc giá (`80`) bị server bỏ qua nên không dùng. Với thành phố lớn,
cách này chỉ lấy được vài trăm khách sạn; muốn lấy trọn vẫn cần API phân trang
hoạt động (chờ Trip.com gỡ chặn, đăng nhập profile bằng
`python scripts\mo_profile.py --lang en`).

## Cào theo danh sách ID / URL

Tab **Danh sách ID / URL** trong khối Thiết lập: dán mỗi dòng một `hotelId` hoặc URL trang
khách sạn Trip.com (`…/hotels/detail/?hotelId=…`, `…-hotel-detail-<id>/…`), hoặc kéo thả
file `.txt` / `.csv` / `.tsv` / `.xlsx` (mọi ô đều được quét, không cần đúng tên cột).
Bấm **Kiểm tra danh sách** → thấy số ID hợp lệ, số đã có đủ trong kho, trùng lặp, dòng
không hiểu, và bảng xem trước. Bấm **Cào N khách sạn trong danh sách** → chạy thẳng bước
cào chi tiết cho đúng các ID đó (không qua bước lấy danh sách theo thành phố, không gọi
`fetchHotelList`), khách sạn ngoài 81 thành phố trong danh mục vẫn cào được; thành phố tự
lấy từ raw. Mặc định bỏ qua khách sạn đã đủ trong kho; tick *Cào lại cả khách sạn đã có*
để ghi đè. API: `POST /api/danh-sach/phan-tich {text}`, `POST /api/danh-sach/tai-file?ten=…`
(body là file), `POST /api/crawl/start-ids {ids, ngon_ngu, cao_lai}`. Tối đa 5.000 ID/lần.

## Kiểm tra trước khi cào

Bấm **Cào dữ liệu** thì app kiểm tra trước (`POST /api/kiem-tra`): Chrome profile, file
cookie (tuổi < 24 giờ), profile đã đăng nhập Trip.com chưa, và gọi thử trang danh sách
bằng httpx để xem Trip.com có trả khách sạn hay đang bắt captcha/chặn IP. Mọi mục OK thì
cào ngay; có cảnh báo thì hiện bảng và nút *Cào ngay* / *Lấy lại cookie*; có mục FAIL
(không kết nối được, captcha) thì khuyên dừng, vẫn có nút *Vẫn cào* nếu cố tình.

## Hàng đợi nhiều thành phố

Chọn thành phố → **＋ Thêm thành phố đang chọn**, lặp lại cho các thành phố khác, rồi
bấm **Cào N thành phố**. App cào lần lượt, nghỉ `QUEUE_PAUSE_SECONDS` (mặc định 60 giây,
gấp 5 nếu vừa bị chặn) giữa hai thành phố. Thành phố đã có raw thì tự chạy ở chế độ cào
tiếp (bỏ qua khách sạn đã đủ). Hàng đợi hiện trong khối tiến độ, bỏ từng thành phố hoặc
**Huỷ hàng đợi**; bấm **Dừng** cũng huỷ luôn phần còn lại. Sau mỗi thành phố, CSV của
thành phố đó được xuất tự động (nếu bật). API: `POST /api/crawl/start` với
`{"city_ids":[58,2],"so_luong":100,"ngon_ngu":["vi","en"]}`, `POST /api/crawl/queue/remove`
`{"id"}`, `POST /api/crawl/queue/clear`.

## Sau khi cào xong

Ngay dưới thanh tiến độ hiện khối kết quả (hoàn tất / chưa đủ / lỗi) với nút **Xuất CSV
ngay**, **Mở file CSV** và **Xem Kho dữ liệu**. Tuỳ chọn *Tự động xuất CSV khi cào xong*
(bật mặc định, nhớ theo máy) sẽ tự tạo file CSV mới trong `output\csv` và hiện thông báo
Windows khi cào xong, kể cả khi cửa sổ app đang ở dưới.

Tab **File CSV** có *Phạm vi xuất*: toàn bộ raw, hoặc tick các thành phố cần xuất
(file đặt tên theo thành phố, ví dụ `trip_property_translation_hong_kong_<thời gian>.csv`).
Xuất tự động sau khi cào chỉ gồm thành phố vừa cào. API: `POST /api/csv/xuat`
với `{}` (tất cả), `{"city_ids":[58]}` hoặc `{"ids":["1971156"]}`.

Khi đang cào, thanh taskbar Windows hiện phần trăm tiến độ và tiêu đề cửa sổ đổi thành
"Đang cào 120/200 (60%)"; xong thì cửa sổ nháy trên taskbar nếu không ở phía trước.

## Xuất CSV: chỉ dữ liệu mới hay gộp tất cả

Tool ghi nhớ khách sạn nào đã nằm trong CSV (`output\trang_thai_xuat_csv.json`, theo
thời điểm raw của từng ngôn ngữ). Ở tab File CSV, mục **Dữ liệu** có 2 lựa chọn:

- **Chỉ dữ liệu mới từ lần xuất trước** (mặc định): chỉ khách sạn được cào hoặc cào lại
  sau lần xuất gần nhất; file đặt tên `..._moi_<phạm vi>_<thời gian>.csv`. Không có gì mới
  thì báo và không tạo file.
- **Gộp tất cả (cũ + mới)**: như trước.

Kết hợp được với "Chỉ thành phố đã chọn". Xuất tự động sau khi cào luôn dùng *chỉ mới +
thành phố vừa cào*, nên file đó đúng bằng phần vừa cào. Nút *Đặt lại dấu đã xuất* để xuất
lại toàn bộ từ đầu. API: `POST /api/csv/xuat {"chi_moi": true, "city_ids": [...]}`.

## Chất lượng dữ liệu trước khi xuất

Tab File CSV hiện khối *Chất lượng dữ liệu trong phạm vi* (theo phạm vi xuất đang chọn):
số khách sạn đủ 3 phần, thiếu mô tả / chính sách / lân cận, raw thiếu packet, chỉ có 1
ngôn ngữ, và số khách sạn có thay đổi so với lần cào trước. Có khách sạn thiếu thì hiện
nút **Cào bù N khách sạn thiếu** (cào lại VI+EN đúng các ID đó) — hoặc cứ xuất phần đang
có. Khối kết quả sau khi cào cũng in một dòng tóm tắt chất lượng của thành phố vừa cào.
API: `GET /api/kho/chat-luong?city_ids=58,2`.

## So sánh với lần cào trước

Mỗi lần ghi raw mới cho một khách sạn đã có raw (cào tiếp, cào bù), app so sánh nội dung
bàn giao (tên, địa chỉ, mô tả; từng mục chính sách; từng địa điểm lân cận + khoảng cách)
và ghi phần khác nhau vào `output\details\changes\<locale>\<currency>\<id>.json`
(chỉ giữ lần gần nhất; giống nhau thì không có file). Trong Kho: chip **Δ n thay đổi**,
bộ lọc *Có thay đổi so với lần cào trước*; trang chi tiết có bảng Trước / Sau.

## Sao lưu & khôi phục

Tab File CSV, khối **Sao lưu & khôi phục**: *Sao lưu ngay* nén `output\` (raw, changes,
cookie, checkpoint, CSV; bỏ recon/html) thành `data\backups\trip-hotel-data_<thời gian>.zip`
(raw `.gz` được lưu thẳng, không nén lại). Danh sách bản sao lưu có 2 nút: *Khôi phục (giữ
file mới hơn)* chỉ thêm file còn thiếu; *Khôi phục ghi đè* thay cả file trùng tên. Không
khôi phục khi đang có tác vụ chạy. API: `GET/POST /api/du-lieu/sao-luu`,
`POST /api/du-lieu/khoi-phuc {ten, ghi_de}`.

## Ngôn ngữ giao diện

Nút **VI / EN** ở thanh điều hướng. Bản EN dịch trực tiếp trên giao diện bằng từ điển
trong `web/assets/i18n.js` (chuỗi đúng-khớp + mẫu regex cho chuỗi có số), áp dụng cả cho
nội dung sinh động (toast, trạng thái, khối kết quả). Không dịch: tên/mô tả/chính sách
khách sạn, log của tiến trình Python, tên file. Thêm chuỗi mới → thêm vào `EXACT` hoặc `RULES`.

## Tự cập nhật ứng dụng

Bản cài dùng `electron-updater` (provider *generic*). Cách phát hành bản mới:

1. Tăng `version` trong `package.json` (vd. 1.2.0) rồi chạy `scripts\build-installer.cmd`.
2. Trong `dist\` có `Trip Hotel Data Setup 1.2.0.exe`, `...exe.blockmap` và `latest.yml`.
   Tải cả 3 file lên một địa chỉ HTTPS tĩnh (web hosting, S3, Cloudflare R2, GitHub Pages…),
   ví dụ `https://ten-mien.com/trip-hotel-data/updates/`.
3. Ghi địa chỉ đó (không có tên file) vào `update-url.txt` **trước khi build** — file này được
   đóng vào `resources\update-url.txt` của bản cài. Máy đã cài sẽ tự kiểm tra khi mở app và
   mỗi 6 giờ; tải xong thì hỏi *Cài ngay và khởi động lại* hoặc *Để sau* (tự cài khi đóng app).

Để trống/`#` trong `update-url.txt` (mặc định) thì tính năng tắt, app chạy như bình thường.
Biến môi trường `TRIP_UPDATE_URL` ghi đè file này. Nhật ký cập nhật nằm trong
`data\output\logs\app.log`. Lần đầu phải `npm install` để có `electron-updater`.

## Nhật ký (log) ra file

- `output\logs\<thời gian>_<crawl|caobu|cookie>.log`: log đầy đủ của từng tác vụ (giống
  khung Nhật ký trong app nhưng không bị cắt 800 dòng). Tự xoá log cũ hơn 30 ngày
  (`LOG_KEEP_DAYS`).
- `output\logs\server.log`: log của backend (request lỗi kèm traceback), xoay khi > 5 MB.
- `output\logs\app.log` (chỉ bản cài): stdout/stderr backend + nhật ký tự cập nhật.
- Chân trang có nút **Mở thư mục log**. Khi mentor báo lỗi, nhờ gửi thư mục này.

## Kho dữ liệu · đối soát · cào bù

Thanh điều hướng trên đầu app có 3 khu vực: **Cào dữ liệu** · **Kho dữ liệu** · **File CSV**.

Tab **Kho dữ liệu** đọc thẳng raw `output/details/raw/<locale>/<currency>/*.json.gz`
(không cần PostgreSQL), mỗi khách sạn một dòng, gộp VI/EN:

- Tìm theo tên/ID, lọc theo thành phố, lọc theo tình trạng thiếu (mô tả, chính sách,
  lân cận, raw thiếu packet, chỉ có 1 ngôn ngữ, raw lỗi).
- Bấm tên khách sạn → trang chi tiết gồm đúng 3 khối bàn giao **DESCRIPTION /
  POLICY / SURROUNDING**, có nút chuyển VI/EN và **Mở trên Trip.com** để đối soát
  với trang thật.
- **Cào bù**: tick chọn khách sạn (hoặc lọc "Thiếu…" rồi "Chọn tất cả"), chọn ngôn
  ngữ, bấm *Cào bù* → app chạy `src/cao_bu.py --ids-file … --languages …`, cào lại
  đúng các ID đó với `--force` và ghi đè raw cũ. Tiến độ hiện ở tab Cào dữ liệu;
  xong thì kho tự làm mới.

Lưu ý: khách sạn "✗ mô tả" nhưng chính sách/lân cận đầy đủ thường là Trip.com
không có mô tả cho khách sạn đó — cào bù lại vẫn trống là bình thường.

API nội bộ: `GET /api/kho/danh-sach`, `GET /api/kho/khach-san/<id>?lang=vi|en`,
`POST /api/kho/cao-bu {ids:[…], ngon_ngu:[…]}`.

## CSV

File dùng UTF-8 có BOM để mở bằng Excel và có đúng 7 cột:

```text
row_uuid, property_id, type, section_type, lang, field, value
```

Logic xuất nằm trong `src/xuat_csv.py`, được giữ theo bản đã đối chiếu với SQL cũ.
