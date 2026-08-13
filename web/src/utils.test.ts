import { describe, expect, it } from "vitest";
import { duration, elapsed } from "./utils.ts";

describe("time presentation", () => {
  it("rounds review durations up to the next whole minute", () => {
    expect(duration(0)).toBe("0h 00m");
    expect(duration(60)).toBe("0h 01m");
    expect(duration(61)).toBe("0h 02m");
    expect(duration(3661)).toBe("1h 02m");
  });

  it("derives live elapsed time from the persisted start instant", () => {
    expect(
      elapsed(
        "2026-08-12T08:00:00.000Z",
        Date.parse("2026-08-12T09:02:03.000Z"),
      ),
    ).toBe("01:02:03");
  });
});
