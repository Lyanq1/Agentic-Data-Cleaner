# Tổng hợp

Deduplication Agent trong hệ thống được thiết kế theo mô hình Tool-calling Agent, nghĩa là Agent không trực tiếp nhồi toàn bộ dữ liệu vào prompt của LLM để xử lý vì gây tốn token, tăng chi phí và tràn ngữ cảnh. Thay vào đó, Agent sẽ đọc metadata và kế hoạch xử lý từ Global State, sau đó suy luận để lựa chọn Tool phù hợp, sinh mã thực thi bằng Python/Pandas, và cuối cùng gửi kết quả qua Validator Agent (Pandera) để kiểm chứng tính hợp lệ.

Kiến trúc Deduplication Agent được triển khai theo 3 cấp độ xử lý tăng dần về độ phức tạp.

Cấp độ 1 là Exact Match Deduplication. Ở bước này, Agent sử dụng các hàm Pandas cơ bản như df.drop_duplicates() để xử lý các bản ghi trùng lặp hoàn toàn hoặc trùng trên các trường định danh cứng như số điện thoại hoặc mã khách hàng. Đây là bước xử lý rẻ và nhanh nhất. Sau khi thực thi, dữ liệu sẽ được Validator kiểm tra bằng các quy tắc như Check.isUnique() để đảm bảo dữ liệu đã sạch trước khi chuyển sang bước tiếp theo.

Cấp độ 2 là Fuzzy Blocking bằng MinHash LSH thông qua thư viện datasketch. Mục tiêu của bước này là giải quyết vấn đề độ phức tạp O(n²) khi phải so sánh chéo tất cả bản ghi với nhau trong bài toán fuzzy matching. Thuật toán MinHash sẽ chuyển dữ liệu thành các n-gram (shingles), băm thành các giá trị hash và sử dụng Locality Sensitive Hashing để gom các bản ghi tương tự vào cùng một "bucket". Nhờ vậy, hệ thống chỉ cần tập trung xử lý một số nhóm nghi ngờ thay vì quét toàn bộ dữ liệu. Agent sẽ tự động kích hoạt bước này khi phát hiện các trường văn bản tự do như tên công ty, địa chỉ hoặc họ tên có khả năng sai chính tả hoặc khác định dạng.

Cấp độ 3 là LLM-Assisted Entity Matching. Sau khi MinHash đã khoanh vùng được các nhóm dữ liệu có khả năng trùng lặp, Agent mới sử dụng LLM để xử lý các trường hợp mơ hồ và khó quyết định. Các cặp bản ghi có độ tương đồng rất cao sẽ được tự động gộp, còn các cặp quá khác biệt sẽ bị loại bỏ ngay. Chỉ những trường hợp nằm trong khoảng trung gian (ví dụ độ tương đồng 0.6-0.8) mới được gửi lên LLM để phân tích ngữ nghĩa sâu hơn. LLM đóng vai trò như một nhân viên cấp cao, thực hiện reasoning đa chiều nhằm xác định hai bản ghi có thực sự đại diện cho cùng một thực thể hay không. Cách tiếp cận hybrid này giúp tăng độ chính xác trong Entity Resolution (xử lý trùng lặp dữ liệu) đồng thời giảm đáng kể số lần gọi API và chi phí xử lý.

Ví dụ Entity Resolution:

- Bản ghi 1: Nguyễn Văn An | 0912345678 | Số 1 Đinh Tiên Hoàng, Q.1, HCM
- Bản ghi 2: N. V. An | +84912345678 | D1 Dinh Tien Hoang, Quan 1
- Bản ghi 3: An Nguyen | <an.nguyen@email.com> | (Không có số điện thoại)
- Mặc dù các chuỗi ký tự trông không giống nhau, nhưng entity resolution sẽ phân tích và nhận định cả 3 bản ghi này đều thuộc về cùng một người.

Toàn bộ luồng hoạt động diễn ra như sau: Supervisor giao task cho Deduplication Agent → Agent đọc Global State để xác định chiến lược phù hợp → gọi Exact Match hoặc MinHash hoặc kết hợp MinHash + LLM tùy độ khó → xuất DataFrame mới → chuyển sang Validator Agent để kiểm tra bằng Pandera. Nếu Validator phát hiện lỗi hoặc dữ liệu vi phạm quy tắc, hệ thống sẽ ném Exception để Agent tự động điều chỉnh lại logic xử lý hoặc threshold của MinHash và thực thi lại theo cơ chế self-healing có giới hạn retry.

