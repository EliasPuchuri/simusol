/**
 * Runs `worker` over `items` with at most `limit` in flight at once. Every item is attempted: the worker is
 * expected to handle its own errors, so one failing item never stops the others.
 */
export async function runPool<T>(items: T[], limit: number, worker: (item: T, index: number) => Promise<void>): Promise<void> {
  let next = 0;
  const lanes = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, async () => {
    while (next < items.length) {
      const index = next++;
      await worker(items[index], index);
    }
  });
  await Promise.all(lanes);
}
