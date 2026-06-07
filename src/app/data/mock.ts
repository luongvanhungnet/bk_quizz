import {
  BarChart3,
  BookOpen,
  Brain,
  Database,
  FileQuestion,
  FileText,
  Globe2,
  GraduationCap,
  Layers,
  Network,
  ShieldCheck,
  Sigma,
} from "lucide-react";

export type Topic = {
  id: number;
  name: string;
  subject: string;
  quizCount: number;
  questionCount: number;
  updated: string;
  color: string;
  icon: typeof BookOpen;
  featured?: boolean;
};

export type Quiz = {
  id: number;
  title: string;
  count: number;
  duration: number;
  createdAt: string;
  difficulty: "Dễ" | "Trung bình" | "Khó";
};

export type Question = {
  id: number;
  text: string;
  type: "single" | "multiple" | "fill";
  options: string[];
  correct: string | string[];
  explanation: string;
};

export type Plan = {
  name: string;
  price: string;
  description: string;
  features: string[];
  highlighted?: boolean;
};

export const topics: Topic[] = [
  {
    id: 1,
    name: "Kỹ thuật truyền thông",
    subject: "ET4060",
    quizCount: 12,
    questionCount: 320,
    updated: "2 giờ trước",
    color: "bg-blue-100 text-blue-700",
    icon: Network,
    featured: true,
  },
  {
    id: 2,
    name: "Cấu trúc dữ liệu & GT",
    subject: "IT3011",
    quizCount: 8,
    questionCount: 210,
    updated: "Hôm qua",
    color: "bg-emerald-100 text-emerald-700",
    icon: Database,
    featured: true,
  },
  {
    id: 3,
    name: "Xác suất thống kê",
    subject: "MI2020",
    quizCount: 15,
    questionCount: 450,
    updated: "2 ngày trước",
    color: "bg-violet-100 text-violet-700",
    icon: Sigma,
    featured: true,
  },
  {
    id: 4,
    name: "Hệ điều hành",
    subject: "IT3070",
    quizCount: 5,
    questionCount: 180,
    updated: "Tuần trước",
    color: "bg-orange-100 text-orange-700",
    icon: Layers,
    featured: true,
  },
  {
    id: 5,
    name: "Công nghệ phần mềm",
    subject: "IT4082",
    quizCount: 20,
    questionCount: 520,
    updated: "Tháng trước",
    color: "bg-rose-100 text-rose-700",
    icon: Brain,
  },
];

export const communityTopics = [
  {
    id: 101,
    title: "Kỹ thuật truyền thông - GK",
    author: "Nguyễn Minh",
    subject: "ET4060",
    quizzes: 18,
    learners: 1240,
    rating: 4.9,
    saves: 340,
  },
  {
    id: 102,
    title: "CTDL & GT - Ôn tập heap/tree",
    author: "Trần Huy",
    subject: "IT3011",
    quizzes: 12,
    learners: 980,
    rating: 4.8,
    saves: 225,
  },
  {
    id: 103,
    title: "Xác suất thống kê - Đề cuối kỳ",
    author: "Lê Hà",
    subject: "MI2020",
    quizzes: 16,
    learners: 1460,
    rating: 4.7,
    saves: 410,
  },
  {
    id: 104,
    title: "Hệ điều hành - Tổng hợp câu hỏi",
    author: "Phạm Long",
    subject: "IT3070",
    quizzes: 9,
    learners: 720,
    rating: 4.6,
    saves: 188,
  },
  {
    id: 105,
    title: "Cơ sở dữ liệu - Truy vấn SQL",
    author: "Đỗ Anh",
    subject: "IT3090",
    quizzes: 14,
    learners: 890,
    rating: 4.8,
    saves: 260,
  },
  {
    id: 106,
    title: "Triết học Mác-Lênin - 500 câu",
    author: "Mai Linh",
    subject: "LLCT",
    quizzes: 20,
    learners: 2100,
    rating: 4.5,
    saves: 560,
  },
];

export const quizzes: Quiz[] = [
  {
    id: 1,
    title: "Quiz GK - Chương 1",
    count: 20,
    duration: 45,
    createdAt: "12 phút trước",
    difficulty: "Trung bình",
  },
  {
    id: 2,
    title: "Quiz ôn tập nhanh 02",
    count: 15,
    duration: 25,
    createdAt: "1 ngày trước",
    difficulty: "Dễ",
  },
  {
    id: 3,
    title: "Đề mô phỏng cuối kỳ",
    count: 40,
    duration: 60,
    createdAt: "3 ngày trước",
    difficulty: "Khó",
  },
];