Ví dụ thực tế: với các bản ghi như "Nguyễn Văn Tèo", "Nguyen Van Teo" hoặc "N.V. Tèo", hệ thống sẽ đầu tiên loại bỏ các dòng trùng hoàn toàn bằng Pandas, sau đó dùng MinHash để gom các dòng có nhiều đặc trưng giống nhau vào cùng một bucket.

Cuối cùng, LLM sẽ phân tích ngữ nghĩa để kết luận rằng đây là cùng một người dựa trên số điện thoại, địa chỉ và biến thể tên gọi. Sau bước này, Validator kiểm tra lại tính duy nhất của dữ liệu trước khi chuyển dataset sạch sang pipeline tiếp theo như Null Handling hoặc Type Casting

Sử dụng datasketch trong trường hợp của mình là:

- Dùng MinHash để băm text của các ô/dòng dữ liệu trong cột.
- Dùng MinHashLSH (hoặc cấu hình AsyncMinHashLSH + Redis nếu dữ liệu lớn) đặt threshold = 0.6.

# Lấy các cặp kết quả trả về, lọc những cặp có điểm tương đồng nằm trong đoạn 0.6 - 0.8 rồi đẩy qua cho Deduplication Agent (LLM) "biện luận đa chiều" để ra quyết định cuối cùng

# I) GIỚI THIỆU

Dựa trên sơ đồ kiến trúc tổng thể (luồng đi từ Planner → Global State →Supervisor → Worker Agents → Validator), Deduplication Agent được thiết kế như một Tool-calling Agent (Tác tử gọi công cụ). không trực tiếp nhồi hàng nghìn dòng dữ liệu vào prompt để hỏi LLM (vì sẽ gây tràn bộ nhớ và tốn kém), mà nó sẽ đọc metadata từ Global State, suy luận để chọn công cụ (Tool) phù hợp, sinh mã thực thi, và gửi kết quả cho Validator (Pandera) kiểm chứng.

# II) Triển khai các bước

## Triển khai chi tiết 3 cấp độ vào Deduplication Agent

### **Cấp độ 1: Khử trùng lặp chính xác (Exact Match)**

- Cách triển khai: Agent được trang bị một Python Tool thực thi các hàm Pandas cơ bản như df.drop_duplicates().
- Quy trình: Khi Planner phân tích Data Profile và ghi chú vào Kế hoạch rằng bộ dữ liệu chỉ có các dòng bị lặp lại hoàn toàn (100% giống nhau) hoặc trùng lặp ở các cột định danh cứng (Mã KH, Số điện thoại), Deduplication Agent sẽ trực tiếp gọi Tool này.
- Khớp nối kiến trúc: Sau khi code chạy xong, dữ liệu được đẩy qua Validator. Pandera sẽ chạy quy tắc isUnique trên các cột định danh để kiểm tra. Nếu qua ải, dữ liệu được khóa cột và đi tiếp.

### **Cấp độ 2: Khoanh vùng xấp xỉ (Fuzzy Blocking) với MinHash LSH**

Thư viện: <https://pypi.org/project/datasketch/>

- Cách triển khai: Trang bị cho Agent một Tool chứa thuật toán MinHash và Locality Sensitive Hashing (LSH).
- Quy trình: Trong kỹ thuật phân giải thực thể, việc so sánh chéo tất cả các dòng dữ liệu với nhau sẽ tạo ra độ phức tạp O(n^2), làm sập hệ thống nếu dữ liệu lớn . MinHash LSH đóng vai trò là bước "Blocking" (Khoanh vùng) . Thuật toán sẽ băm (hash) các đặc trưng văn bản thành các n-gram (shingles) và chia thành các dải (bands) . Những bản ghi có chung mã băm sẽ được ném vào cùng một "xô" (bucket) .
  - Trong xử lý dữ liệu thực tế, việc chọn n-gram N từ 5 đến 9 (đối với ký tự) được coi là "khoảng ngọt" (sweet spot) giúp hệ thống phân biệt chính xác văn bản mà không bị tốn quá nhiều bộ nhớ. (Đọc thêm bên dưới)
