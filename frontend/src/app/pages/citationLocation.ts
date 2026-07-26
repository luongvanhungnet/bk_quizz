export interface CitationLocation {
  pageNumber: number | null;
  slideNumber: number | null;
  chunkIndex: number;
}

export function citationLocation(value: CitationLocation): string {
  if (value.pageNumber != null) return `Trang ${value.pageNumber}`;
  if (value.slideNumber != null) return `Slide ${value.slideNumber}`;
  return `Đoạn ${value.chunkIndex + 1}`;
}
