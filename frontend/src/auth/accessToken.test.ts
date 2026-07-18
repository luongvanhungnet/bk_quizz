import { accessTokenStore } from "./accessToken";

describe("accessTokenStore", () => {
  it("keeps the access token in memory and clears it without browser persistence", () => {
    const localStorageSpy = vi.spyOn(Storage.prototype, "setItem");

    accessTokenStore.set("short-lived-token");
    expect(accessTokenStore.get()).toBe("short-lived-token");
    accessTokenStore.clear();

    expect(accessTokenStore.get()).toBeNull();
    expect(localStorageSpy).not.toHaveBeenCalled();
  });
});