- Khi nào Agent gọi: Khi dữ liệu chứa các trường văn bản tự do, địa chỉ hoặc tên công ty dễ gõ sai (VD: "Cong ty ABC" và "Cong ty A.B.C"). Agent sẽ cấu hình tham số nội bộ để lọc ra các cặp bản ghi có độ tương đồng Jaccard cao (ví dụ: ngưỡng > 0.8) \`\`.

### **Cấp độ 3: Phân giải thực thể bằng LLM (LLM-Assisted Entity Matching)**

- Cách triển khai: Sử dụng LLM làm phân tích ngữ nghĩa ở bước "Matching" (Khớp nối) cho các ca khó \`\`.
- Quy trình: Đối với những cặp bản ghi đã được MinHash gom vào cùng một "xô" ở Cấp độ 2 nhưng chưa đủ độ giống nhau để tự động gộp (ví dụ tương đồng ở mức 0.6 - 0.8), Deduplication Agent mới bắt đầu gọi API của LLM. Agent sẽ tạo ra một prompt đưa hai bản ghi này vào và yêu cầu LLM lập luận đa chiều (debate-based reasoning) xem chúng có phải là một thực thể không
  - để xử lý các ca "quá giống" (ví dụ >0.9 thì tự gộp) hoặc "quá khác" (ví dụ <0.6 thì loại luôn). LLM lúc này chỉ đóng vai trò như một "Trọng tài cấp cao" chuyên xử lý các ca nhạy cảm, mập mờ trong khoảng khó (0.6 - 0.8).
- Lợi ích kiến trúc: Nhờ MinHash làm bộ lọc trước, bạn chỉ phải gửi một số lượng cực nhỏ các cặp bản ghi lên LLM. Tăng độ chính xác và giảm số lần gọi LLM

<div class="joplin-table-wrapper"><table><tbody><tr><th><p>ĐỌC THÊM:</p><p>Ví dụ 1: Character-level Shingles (Cắt theo Ký tự)</p><p>Ứng dụng: Thường dùng cho các cột ngắn như Họ tên, Địa chỉ, Tên công ty để bắt lỗi gõ sai chính tả, viết tắt.</p><p>Giả sử trong file Excel của bạn có 2 ô ở cột "Tên Công Ty" bị gõ lệch nhau:</p><ul><li>Ô 1: "VNG Corp"</li><li>Ô 2: "VNG Gorp" <em>(bị gõ sai chữ C thành chữ G)</em></li></ul><p>Chúng ta sẽ dùng 3-gram Shingles (Ký tự), tức là lấy kính lúp độ dài 3 ký tự và trượt dần (tính cả dấu cách _).</p><ul><li>Ô 1 ("VNG Corp"):<ul><li>Trượt: VNG, NG_, G_C, _Co, Cor, orp</li><li>Tập hợp Shingles 1 = {"VNG", "NG_", "G_C", "_Co", "Cor", "orp"}</li></ul></li><li>Ô 2 ("VNG Gorp"):<ul><li>Trượt: VNG, NG_, G_G, _Go, Gor, orp</li><li>Tập hợp Shingles 2 = {"VNG", "NG_", "G_G", "_Go", "Gor", "orp"}</li></ul></li></ul><h3><a id="_x2ah0flb2vsg"></a><strong>Kết quả so sánh toán học (Độ tương đồng Jaccard):</strong></h3><ul><li>Phần giống nhau (Giao nhau): {"VNG", "NG_", "orp"} 3 cụm</li><li>Tổng số cụm không trùng (Hợp nhau): {"VNG", "NG_", "G_C", "_Co", "Cor", "orp", "G_G", "_Go", "Gor"} 9 cụm</li><li>Tỷ lệ tương đồng: 3/9 = 33%</li></ul><p>Dù chỉ sai đúng 1 ký tự (C thành G), nhưng vì cơ chế gối đầu, nó làm sai lệch tới 3 cụm Shingles liên tiếp, kéo độ tương đồng xuống còn 33%. Đó là lý do vì sao trong bài phân tíchi ta thường phải chọn N lớn hơn (từ 5 đến 9) để thuật toán nhận diện mượt mà hơn, tránh bị "nhạy cảm" quá mức với các từ ngắn.</p><p>Ví dụ 2: Word-level Shingles (Cắt theo Từ)</p><p>Ứng dụng: Thường dùng cho các cột chứa chuỗi dài như Mô tả sản phẩm, Địa chỉ chi tiết, hoặc các đoạn văn bản. Ví dụ:</p><ul><li>Địa chỉ 1: "Số 10 Nguyễn Trãi Thanh Xuân"</li><li>Địa chỉ 2: "Thanh Xuân Số 10 Nguyễn Trãi" <em>(Bị đảo thứ tự viết)</em></li></ul><p>Nếu chỉ cắt từ đơn lẻ (1-gram), hai ô này sẽ giống nhau 100%. Nhưng nếu ta dùng 2-gram Shingles (Từ) (ghép từng cặp 2 từ kế tiếp nhau):</p><ul><li>Địa chỉ 1:<ul><li>Cắt cặp: ["Số 10", "10 Nguyễn", "Nguyễn Trãi", "Trãi Thanh", "Thanh Xuân"]</li><li>Tập hợp 1 = {"Số 10", "10 Nguyễn", "Nguyễn Trãi", "Trãi Thanh", "Thanh Xuân"} (5 phần tử)</li></ul></li><li>Địa chỉ 2:<ul><li>Cắt cặp: ["Thanh Xuân", "Xuân Số", "Số 10", "10 Nguyễn", "Nguyễn Trãi"]</li><li>Tập hợp 2 = {"Thanh Xuân", "Xuân Số", "Số 10", "10 Nguyễn", "Nguyễn Trãi"} (5 phần tử)</li></ul></li></ul><h3><a id="_kjr6tpj8t0u9"></a><strong>Kết quả so sánh toán học:</strong></h3><ul><li>Phần giống nhau (Giao nhau): {"Thanh Xuân", "Số 10", "10 Nguyễn", "Nguyễn Trãi"} 4 phần tử</li><li>Tổng số phần tử (Hợp nhau): Gồm 5 phần tử của tập 1 + phần tử "Xuân Số" của tập 2: 6 phần tử</li><li>Tỷ lệ tương đồng: 4/6 = 66%</li></ul><p>Điểm mấu chốt nối vào hệ thống:</p><p>Khi chạy thực tế, toàn bộ quá trình cắt và so sánh thủ công bằng mắt ở trên sẽ được tự động hóa hoàn toàn nhờ thư viện:</p><ol><li>MinHash sẽ biến các tập hợp chữ ({"Số 10", "10 Nguyễn",...}) ở trên thành một dãy số cố định ngắn gọn (Signature).</li><li>Dựa vào dãy số này, MinHashLSH phát hiện ngay cặp Địa chỉ 1 và Địa chỉ 2 có độ tương đồng là 0.66.</li><li>Vì mức 0.66 nằm đúng vào khoảng nghi vấn 0.6 - 0.8 thiết lập à, hệ thống lập tức bốc cặp này cho Deduplication Agent (LLM) kèm prompt: <em>"Hai địa chỉ này bị đảo từ, hãy phân tích xem có phải là cùng một nhà không?"</em>.</li><li>LLM đọc và nhận ra ngay: <em>"Dù đảo từ nhưng cấu trúc số nhà và tên đường giống nhau"</em></li></ol></th></tr></tbody></table></div>

## Tóm tắt luồng đi trong sơ đồ

- Supervisor giao task cho Deduplication Agent.
- Agent đọc Global State, tự động chọn gọi Cấp độ 1, Cấp độ 2, hoặc Cấp độ 2 + 3 tùy theo độ khó của cột dữ liệu.
- Agent xuất ra DataFrame mới, ném qua cho Validator.
- Nếu thuật toán MinHash gom nhầm dữ liệu sai luật, Validator (Pandera) bắn lỗi (Exception). Agent nhận log lỗi, tự động tinh chỉnh lại ngưỡng (threshold) của MinHash hoặc code Pandas và chạy lại.

# III) Ví dụ

Giả sử Supervisor Agent giao cho Deduplication Agent một bảng dữ liệu gồm 5 bản ghi:

- Dòng 1: Nguyễn Văn Tèo | 0901234567 | 123 Lê Lợi, Q1
- Dòng 2: Nguyễn Văn Tèo | 0901234567 | 123 Lê Lợi, Q1 _(Lặp y hệt Dòng 1)_
- Dòng 3: Nguyen Van Teo | 0901234567 | Số 123 đ. Lê Lợi, Quận 1 _(Sai chính tả, khác định dạng)_
- Dòng 4: N.V. Tèo | 0901234567 | 123 Lê Lợi, Q1 _(Tên viết tắt)_
- Dòng 5: Trần Thị Nụ | 0987654321 | 456 Hai Bà Trưng _(Một người hoàn toàn khác)_

### **Giai đoạn 1: Khử trùng lặp chính xác (Exact Match)**

- Hành động của Agent: Agent sinh ra mã Python gọi hàm df.drop_duplicates() của Pandas để quét toàn bộ bảng.
- Chuyện gì xảy ra với dữ liệu: Thuật toán phát hiện Dòng 1 và Dòng 2 giống nhau 100% ở mọi ký tự. Dòng 2 bị xóa bỏ ngay lập tức.
- Kết quả: Còn lại Dòng 1, 3, 4, 5. Phép toán này cực kỳ rẻ và diễn ra trong vài mili-giây.

### **Giai đoạn 2: Khoanh vùng xấp xỉ (Fuzzy Blocking) với MinHash LSH**

Thay vì bắt LLM đọc chéo tất cả các dòng còn lại (rất tốn token), Agent sử dụng Tool MinHash LSH để khoanh vùng.

- Hành động của Agent: Thuật toán chia nhỏ các chuỗi văn bản thành các cụm từ (n-grams), băm (hash) chúng và đẩy những bản ghi có mã băm giống nhau vào chung một "xô" (bucket).
- Chuyện gì xảy ra với dữ liệu:
  - Dòng 1, Dòng 3 và Dòng 4 có chung số điện thoại và chia sẻ nhiều cụm từ giống nhau (như "123", "Lê Lợi", "Teo/Tèo"). MinHash gom 3 dòng này vào chung một "xô" nghi ngờ là trùng lặp.
  - Dòng 5 ("Trần Thị Nụ") có mã băm hoàn toàn khác biệt, bị đưa ra một "xô" riêng và được xác nhận là bản ghi độc lập.
- Kết quả: Thuật toán đã thành công cô lập được một nhóm (Dòng 1, 3, 4) cần phân tích sâu hơn.

### **Giai đoạn 3: Phân giải thực thể bằng LLM (LLM-Assisted Entity Resolution)**

Lúc này, Agent mới dùng đến LLM để làm "Trọng tài" giải quyết nội bộ cái "xô" chứa Dòng 1, 3 và 4.

- Hành động của Agent: Agent đưa các cặp (Dòng 1 - Dòng 3) và (Dòng 1 - Dòng 4) vào Prompt của LLM, yêu cầu LLM tranh luận (debate) xem chúng có phải là một người không.
- Chuyện gì xảy ra với dữ liệu:
  - LLM phân tích Dòng 1 & Dòng 3: _"Cùng số điện thoại. 'Nguyen Van Teo' là phiên bản không dấu của 'Nguyễn Văn Tèo'. 'Số 123 đ. Lê Lợi' cùng nghĩa ngữ cảnh với '123 Lê Lợi'. Kết luận: Trùng lặp."_ → Gộp Dòng 3 vào Dòng 1.
  - LLM phân tích Dòng 1 & Dòng 4: _"Cùng số điện thoại và địa chỉ. 'N.V.' là dạng viết tắt phổ biến của 'Nguyễn Văn'. Kết luận: Trùng lặp."_ → Gộp Dòng 4 vào Dòng 1.
- Kết quả: Nhờ phương pháp làm sạch lai (hybrid) này, hệ thống đã giải quyết được các biến thể tên gọi phức tạp và giảm chi phí gọi API vì Dòng 2 và Dòng 5 không bị đưa vào prompt để hỏi LLM.

### **Giai đoạn 4: Chốt chặn kiểm định (Validator Agent)**

Sau khi Deduplication Agent xử lý xong, bảng dữ liệu lúc này chỉ còn 2 dòng duy nhất sạch sẽ: Dòng 1 (Tèo) và Dòng 5 (Nụ).

- Luồng dữ liệu được đẩy qua Validator Agent (sử dụng thư viện Pandera).
- Pandera chạy quy tắc kiểm tra tĩnh: Check.isUnique("Số điện thoại").
- Vì lúc này cột số điện thoại của Dòng 1 và Dòng 5 đã hoàn toàn khác biệt, Pandera xác nhận "Đúng", không ném ra bất kỳ Exception nào.
- Dữ liệu hợp lệ được Supervisor Agent tiếp nhận để chuẩn bị giao cho trạm tiếp theo (Null Handling Agent) một cách an toàn.

<https://blog.nelhage.com/post/fuzzy-dedup/>

<https://pypi.org/project/datasketch/>