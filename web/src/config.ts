/** Polling intervals in milliseconds. Mutable only so tests can shorten them. */
export const POLL_MS = { qc: 1500, characterization: 1500, comparison: 2000 };

/** Files uploaded at the same time: hides the round trip of each request without overloading a 1-CPU server. */
export const UPLOAD_CONCURRENCY = 3;
