export type CognitiveLevel = "L1" | "L2" | "L3" | "L4" | "L5";
export type CognitiveMode = CognitiveLevel | "BALANCED";

export const cognitiveOptions: Array<{
  value: CognitiveMode;
  label: string;
  description: string;
}> = [
  { value: "L1", label: "Nhận biết", description: "Tìm lại kiến thức trực tiếp từ tài liệu" },
  { value: "L2", label: "Hiểu", description: "Giải thích, phân biệt và nhận diện khái niệm" },
  { value: "L3", label: "Áp dụng", description: "Sử dụng kiến thức vào tình huống mới" },
  { value: "L4", label: "Phân tích", description: "Kết hợp nhiều kiến thức và suy luận" },
  { value: "L5", label: "Thử thách", description: "Giải quyết vấn đề nhiều bước" },
  { value: "BALANCED", label: "Cân bằng", description: "Phân bổ nhiều mức độ tư duy theo tỷ lệ chuẩn" },
];

export function cognitiveLabel(value: CognitiveMode | null | undefined): string {
  return cognitiveOptions.find((option) => option.value === value)?.label ?? "Chưa xác định";
}

export function cognitiveDistribution(total: number): Record<CognitiveLevel, number> {
  const values: CognitiveLevel[] = ["L3", "L2", "L4", "L1", "L5"];
  const weights = [0.35, 0.25, 0.25, 0.1, 0.05];
  const floors = weights.map((weight) => Math.floor(Math.max(0, total) * weight));
  const remaining = Math.max(0, total) - floors.reduce((sum, value) => sum + value, 0);
  const order = weights
    .map((weight, index) => ({ index, remainder: total * weight - floors[index]! }))
    .sort((a, b) => b.remainder - a.remainder || a.index - b.index);
  for (let index = 0; index < remaining; index += 1) {
    const target = order[index]!.index;
    floors[target] = floors[target]! + 1;
  }
  const result = { L1: 0, L2: 0, L3: 0, L4: 0, L5: 0 };
  values.forEach((level, index) => { result[level] = floors[index]!; });
  return result;
}
