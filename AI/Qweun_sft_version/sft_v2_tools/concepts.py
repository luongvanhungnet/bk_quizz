"""Curated named-concept vocabulary; reject pronouns, captions, author names and fragments.

This is editorial filtering, not expert certification of every source definition.
Canonical spacing corrects joined words in labels only; evidence bytes stay exact.
"""
import re
from common import norm

NAMES = """
ICT|Communication|CSDL|CSDL công ty|CSDL phân tán|DBMS engine|Desktop|Directory server|Giao thức|Hệ thống con thao tác dữ liệu|Hệ thống con tạo ứng dụng|Hệ thống con định nghĩa dữ liệu|Mạng máy tính|Node|PHP|Phần mềm hệ thống|Phần mềm ứng dụng|Site licenses|Concurrent-user licenses|Thiết bị vào|Thiết kế top-down|Thuật giải|Tính khách quan|Tính kết thúc|Tính phổ dụng|Tính rõ ràng|Web
Algorithm|Bước chuyển qui nạp|Bước cơ sở qui nạp|Danh sách tuyến tính|Sắp xếp chèn|Thứ tự của các nút trên cây|Trường hợp tốt nhất|Định nghĩa của prefix|Định nghĩa của suffix
Bế tắc|File thực thi|Hệ số song song của hệ thống|Ngắt|Thao tác nhập xuất|Thư mục|Tiến trình đa luồng|Tiến trình đơn luồng|Tiến trình đặc biệt|Trang của tiến trình|Trạng thái của tiến trình|Vùng đệm
Biến cục bộ|Biểu đồ cấu trúc|BorderPane|Built-in UI controls|Các phương thức thiết lập Set|Các phương thức truy vấn Get|Công nghệ đối tượng|GridPane|Group|Hướng đối tượng|Implementations|Interfaces|Java|Kỹ thuật lập trình|Nạp chồng phương thức|OOA|OOP|Phương thức hủy|Scene Builder|Scene graph|Thư viện lớp|Trách nhiệm của lớp|Trừu tượng hóa dữ liệu|Tính đúng đắn|Tương tác của lớp|Đối tượng
Biểu đồ hoạt động|Biểu đồ lớp|Bước dịch chuyển|Các lớp|Các lớp cha|Cảnh giới|Hoạt động hữu hạn|Hoạt động liên tục|Lớp|Lớp chủ động|Mã tường minh|Một lớp liên kết|Một thuộc tính|Ngoại lệ|Sự kiện thay đổi|Sự kiện thời gian|Sự kiện đầu ra|Thao tác|Tín hiệu|Tầng nghiệp vụ|Tầng truy cập dữ liệu|Tầng trình bày|Tầng ứng dụng
Cây DFS|Cầu|Dãy con chung dài nhất|Dãy con tăng dài nhất|Kỹ thuật đệ qui|Một đồ thị|Sắp xếp topo|Tham lam|Thuật toán Kruskal|Thuật toán Prim|Thời gian tính khấu trừ|Tập đoạn thẳng không giao nhau|char|Đệ qui|Đổi tiền
Chất lượng phần mềm|Clarity and simplicity of Expression|Control Constructs|Công nghệ phần mềm|Information hiding|Kỹ thuật Ethnographic|Mã hóa|Một baseline|Naming|Nesting|Phương thức của đối tượng|Procedural|Programming|Quy trình không hình thức|Quản lý cấu hình phần mềm|Side-effects|Thuộc tính của đối tượng|Thực thể|Tài liệu về yêu cầu|User-defined types|Độ đo phần mềm
ANN|Bagging|Giả thuyết i.i.d|Giảm chiều|Khai phá dữ liệu|Làm sạch|Model selection|Mô hình hỗn hợp|Một ANN|Ngoại lai|Rời rạc hoá|SVM
Interpreter|Khối trong ngôn ngữ lập trình|Ký pháp BNF|Một biểu thức kiểu|Ngôn ngữ định kiểu mạnh|Phân tích trái của a|Quản lý phạm vi động nghĩa|Thuộc tính|Thuộc tính kế thừa|Tối ưu mã|Từ khóa
CAsyncSocket|CSocket|IPEndPoint|Lập trình mạng|OnAccept|OnClose|OnConnect|OnReceive
Bộ phát hiện|Chống từ chối|Clickjacking|Content-Type|Giao thức truy cập|Mật mã khóa đối xứng|Strokejacking|Tính toàn vẹn|Tính xác thực
Bộ nhớ cảm nhận|Các chế độ nhãn|Giao diện|Giao diện người dùng|Giải quyết vấn đề|HT giả định|Kế hoạch|Lập luận|MALTRON|Menu|Mẫu thử|Thiết kế thành viên|Thiết kế xã hội|Tính khái quát|Tính phù hợp của kiểu hội thoại|Tốc độ xử lý|Xử lý theo lô|Đặc trưng phi chức năng
Giao tiếp không dây|Historycal principle|Hệ thống phân cấp thiết kế|Kênh vào ra|Kế hoạch thử nghiệm|Ngôn ngữ tự nhiên với 2 dạng|Sketch|Thiết kế Skeuomorph|Thiết lập yêu cầu|Trải nghiệm người dùng|Tính nhất quán bên ngoài|Tính nhất quán nội bộ|Tính nhất quán trong thế giới thực|Đáp ứng của hệ thống|Độ nhìn
Quá trình ngẫu nhiên|Multicasting|Focal loss|Tensorflow Lite|Xử lý NNTN|An Intent|Component tree|Fragment result API|LiveData|Weight
Android|Animation/Painting/Gesture|Babel|Build Context|Bảo mật|Callable classes|Chính sách quyền riêng tư|Components|Cơ chế bất đồng bộ|Cảm biến tiệm cận|Cảm biến ánh sáng xung quanh|Cấu trúc điều hướng phẳng|Cấu trúc điều hướng sâu|Dart|Flexbox|Flutter|Flutter engine|GDPR|GPU|Hybrid|Khái niệm mixin|Kiến trúc một khối|La bàn|Life cycle|ListView|Lập trình bất đồng bộ - Asynchronous|Lớp trừu tượng|Material Design|Material/Cupertino|Mounted|Mô hình Null Navigation|Một promise|Navigation.push|Opening webview|Props|Provider|ScrollView|Sensor|Single Child Widgets|Spacer widget|State|Tầng dữ liệu|UnMounted|ViewModel|Widget|Widgets|Đồ họa 3D
Exclusive Lock|LockFile, UnlockFile|Setuid|Shared Lock
Biểu diễn của văn bản|Biểu diễn ký tự|CBOW|CNN-non-static|CNN-rand|CNN-static|Hệ tìm kiếm|Phân giải đồng tham chiếu|Phân loại đồ thị|SST|Truy vấn cụm|Truy vấn nhị phân|Truy vấn từ khóa|Trích rút thông tin|Tên riêng|Từ chỉ cảm xúc|Unigram
An Estimator|Apache Kafka|Apache ZooKeeper|Availability|CAP theorem|Consistency|Consistent hashing|Data Streaming|Dynamo|Eventual Consistency|HBase|Hadoop|InputDStreams|Location Independence|Oozie|Output|Partition Tolerance|Query|Sqoop|Transformer|Tính sẵn sàng
"""


def key(text): return re.sub(r"\s+", "", norm(text))
CANONICAL = {key(name.strip()): name.strip() for line in NAMES.splitlines() for name in line.split('|') if name.strip()}


def canonical_concept(text):
    return CANONICAL.get(key(text))
