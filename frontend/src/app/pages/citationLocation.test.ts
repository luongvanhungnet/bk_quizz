import { describe, expect, it } from "vitest";
import { citationLocation } from "./citationLocation";

describe("citationLocation", () => {
  it("ưu tiên trang, slide rồi mới dùng số đoạn", () => {
    expect(citationLocation({ pageNumber: 3, slideNumber: null, chunkIndex: 8 })).toBe("Trang 3");
    expect(citationLocation({ pageNumber: null, slideNumber: 4, chunkIndex: 8 })).toBe("Slide 4");
    expect(citationLocation({ pageNumber: null, slideNumber: null, chunkIndex: 0 })).toBe("Đoạn 1");
  });
});
