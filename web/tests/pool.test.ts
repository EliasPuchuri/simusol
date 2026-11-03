import { describe, expect, it } from "vitest";

import { runPool } from "../src/pool";

const tick = () => new Promise((r) => setTimeout(r, 5));

describe("runPool", () => {
  it("never runs more than the limit at once and attempts every item", async () => {
    let inFlight = 0, peak = 0;
    const done: number[] = [];
    await runPool([...Array(10).keys()], 3, async (n) => {
      peak = Math.max(peak, ++inFlight);
      await tick();
      inFlight--;
      done.push(n);
    });
    expect(peak).toBe(3);
    expect(done.sort((a, b) => a - b)).toEqual([...Array(10).keys()]);
  });

  it("starts the items in order and hands each one its index", async () => {
    const started: number[] = [];
    await runPool(["a", "b", "c", "d"], 2, async (_item, i) => {
      started.push(i);
      await tick();
    });
    expect(started).toEqual([0, 1, 2, 3]);
  });

  it("copes with fewer items than lanes and with no items", async () => {
    let n = 0;
    await runPool([1], 5, async () => void n++);
    await runPool([], 3, async () => void n++);
    expect(n).toBe(1);
  });
});
