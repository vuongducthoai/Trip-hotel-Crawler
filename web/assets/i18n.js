/* Song ngữ giao diện VI/EN. Cách làm: giữ nguyên chuỗi tiếng Việt trong HTML/JS,
   khi chọn EN thì dịch trực tiếp trên DOM (text node + placeholder/title) bằng từ điển
   chuỗi đúng-khớp và một số mẫu regex cho chuỗi có số/tên. Nội dung dữ liệu (tên khách
   sạn, mô tả, chính sách, log Python) không dịch. */
(() => {
  'use strict';

  const EXACT = {
    // --- điều hướng / chung ---
    '▶ Crawl dữ liệu': '▶ Crawl', '▦ Kho dữ liệu': '▦ Data store', '⇩ File CSV': '⇩ CSV files',
    'Khu vực': 'Sections', 'Ngôn ngữ giao diện': 'Interface language', 'Đóng': 'Close', 'Mở': 'Open',
    'Xem': 'View', 'Xem trước': 'Preview', 'Tải về': 'Download', 'Bắt đầu': 'Started', 'Kết thúc': 'Finished',
    'Thời lượng': 'Duration', 'Trạng thái': 'Status', 'Xem log': 'View log', 'Không có log.': 'No log.',
    'Mở thư mục': 'Open folder', 'Mở thư mục log': 'Open log folder', 'Đổi thư mục…': 'Change folder…', 'Dùng mặc định': 'Use default',
    'Chọn thư mục khác để lưu dữ liệu, ví dụ ngoài thư mục cài đặt để không mất khi gỡ app': 'Pick another folder for data, e.g. outside the install folder so it survives uninstall',
    'Đang khởi động lại với thư mục mới…': 'Restarting with the new folder…', 'Đang khởi động lại…': 'Restarting…', 'Thư mục dữ liệu': 'Data folder', 'Trip Hotel Data · Dữ liệu lưu tại': 'Trip Hotel Data · Data stored at',
    'Thống kê dữ liệu': 'Data stats', 'raw đã lưu': 'raw files saved', 'file CSV': 'CSV files', 'khách sạn': 'hotels',
    'Tiếng Việt': 'Vietnamese', 'English': 'English', 'Ngôn ngữ': 'Languages',
    // --- thiết lập ---
    'Thiết lập lượt cào': 'Crawl setup',
    'Chọn từ 1.050 thành phố quốc tế có sẵn hoặc dán URL tùy biến.': 'Pick one of 1,050 international cities or paste a custom URL.',
    'Chọn điểm đến (1.050 TP)': 'Pick a destination (1,050 cities)', 'Dán URL tùy biến': 'Paste a custom URL',
    'Quốc gia (151 quốc gia)': 'Country (151 countries)', 'Thành phố': 'City', 'URL trang danh sách Trip.com': 'Trip.com hotel list URL',
    'Chọn từ 81 thành phố quốc tế có sẵn hoặc dán URL tùy biến.': 'Pick one of 81 international cities or paste a custom URL.',
    'Chọn điểm đến (81 TP)': 'Pick a destination (81 cities)',
    'Quốc gia (19 quốc gia)': 'Country (19 countries)',
    'Số lượng khách sạn (tổng mục tiêu)': 'Number of hotels (total target)', 'Số lượng khách sạn muốn cào thêm': 'Number of extra hotels to crawl',

    'Gõ tên quốc gia…': 'Type a country…', 'Gõ tên thành phố (vd. hk, ho, bang)…': 'Type a city (e.g. hk, ho, bang)…', 'Gõ để tìm…': 'Type to search…',
    'Không có kết quả.': 'No matches.',
    'Danh sách ID / URL': 'ID / URL list', 'Dán danh sách': 'Paste a list', 'Hướng dẫn': 'Help',
    'Mỗi dòng một khách sạn': 'One hotel per line', ', chấp nhận:': ', accepted:', ' — hotelId (số 4–12 chữ số)': ' — hotelId (4–12 digits)', ' — URL trang khách sạn': ' — hotel page URL',
    ' — nhiều ID trên một dòng, cách nhau bởi dấu phẩy / chấm phẩy / tab': ' — several IDs on one line, separated by comma / semicolon / tab', ' — có chữ kèm theo vẫn nhận số đầu tiên': ' — extra text is fine, the first number is used',
    '• Dòng bắt đầu bằng ': '• Lines starting with ', ' là ghi chú, bị bỏ qua': ' are comments and skipped', 'ID trùng tự gộp; dòng không hiểu sẽ được liệt kê sau khi bấm ': 'Duplicates are merged; unrecognised lines are listed after clicking ',
    'Không cần định dạng đặc biệt.': 'No special format needed.', ' Tool quét ': ' The app scans ', 'mọi ô': 'every cell', ' trong file và nhặt ra hotelId (số 4–12 chữ số) hoặc URL trang khách sạn Trip.com; có dòng tiêu đề hay cột khác cũng không sao.': ' in the file and picks out hotelIds (4–12 digits) or Trip.com hotel URLs; header rows and other columns are fine.',
    ': mỗi dòng một ID/URL': ': one ID/URL per line', ': bất kỳ cột nào, phân cách , ; tab đều được (UTF-8 hoặc Excel)': ': any column, separated by , ; or tab (UTF-8 or Excel)', ': quét mọi sheet, mọi ô; ô số dạng 1.97E+06 vẫn đọc đúng': ': every sheet and cell is scanned; numbers like 1.97E+06 are read correctly',
    'Sau khi đọc, các ID được đổ vào ô dán bên trái để anh kiểm tra/sửa trước khi crawl. Tối đa 5.000 khách sạn một lần, file ≤ 25 MB.': 'After reading, the IDs are placed in the text box on the left so you can review/edit before crawling. Up to 5,000 hotels per run, file ≤ 25 MB.',
    'Hoặc nhập từ file': 'Or import a file', 'Kéo thả file vào đây': 'Drop a file here', 'chọn file': 'browse', 'Crawl lại cả khách sạn đã có đủ trong kho': 'Also re-crawl hotels already complete in the store',
    'Số khách sạn trong danh sách (tự tính)': 'Hotels in the list (auto)', 'Ghi đè khách sạn đã có đủ trong kho (bỏ tick = bỏ qua chúng)': 'Overwrite hotels already complete in the store (untick = skip them)',
    'đang chọn': 'selected', 'mới (chưa có trong kho)': 'new (not in store)', 'đã có đủ · sẽ ghi đè': 'already complete · will overwrite', 'đã có đủ · sẽ bỏ qua': 'already complete · will skip',
    'Chỉ chọn mới': 'Select new only', 'Chỉ chọn đã có': 'Select existing only', 'Bỏ chọn tất cả': 'Deselect all', 'mới': 'new', 'sẽ ghi đè': 'will overwrite',
    'Hãy tick chọn ít nhất một khách sạn trong bảng.': 'Please tick at least one hotel in the table.', 'Kiểm tra danh sách': 'Check list', 'Crawl danh sách': 'Crawl list', 'ID hợp lệ': 'valid IDs', 'đã có đủ trong kho (sẽ bỏ qua)': 'already complete (will skip)', 'đã có đủ trong kho (sẽ crawl lại)': 'already complete (will re-crawl)',
    'trùng lặp đã gộp': 'duplicates merged', 'dòng không hiểu': 'unrecognised lines', 'chưa có trong kho': 'not in store yet', 'Hotel ID': 'Hotel ID', 'Tên (nếu đã có)': 'Name (if known)',
    'Hãy dán ID/URL hoặc nhập file rồi bấm "Kiểm tra danh sách".': 'Paste IDs/URLs or import a file, then click "Check list".', 'Hãy dán danh sách hoặc nhập file trước.': 'Paste a list or import a file first.',
    'Hàng đợi nhiều thành phố': 'Multi-city queue',
    'Chọn thành phố ở trên rồi bấm thêm; app crawl lần lượt, nghỉ 60 giây giữa mỗi thành phố.': 'Pick a city above and add it; cities are crawled one by one with a 60-second pause in between.',
    '＋ Thêm thành phố đang chọn': '＋ Add selected city',
    'Chưa có thành phố nào trong hàng đợi — bấm "Crawl dữ liệu" sẽ crawl thành phố đang chọn.': 'Queue is empty — "Crawl" will crawl the selected city.',
    'Bỏ khỏi hàng đợi': 'Remove from queue', 'Huỷ hàng đợi': 'Clear queue',
    'Kiểm tra trước khi crawl': 'Pre-crawl check', 'Vẫn crawl': 'Crawl anyway', 'Vẫn crawl (không khuyến khích)': 'Crawl anyway (not recommended)',
    'Crawl ngay': 'Crawl now', 'Không nên crawl lúc này': 'Better not to crawl right now', 'Có thể crawl, nhưng lưu ý': 'You can crawl, but note',
    'Mọi thứ sẵn sàng': 'All good', 'Lấy lại cookie': 'Refresh cookies',
    'Dữ liệu đã có': 'Existing data', 'App tự bỏ qua dữ liệu hoàn chỉnh': 'Complete hotels are skipped automatically',
    'Chế độ crawl thêm · không tính lại khách sạn đã đủ': 'Continue mode · complete hotels are not counted again',
    'Thoát chế độ crawl tiếp': 'Exit continue mode', 'Đang kiểm tra dữ liệu đã lưu…': 'Checking saved data…',
    'Chọn ngôn ngữ để xem thống kê.': 'Pick a language to see stats.',
    'Crawl dữ liệu': 'Crawl', 'Crawl tiếp dữ liệu': 'Continue crawling', 'Dừng': 'Stop',
    'Tự động xuất CSV khi crawl xong': 'Export CSV automatically when done',
    'Chrome sẽ mở khoảng 45 giây khi lấy cookie.': 'Chrome opens for about 45 seconds to fetch cookies.',
    'Đang kiểm tra…': 'Checking…',
    // --- tiến độ ---
    'Tiến độ trực tiếp': 'Live progress', 'Chưa có tác vụ đang chạy.': 'No task running.', 'Sẵn sàng': 'Ready',
    'Đang chạy': 'Running', 'Đang dừng': 'Stopping', 'Thành công': 'Success', 'Chưa đủ': 'Incomplete', 'Đã dừng': 'Stopped', 'Có lỗi': 'Failed',
    'Đang thực hiện…': 'Working…', 'Nhật ký tác vụ': 'Task log', 'Sao chép log': 'Copy log', 'Chưa chạy tác vụ nào.': 'No task has run yet.',
    'Crawl xong': 'Crawl finished', '⇩ Xuất CSV ngay': '⇩ Export CSV now', '⇩ Xuất CSV lại': '⇩ Export CSV again', 'Mở file CSV': 'Open CSV file',
    'Xem Kho dữ liệu': 'Open data store', 'Đang xuất CSV…': 'Exporting CSV…',
    'Xem nhật ký bên dưới để biết nguyên nhân. Dữ liệu đã crawl trước khi dừng vẫn được giữ.': 'See the log below for the cause. Data crawled before the stop is kept.',
    // --- CSV ---
    'File kết quả': 'Output files', 'CSV gồm đúng 7 cột theo cấu trúc bàn giao.': 'CSV with exactly the 7 hand-over columns.',
    'Xuất CSV': 'Export CSV', 'Xuất SQL': 'Export SQL', 'Đang xuất…': 'Exporting…',
    'Định dạng SQL (PostgreSQL) — bảng': 'SQL format (PostgreSQL) — table', 'Tên bảng': 'Table name',
    'ON CONFLICT (row_uuid, lang, field) DO UPDATE — nạp lại nhiều lần không trùng': 'ON CONFLICT (row_uuid, lang, field) DO UPDATE — safe to load repeatedly',
    'Thêm CREATE TABLE IF NOT EXISTS ở đầu file (DB trống)': 'Prepend CREATE TABLE IF NOT EXISTS (empty database)',
    'Mỗi bản ghi một câu INSERT (giống mẫu cũ; mặc định gộp 500 bản ghi/câu)': 'One INSERT per record (like the old sample; default batches 500 per statement)',
    'TripAdvisor — field': 'TripAdvisor — field', 'chưa có API key': 'no API key yet', 'Tripadvisor Content API key': 'Tripadvisor Content API key',
    'Dán API key rồi bấm Lưu': 'Paste the API key and click Save', 'Lưu': 'Save',
    'Chưa có key — field tripAdvisorId sẽ bị bỏ trống khi xuất.': 'No key yet — tripAdvisorId will be left empty on export.',
    'Tự ghép TripAdvisor ngay sau khi crawl xong (chỉ khách sạn chưa ghép)': 'Match TripAdvisor automatically right after a crawl (unmatched hotels only)',
    'Ghép lại cả khách sạn đã có kết quả': 'Re-match hotels that already have a result',
    '⇄ Ghép TripAdvisor theo phạm vi trên': '⇄ Match TripAdvisor for the scope above',
    'đã ghép (matched)': 'matched', 'cần xem lại': 'needs review', 'TripAdvisor không có': 'not on TripAdvisor', 'lỗi': 'errors', 'chưa ghép': 'not matched yet',
    'Ghép TripAdvisor · hoàn tất': 'TripAdvisor matching · finished', 'Ghép TripAdvisor · dừng sớm': 'TripAdvisor matching · stopped early',
    'Ghép bằng Tripadvisor Content API (tên + toạ độ Trip.com), ~2 lần gọi/khách sạn, hạn mức ~10.000 lần/ngày. Chỉ trạng thái "matched" mới được xuất ID; "review" xem lại trong Kho.': 'Matched through the Tripadvisor Content API (name + Trip.com coordinates), ~2 calls per hotel, quota ~10,000 calls/day. Only "matched" hotels get an exported ID; "review" ones are listed in the Data store for a manual check.',
    'Xuất CSV/SQL để có field tripAdvisorId; khách sạn "review" xem lại trong Kho.': 'Export CSV/SQL to get the tripAdvisorId field; check "review" hotels in the Data store.',
    'Đã ghép — tên và vị trí đều khớp, ID sẽ được xuất': 'Matched — name and location both agree; the ID will be exported',
    'Cần xem lại — tên hoặc vị trí chưa khớp hẳn, ID KHÔNG được xuất': 'Needs review — name or location does not fully agree; the ID is NOT exported',
    'TripAdvisor không có khách sạn phù hợp quanh đây': 'No matching hotel on TripAdvisor nearby', 'Gọi API lỗi — sẽ thử lại ở lần ghép sau': 'API error — will retry on the next matching run',
    'Chưa ghép. Bấm "Ghép TripAdvisor" ở tab File CSV (cần API key), hoặc crawl lại khách sạn này.': 'Not matched yet. Click "Match TripAdvisor" in the CSV tab (API key required) or re-crawl this hotel.',
    'Tên Trip.com': 'Trip.com name', 'Tên TripAdvisor': 'TripAdvisor name', 'Độ giống tên': 'Name similarity', 'Khoảng cách': 'Distance', 'Đánh giá': 'Rating', 'Ghép lúc': 'Matched at', 'Lỗi': 'Error',
    '(ghép khi ≥ 80%)': '(matched at ≥ 80%)', '(ghép khi ≤ 300 m)': '(matched at ≤ 300 m)', 'Mở trang TripAdvisor để đối chiếu ↗': 'Open the TripAdvisor page to compare ↗',
    'TripAdvisor: chưa ghép': 'TripAdvisor: not matched yet', 'TripAdvisor: lỗi ghép': 'TripAdvisor: match error', 'TripAdvisor: không có': 'TripAdvisor: not found',
    'Tự động xuất khi crawl xong': 'Export automatically when crawl finishes', 'Định dạng xuất tự động': 'Auto-export format',
    '⇩ Xuất file ngay': '⇩ Export now', 'Mở file vừa xuất': 'Open exported file', '⇩ Xuất lại': '⇩ Export again', 'XEM TRƯỚC SQL': 'SQL PREVIEW', 'Phạm vi xuất': 'Export scope', 'Tất cả khách sạn đã crawl': 'All crawled hotels',
    'Dấu "đã xuất CSV"': '"Exported to CSV" marks', 'Tool nhớ khách sạn nào đã nằm trong CSV để lần sau chỉ xuất phần mới. Bình thường không cần đụng vào.': 'The app remembers which hotels are already in a CSV so the next export can include only new ones. Normally you never need to touch this.',
    '✓ Đánh dấu tất cả là đã xuất': '✓ Mark all as exported', '↺ Quên dấu đã xuất (xuất lại từ đầu)': '↺ Forget exported marks (export everything again)',
    'Đã quên dấu đã xuất — mọi khách sạn giờ là "mới".': 'Exported marks forgotten — every hotel is now "new".',
    'Coi như chưa xuất khách sạn nào; lần xuất \'chỉ mới\' kế tiếp sẽ gồm toàn bộ': 'Treat every hotel as not yet exported; the next "only new" export includes everything',
    'Dữ liệu': 'Data', 'Phạm vi': 'Scope', 'Chỉ dữ liệu mới từ lần xuất trước': 'Only new since last export', 'Gộp tất cả (cũ + mới)': 'Everything (old + new)', 'Mọi thành phố': 'All cities',
    'Chỉ thành phố đã chọn': 'Selected cities only', 'Chưa có file CSV.': 'No CSV files yet.',
    'Chưa có file CSV. Sau khi crawl xong, bấm “Xuất CSV”.': 'No CSV files yet. After crawling, click "Export CSV".',
    'Chất lượng dữ liệu trong phạm vi': 'Data quality in scope', '↻ Crawl bù khách sạn thiếu': '↻ Re-crawl missing hotels',
    'đủ 3 phần': 'complete (3 parts)', 'thiếu mô tả': 'missing description', 'thiếu chính sách': 'missing policies', 'thiếu lân cận': 'missing nearby places',
    'raw thiếu packet': 'raw missing packet', 'chỉ 1 ngôn ngữ': 'one language only', 'có thay đổi so với lần trước': 'changed since last crawl',
    'Sao lưu & khôi phục': 'Backup & restore', '⛁ Sao lưu ngay': '⛁ Back up now', 'Đang nén…': 'Zipping…',
    'Nén toàn bộ dữ liệu đã crawl (raw, thay đổi, cookie, CSV) thành một file zip. Nên sao lưu trước khi cập nhật hoặc gỡ ứng dụng.': 'Zips all crawled data (raw, changes, cookies, CSV) into one file. Back up before updating or uninstalling the app.',
    'Chưa có bản sao lưu.': 'No backups yet.', 'Khôi phục (giữ file mới hơn)': 'Restore (keep newer files)', 'Khôi phục ghi đè': 'Restore & overwrite',
    'Xoá': 'Delete', 'Xoá tất cả CSV': 'Delete all CSV', 'Xoá tất cả file': 'Delete all files', 'CSV hoặc SQL dump (PostgreSQL), đúng 7 cột theo cấu trúc bàn giao.': 'CSV or SQL dump (PostgreSQL), exactly the 7 hand-over columns.', 'XEM TRƯỚC CSV': 'CSV PREVIEW', '✓ Đã tải': '✓ Downloaded', 'Mới nhất': 'Latest',
    // --- thành phố đã crawl / lịch sử ---
    'Thành phố đã crawl': 'Crawled cities', 'Tổng hợp từ raw và checkpoint đang lưu trên máy.': 'Summarised from raw files and checkpoints on this computer.',
    'Tìm thành phố, quốc gia, mã…': 'Search city, country, id…', 'Chưa có thành phố nào.': 'No cities yet.', 'Không có thành phố nào khớp.': 'No city matches.',
    'Chưa có thành phố nào trong dữ liệu raw.': 'No cities in raw data yet.', 'khách sạn raw': 'raw hotels', 'ID đã biết': 'Known IDs', 'Crawl tiếp': 'Continue', 'Crawl thêm': 'Crawl more', 'Crawl': 'Crawl',
    'Lịch sử hoạt động': 'Activity history', 'Lịch sử được giữ lại sau khi đóng và mở lại ứng dụng.': 'History is kept after closing and reopening the app.',
    'Xóa lịch sử': 'Clear history', 'Chưa có lịch sử.': 'No history yet.', 'Chưa có lịch sử. Các lượt hoàn tất sẽ xuất hiện tại đây.': 'No history yet. Finished runs appear here.',
    'LỊCH SỬ TÁC VỤ': 'TASK HISTORY', 'XEM CHI TIẾT': 'DETAILS', 'Chi tiết': 'Details',
    // --- kho ---
    'Kho dữ liệu đã crawl': 'Crawled data store',
    'Đối soát mô tả · chính sách · lân cận với trang Trip.com thật, và crawl bù phần còn thiếu.': 'Cross-check description · policies · nearby places against the live Trip.com page, and re-crawl what is missing.',
    '↻ Quét lại': '↻ Rescan', 'Crawl bù': 'Re-crawl', 'có bản VI': 'with VI', 'có bản EN': 'with EN', 'thiếu dữ liệu': 'missing data',
    'Tìm theo tên hoặc mã khách sạn…': 'Search by hotel name or id…', 'Tất cả thành phố': 'All cities', 'Tất cả khách sạn': 'All hotels',
    'Thiếu do crawl (nên crawl bù)': 'Missing due to crawl (re-crawl)', 'Thiếu mô tả (do crawl)': 'Missing description (crawl)', 'Thiếu chính sách (do crawl)': 'Missing policies (crawl)', 'Thiếu lân cận (do crawl)': 'Missing nearby places (crawl)',
    'Trip.com không có mô tả / CS / LC': 'Not provided by Trip.com (desc / policies / nearby)', 'thiếu do crawl': 'missing (crawl)',
    '— không có mô tả': '— no description', '— không có CS': '— no policies', '— không có LC': '— no nearby',
    'Trip.com không có mô tả': 'no description on Trip.com', 'Trip.com không có chính sách': 'no policies on Trip.com', 'Trip.com không có lân cận': 'no nearby places on Trip.com',
    'Trip.com không cung cấp phần này cho khách sạn (đã crawl đủ, không phải crawl thiếu)': 'Trip.com does not provide this for the hotel (fully crawled, not a crawl gap)',
    'Raw chưa đủ packet — nên crawl bù': 'Raw is missing a packet — re-crawl recommended',
    'Trip.com không có mô tả cho khách sạn này (đã crawl đủ packet — không phải crawl thiếu).': 'Trip.com has no description for this hotel (fully crawled — not a crawl gap).',
    'Trip.com không có chính sách cho khách sạn này (đã crawl đủ packet).': 'Trip.com has no policies for this hotel (fully crawled).',
    'Trip.com không có địa điểm lân cận cho khách sạn này (đã crawl đủ packet).': 'Trip.com has no nearby places for this hotel (fully crawled).',
    'Chưa crawl được phần mô tả (raw chưa đủ packet — nên crawl bù).': 'Description not crawled (raw missing a packet — re-crawl).',
    'Chưa crawl được chính sách (raw chưa đủ packet — nên crawl bù).': 'Policies not crawled (raw missing a packet — re-crawl).',
    'Chưa crawl được địa điểm lân cận (raw chưa đủ packet — nên crawl bù).': 'Nearby places not crawled (raw missing a packet — re-crawl).',
    'Thiếu bất kỳ': 'Missing anything', 'Thiếu mô tả': 'Missing description', 'Thiếu chính sách': 'Missing policies', 'Thiếu lân cận': 'Missing nearby places',
    'Raw chưa đủ (thiếu packet)': 'Raw incomplete (missing packet)', 'Chỉ có 1 ngôn ngữ': 'One language only', 'Raw lỗi, không đọc được': 'Raw unreadable',
    'Có thay đổi so với lần crawl trước': 'Changed since last crawl', 'Crawl bù cho': 'Re-crawl for',
    'Chưa chọn khách sạn nào.': 'No hotel selected.', 'Tick chọn khách sạn cần crawl lại, hoặc dùng bộ lọc "Thiếu…" rồi "Chọn tất cả".': 'Tick hotels to re-crawl, or use a "Missing…" filter then "Select all".',
    'Khách sạn': 'Hotel', 'Cập nhật': 'Updated', 'Đang đọc kho…': 'Reading store…', 'Không có khách sạn nào khớp bộ lọc.': 'No hotel matches the filter.',
    'Hiện thêm': 'Show more', '✓ mô tả': '✓ description', '✗ mô tả': '✗ description', 'thiếu packet': 'missing packet', 'raw lỗi': 'raw error',
    '← Danh sách': '← List', '↻ Crawl bù khách sạn này': '↻ Re-crawl this hotel', 'Mở trên Trip.com ↗': 'Open on Trip.com ↗', 'Chọn một khách sạn.': 'Pick a hotel.',
    'Đang đọc raw…': 'Reading raw…', 'Chưa crawl ngôn ngữ này': 'Not crawled in this language', 'Đủ 3 phần': 'All 3 parts', 'Raw thiếu packet': 'Raw missing packet',
    'Chưa có địa chỉ': 'No address', '(chưa có tên)': '(no name)', 'Mô tả': 'Description', 'Mô tả khách sạn': 'Hotel description', 'Chính sách': 'Policies',
    'Địa điểm lân cận': 'Nearby places', 'Thay đổi': 'Changes', 'SO VỚI LẦN CRAWL TRƯỚC': 'VS PREVIOUS CRAWL', 'Phần': 'Part', 'Mục': 'Item', 'Trước': 'Before', 'Sau': 'After',
    'Chưa crawl được phần mô tả.': 'Description not crawled.', 'Chưa crawl được chính sách.': 'Policies not crawled.', 'Chưa crawl được địa điểm lân cận.': 'Nearby places not crawled.',
    'thêm': 'added', 'bỏ': 'removed', 'đổi': 'changed', 'đi bộ': 'walk', 'lái xe': 'drive', 'đường thẳng': 'straight line',
  };

  // Mẫu có số / tên: [regex, thay thế]. Chạy sau khi không khớp EXACT.
  const RULES = [
    [/^Ghép TripAdvisor (\d[\d.,]*) khách sạn$/, 'Match TripAdvisor for $1 hotels'],
    [/^([\d.]+)★ · (\d[\d.,]*) lượt$/, '$1★ · $2 reviews'],
    [/^Ghép TripAdvisor · (\d[\d.,]*) khách sạn( · ghép lại)?$/, (m, n, r) => `TripAdvisor matching · ${n} hotels${r ? ' · re-match' : ''}`],
    [/^(\d[\d.,]*)\/(\d[\d.,]*) đã ghép · (\d[\d.,]*) chưa ghép$/, '$1/$2 matched · $3 not matched yet'],
    [/^Đang dùng key (\S+)\. Kết quả lưu trong (.+)\.$/, 'Using key $1. Results stored in $2.'],
    [/^TripAdvisor: cần xem lại \((\d*)\)$/, 'TripAdvisor: needs review ($1)'],
    [/^(\d[\d.,]*) raw đã lưu$/, '$1 raw files saved'],
    [/^(\d[\d.,]*) thành phố$/, '$1 cities'],
    [/^Crawl (\d+) thành phố$/, 'Crawl $1 cities'],
    [/^Chọn tất cả đang hiện \($/, 'Select all shown ('],
    [/^Hiện thêm \((\d[\d.,]*) còn lại\)$/, 'Show more ($1 left)'],
    [/^(\d[\d.,]*) mục$/, '$1 items'],
    [/^(\d[\d.,]*) địa điểm · (\d+) nhóm$/, '$1 places · $2 groups'],
    [/^Chính sách \((\d+)\)$/, 'Policies ($1)'], [/^Lân cận \((\d+)\)$/, 'Nearby ($1)'],
    [/^(\d[\d.,]*) ký tự$/, '$1 characters'],
    [/^Crawl lúc (.+?)( · (\d[\d.,]*) phòng)?$/, (m, t, _r, n) => `Crawled ${t}${n ? ` · ${n} rooms` : ''}`],
    [/^Δ (\d+) thay đổi$/, 'Δ $1 changes'], [/^(\d+) mục · lúc (.+)$/, '$1 items · at $2'],
    [/^— chưa crawl (VI|EN)$/, '— no $1 crawl'],
    [/^▤ (\d+) CS$/, '▤ $1 pol'], [/^⌖ (\d+) LC$/, '⌖ $1 near'],
    [/^Đã chọn (\d[\d.,]*) khách sạn · crawl bù (.+)$/, 'Selected $1 hotels · re-crawl $2'],
    [/^(\d[\d.,]*) khách sạn · (\d+) thành phố$/, '$1 hotels · $2 cities'], [/^(\d[\d.,]*) khách sạn · toàn bộ kho$/, '$1 hotels · whole store'],
    [/^(\d[\d.,]*) khách sạn thiếu dữ liệu \(VI (\d+), EN (\d+)\)\. .*$/, '$1 hotels are missing data (VI $2, EN $3). Re-crawl them before exporting for a fuller CSV — or export what you have.'],
    [/^↻ Crawl bù (\d[\d.,]*) khách sạn thiếu$/, '↻ Re-crawl $1 missing hotels'],
    [/^Lưu tại (.+)$/, 'Stored at $1'],
    [/^(.+?) · bắt đầu (.+)$/, '$1 · started $2'],
    [/^(\d+) phút (\d+) giây$/, '$1 min $2 s'], [/^(\d+) giây$/, '$1 s'],
    [/^Crawl (\d+) khách sạn trong danh sách$/, 'Crawl $1 listed hotels'], [/^Crawl (\d+) khách sạn đã chọn$/, 'Crawl $1 selected hotels'],
    [/^Chọn tất cả \($/, 'Select all ('], [/^… và (\d+) ID nữa \(vẫn được tick theo "Chọn tất cả"\)\.$/, '… and $1 more IDs (still ticked via "Select all").'],
    [/^Crawl danh sách (\d+) khách sạn · hoàn tất$/, 'Crawl list of $1 hotels · finished'], [/^Crawl danh sách (\d+) khách sạn · chưa đủ số lượng$/, 'Crawl list of $1 hotels · incomplete'], [/^Crawl danh sách (\d+) khách sạn · dừng vì lỗi$/, 'Crawl list of $1 hotels · stopped on error'],
    [/^Crawl danh sách (\d+) khách sạn(.*)$/, 'Crawl list of $1 hotels$2'],
    [/^Đang crawl (\d+) khách sạn trong danh sách\.$/, 'Crawling $1 listed hotels.'],
    [/^(.+) · (\d+) dòng · (\d+) ID$/, '$1 · $2 lines · $3 IDs'], [/^Đang đọc (.+)…$/, 'Reading $1…'], [/^Không hiểu: (.+)$/, 'Unrecognised: $1'], [/^… và (\d+) ID nữa\.$/, '… and $1 more IDs.'],
    [/^(VI|EN) (đủ|thiếu)$/, (m, l, st) => `${l} ${st === 'đủ' ? 'complete' : 'missing'}`],
    [/^Crawl (.+) · hoàn tất$/, 'Crawl $1 · finished'], [/^Crawl (.+) · chưa đủ số lượng$/, 'Crawl $1 · fewer than requested'], [/^Crawl (.+) · dừng vì lỗi$/, 'Crawl $1 · stopped on error'],
    [/^Crawl bù (\d+) khách sạn · hoàn tất$/, 'Re-crawl $1 hotels · finished'], [/^Crawl bù (\d+) khách sạn · chưa đủ số lượng$/, 'Re-crawl $1 hotels · incomplete'], [/^Crawl bù (\d+) khách sạn · dừng vì lỗi$/, 'Re-crawl $1 hotels · stopped on error'],
    [/^Đã crawl (\d[\d.,]*)\/(\d[\d.,]*) lượt\. Dữ liệu nằm trong Kho, sẵn sàng xuất CSV\.(.*)$/, (m, a, b, rest) => `Crawled ${a}/${b}. Data is in the store, ready to export.${rest}`],
    [/^Trip\.com chỉ cung cấp (\d[\d.,]*)\/(\d[\d.,]*) lượt\..*?(Đã tự xuất .+)?$/, (m, a, b, rest) => `Trip.com only returned ${a}/${b}. What was crawled is usable; click "Continue" in a few minutes to get more.${rest ? ' ' + rest : ''}`],
    [/Đã tự xuất (\S+) \(chỉ gồm phần vừa crawl; vì vậy huy hiệu "mới" ở tab CSV về 0\)\./, 'Auto-exported $1 (only what was just crawled, so the "new" badge in the CSV tab drops to 0).'],
    [/Đã tự xuất (\S+)\./, 'Auto-exported $1.'],
    [/Chất lượng: (\d+)\/(\d+) đủ 3 phần; (.+?) \(xem tab File CSV để crawl bù\)\./, 'Quality: $1/$2 complete; $3 (see CSV tab to re-crawl).'],
    [/Chất lượng: (\d+)\/(\d+) khách sạn đủ 3 phần\./, 'Quality: $1/$2 hotels complete.'],
    [/(\d+) thiếu mô tả/g, '$1 missing description'], [/(\d+) thiếu chính sách/g, '$1 missing policies'], [/(\d+) thiếu lân cận/g, '$1 missing nearby places'], [/(\d+) có thay đổi so với lần trước/g, '$1 changed since last crawl'],
    [/^Còn (\d+) thành phố chờ sau tác vụ này$/, '$1 more cities queued after this task'],
    [/^Nghỉ (\d+) giây rồi crawl tiếp (.+)$/, 'Pausing $1 s, then crawling $2'], [/^Chuẩn bị crawl (.+)$/, 'Preparing to crawl $1'],
    [/^(VI|EN|Tiếng Việt|English): đã có (\d+) · tìm thêm (\d+) → mục tiêu (\d+)(.*)$/, '$1: have $2 · find $3 more → target $4$5'],
    [/^(VI|EN|Tiếng Việt|English): (\d+) hoàn chỉnh · còn (\d+) để đạt (\d+)(.*)$/, '$1: $2 complete · $3 to reach $4$5'],
    [/ · (\d+) raw cũ sẽ crawl lại/, ' · $1 old raw files will be re-crawled'],
    [/^(.+?) · có thể tiếp tục lượt trước$/, '$1 · can continue previous run'],
    [/^(\d+)\/(\d+) đủ$/, '$1/$2 complete'], [/^Cập nhật (.+)$/, 'Updated $1'],
    [/^Tổng (\d[\d.,]*) dòng · đang hiển thị tối đa (\d+) dòng đầu\.$/, '$1 rows in total · showing at most the first $2.'],
    [/^URL tự sinh: (.+)$/, 'Generated URL: $1'],
    [/^Đang crawl bù (\d[\d.,]*) khách sạn \((.+)\)\. Theo dõi ở tab Crawl dữ liệu\.$/, 'Re-crawling $1 hotels ($2). Follow it in the Crawl tab.'],
    [/^Đã xếp (\d+) thành phố vào hàng đợi\.$/, 'Queued $1 cities.'], [/^Đã tạo (.+)$/, 'Created $1'],
    [/^Đã sao lưu (\d+) file → (.+)$/, 'Backed up $1 files → $2'], [/^Đã khôi phục (\d+) file, bỏ qua (\d+) file đã có\.$/, 'Restored $1 files, skipped $2 existing.'],
    [/^Đang tìm và crawl thêm (\d+) khách sạn\.$/, 'Searching for and crawling $1 more hotels.'], [/^Đã bắt đầu crawl dữ liệu\.$/, 'Crawl started.'],
    [/^Đã bật crawl tiếp (.+)\. Nhập số lượng muốn crawl thêm\.$/, 'Continue mode on for $1. Enter how many more to crawl.'],
    [/^(.+) đã có trong hàng đợi\.$/, '$1 is already queued.'], [/^Đã huỷ hàng đợi\.$/, 'Queue cleared.'],
    [/^Hãy chọn ít nhất một ngôn ngữ\.$/, 'Please pick at least one language.'], [/^Số lượng khách sạn không hợp lệ\.$/, 'Invalid number of hotels.'],
    [/^Hãy chọn thành phố trong danh mục\.$/, 'Please pick a city from the catalogue.'], [/^Hãy dán URL trang danh sách Trip\.com\.$/, 'Please paste a Trip.com list URL.'],
    [/^Hãy tick ít nhất một thành phố để xuất\.$/, 'Please tick at least one city to export.'], [/^Hãy chọn thành phố trước\.$/, 'Please pick a city first.'],
    [/^Không kiểm tra được \((.+)\); crawl luôn\.$/, 'Check failed ($1); crawling anyway.'],
    [/^Lỗi (\d+)$/, 'Error $1'],
    [/^Đã đánh dấu (\d+) khách sạn là đã xuất\.$/, 'Marked $1 hotels as exported.'],
    [/^⇩ Xuất (SQL|CSV|SQL \+ CSV) ngay$/, '⇩ Export $1 now'],
    [/^(\d[\d.,]*) mới$/, '$1 new'], [/^(\d[\d.,]*) mới \/ (\d[\d.,]*)$/, '$1 new / $2'],
    [/^(\d[\d.,]*) khách sạn mới chưa xuất \(trên (\d[\d.,]*)\) · (\d+) thành phố$/, '$1 new, not yet exported (of $2) · $3 cities'],
    [/^(\d[\d.,]*) khách sạn mới chưa xuất \(trên (\d[\d.,]*)\) · toàn bộ kho$/, '$1 new, not yet exported (of $2) · whole store'],
    [/^Không có khách sạn mới kể từ lần xuất trước — .*$/, 'No new hotels since the last export — everything in this scope is already in a CSV. Choose "Everything" to export again.'],
    [/^Không có khách sạn mới nào kể từ lần xuất trước trong phạm vi này\.$/, 'No new hotels since the last export in this scope.'],
    [/^KHÁCH SẠN · ID (\d+) · (.+)$/, 'HOTEL · ID $1 · $2'],
    [/^(\d+) cảnh báo khi bóc raw$/, '$1 warnings while parsing raw'],
    [/^Nhóm (\d+)$/, 'Group $1'],
    [/^Trip\.com không có: (.+)$/, 'Not on Trip.com: $1'], [/^Thiếu: (.+)$/, 'Missing: $1'],
    [/(\d+) Trip\.com không có mô tả/g, '$1 without description on Trip.com'],
    [/^Đã xoá (\d+) file\.$/, 'Deleted $1 files.'], [/^Đã xoá (.+)$/, 'Deleted $1'],
    [/ · Mới nhất/, ' · Latest'], [/ · Đã tải (.+)$/, ' · Downloaded $1'],
    [/^Chọn từ (\d[\d.,]*) thành phố quốc tế có sẵn hoặc dán URL tùy biến\.$/, 'Pick one of $1 international cities or paste a custom URL.'],
    [/^Chọn điểm đến \((\d[\d.,]*) TP\)$/, 'Pick a destination ($1 cities)'],
    [/^Quốc gia \((\d+) quốc gia\)$/, 'Country ($1 countries)'],
  ];

  const SKIP = 'pre, code, #log, .mono, .combo-list, .col-name, .detail-text, .policy-body, .policy-name h4, .nearby-list, .changes-table td, .file-info strong, .city-card-title strong, .detail-head h2, .detail-sub, #data-dir, #destination-preview-url, .schema';

  function translate(text) {
    const trimmed = text.trim();
    if (!trimmed) return null;
    if (EXACT[trimmed] !== undefined) return EXACT[trimmed];
    let out = trimmed;
    let hit = false;
    for (const [re, rep] of RULES) {
      if (re.test(out)) {
        out = out.replace(re, rep);
        hit = true;
        if (!re.global) break;
      }
      if (re.global) re.lastIndex = 0;
    }
    return hit ? out : null;
  }

  function translateNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const parent = node.parentElement;
      if (!parent || parent.closest(SKIP)) return;
      const raw = node.nodeValue;
      const t = translate(raw);
      if (t !== null && t !== raw.trim()) node.nodeValue = raw.replace(raw.trim(), t);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    for (const attr of ['placeholder', 'title', 'aria-label']) {
      const v = node.getAttribute(attr);
      if (v) { const t = translate(v); if (t !== null) node.setAttribute(attr, t); }
    }
    if (node.closest(SKIP)) return;
    if (node.tagName === 'OPTION') {
      // option thành phố/quốc gia (value là số hoặc tên nước) giữ nguyên; option bộ lọc dịch.
      if (node.value === '' || !/^\d+$/.test(node.value) && node.parentElement && node.parentElement.id === 'kho-filter') {
        const t = translate(node.textContent);
        if (t !== null) node.textContent = t;
      }
      return;
    }
    node.childNodes.forEach(translateNode);
  }

  let lang = 'en';
  try { lang = localStorage.getItem('ui-lang') || 'en'; } catch (_) { /* không có localStorage */ }

  const observer = new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === 'characterData') translateNode(r.target);
      r.addedNodes.forEach(translateNode);
    }
  });

  window.I18N = {
    get lang() { return lang; },
    t: (s) => (lang === 'en' ? (translate(s) ?? s) : s),
    set(next) {
      if (next === lang) return;
      try { localStorage.setItem('ui-lang', next); } catch (_) { /* bỏ qua */ }
      window.location.reload();   // dịch lại từ đầu: đơn giản và chắc chắn
    },
  };

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-ui-lang]').forEach((b) => {
      b.classList.toggle('active', b.dataset.uiLang === lang);
      b.addEventListener('click', () => window.I18N.set(b.dataset.uiLang));
    });
    if (lang !== 'en') return;
    document.documentElement.lang = 'en';
    translateNode(document.body);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  });
})();
