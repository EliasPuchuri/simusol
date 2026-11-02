/** Default opacity per layer. Kept apart from ThreeScene so the UI can read it without loading WebGL code. */
export const DEFAULT_OPACITY = { previous: 1, current: 0.8, common: 0.55, added: 1, removed: 1 } as const;