export const questions: Question[] = [
  {
    id: 1,
    text: "Giao thức TCP thuộc tầng nào trong mô hình OSI?",
    type: "single",
    options: [
      "Tầng Ứng dụng (Application)",
      "Tầng Giao vận (Transport)",
      "Tầng Mạng (Network)",
      "Tầng Liên kết dữ liệu (Data Link)",
    ],
    correct: "Tầng Giao vận (Transport)",
    explanation:
      "TCP là giao thức truyền tin có đảm bảo, hoạt động ở tầng giao vận và chịu trách nhiệm thiết lập kết nối, kiểm soát lỗi, kiểm soát luồng.",
  },
  {
    id: 2,
    text: "Các giao thức nào sau đây thuộc tầng Giao vận? (Chọn nhiều đáp án)",
    type: "multiple",
    options: ["TCP", "IP", "UDP", "HTTP"],
    correct: ["TCP", "UDP"],
    explanation:
      "TCP và UDP là hai giao thức lõi của tầng Giao vận. IP thuộc tầng Mạng, HTTP thuộc tầng Ứng dụng.",
  },
  {
    id: 3,
    text: "Điền vào chỗ trống: [...] là quá trình chuyển đổi tín hiệu tương tự sang tín hiệu số.",
    type: "fill",
    options: [],
    correct: "Điều chế xung mã",
    explanation:
      "Điều chế xung mã (PCM) gồm lấy mẫu, lượng tử hóa và mã hóa tín hiệu analog thành tín hiệu digital.",
  },
];

for (let i = 4; i <= 33; i += 1) {
  questions.push({
    id: i,
    text: `Câu hỏi phụ số ${i}: Băng thông chuẩn của kênh thoại trong hệ thống truyền thông là bao nhiêu?`,
    type: "single",
    options: ["3.1 kHz", "4 kHz", "20 kHz", "2.4 GHz"],
    correct: "3.1 kHz",
    explanation:
      "Kênh thoại thường xét dải 300 Hz đến 3400 Hz, tương đương khoảng 3.1 kHz.",
  });
}

export const plans: Plan[] = [
  {
    name: "Free",
    price: "0đ",
    description: "Dành cho sinh viên muốn thử nhanh.",
    features: ["3 chủ đề", "50 câu hỏi/tháng", "Thi thử có timer", "Xuất PDF cơ bản"],
  },
  {
    name: "Pro SV",
    price: "49.000đ/tháng",
    description: "Ôn GK/CK thường xuyên với AI.",
    features: ["Không giới hạn chủ đề", "1.000 câu hỏi/tháng", "Export PDF/DOCX/CSV", "AI giải thích câu sai"],
    highlighted: true,
  },
  {
    name: "Giảng viên",
    price: "199.000đ/tháng",
    description: "Tạo ngân hàng câu hỏi cho lớp học.",
    features: ["Lớp học & chia sẻ", "Rubric tự luận", "Phân tích kết quả", "Hỗ trợ ưu tiên"],
  },
];

export const activities = [
  { title: "Hoàn thành Quiz GK - Chương 1", score: "8.7", time: "Hôm nay", icon: ShieldCheck },
  { title: "Tạo chủ đề Kỹ thuật truyền thông", score: "20 câu", time: "2 giờ trước", icon: FileQuestion },
  { title: "Xuất đề ôn tập sang PDF", score: "PDF", time: "Hôm qua", icon: FileText },
  { title: "Chia sẻ chủ đề cho nhóm học", score: "12 SV", time: "3 ngày trước", icon: Globe2 },
];

export const sourceFiles = [
  { id: 1, name: "Chuong_1_Tong_Quan.pdf", size: "2.4 MB", type: "PDF", selected: true },
  { id: 2, name: "Slide_Bai_Giang_02.ppt", size: "5.1 MB", type: "PPT", selected: true },
  { id: 3, name: "Bai_tap_mang_can_bang.docx", size: "860 KB", type: "DOCX", selected: false },
];

export const stats = [
  { label: "Chủ đề", value: "12", icon: BookOpen },
  { label: "Quiz đã làm", value: "156", icon: GraduationCap },
  { label: "Câu hỏi", value: "1.280", icon: FileQuestion },
  { label: "Điểm TB", value: "8.2/10", icon: BarChart3 },
];
