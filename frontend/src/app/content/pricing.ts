export interface Plan { name: string; price: string; description: string; features: string[]; highlighted?: boolean; }
export const plans: Plan[] = [
  { name: "Free", price: "0đ", description: "Các chức năng học tập cơ bản.", features: ["Tạo chủ đề", "Tạo quiz thủ công", "Làm bài có timer", "Lưu tiến độ"] },
  { name: "Pro sinh viên", price: "Sắp công bố", description: "Các công cụ AI và xuất nội dung nâng cao.", features: ["Sinh quiz bằng AI", "Nhiều nguồn tài liệu", "AI giải thích", "Export nhiều định dạng"], highlighted: true },
  { name: "Giảng viên", price: "Sắp công bố", description: "Quản lý lớp học và bài tập.", features: ["Lớp học", "Giao bài", "Theo dõi kết quả", "Quản lý thành viên"] },
];
