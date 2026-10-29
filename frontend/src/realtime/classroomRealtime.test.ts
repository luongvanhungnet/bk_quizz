import { describe, expect, it } from "vitest";

import { classroomChannelName, resolveRealtimeProvider } from "./classroomRealtime";

describe("resolveRealtimeProvider", () => {
  it("uses Ably only when it is explicitly configured", () => {
    expect(resolveRealtimeProvider("ably")).toBe("ably");
    expect(resolveRealtimeProvider("stomp")).toBe("stomp");
    expect(resolveRealtimeProvider(undefined)).toBe("stomp");
  });
});

describe("classroomChannelName", () => {
  it("uses the server-owned classroom channel namespace", () => {
    expect(classroomChannelName("3e6dc560-f826-4f80-a340-e4f44821fd92"))
      .toBe("bkquiz:classroom:3e6dc560-f826-4f80-a340-e4f44821fd92");
  });
});
