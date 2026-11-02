export type Dataset = {
  id: string;
  name: string;
  period_label: string;
  period_kind: "annual" | "monthly";
  revision: number;
  is_demo: boolean;
  spatial_reference: string | null;
  units: string | null;
  state: "open" | "closed";
  created_at: string;
  file_count?: number;
};

export type FileEntry = { filename: string; key: string; sha256: string; size_bytes: number };
export type Incident = { code: string; message: string; detail: Record<string, unknown> };
export type DatasetDetail = Dataset & {
  files: FileEntry[];
  incidents: Incident[];
  counts: { files: number; keys: number };
  orientation_reference_count?: number;
};
export type Matches = {
  pairs: { key: string; previous: FileEntry; current: FileEntry }[];
  only_previous: FileEntry[];
  only_current: FileEntry[];
  incidents: Incident[];
};
export type SceneLayer = {
  role: "previous" | "current";
  filename: string;
  status: "ok" | "failed";
  url?: string;
  reason?: string;
  vertices?: number;
  triangles?: number;
};
export type SceneManifest = {
  key: string;
  origin: { east: number; north: number; elevation: number } | null;
  axes: string;
  layers: SceneLayer[];
};
export type MetricJson = { value: number | null; validity: string; reason: string | null };
export type QcResult = {
  filename: string;
  key: string;
  size_bytes: number;
  status: "ok" | "with_issues" | "failed" | "pending";
  problems: string[];
  error: string | null;
  signed_volume_m3?: number | null;
  volume_m3?: MetricJson;
  orientation?: string;
  open_edges?: number | null;
  non_manifold_edges?: number | null;
  duplicate_vertices?: number | null;
  duplicate_faces?: number | null;
  degenerate_faces?: number | null;
  components?: MetricJson;
  self_intersections?: MetricJson;
};
export type QcRun = { id: string; dataset_id: string; state: string; total: number; done: number; error: string | null };
export type QcReport = {
  run: QcRun | null;
  summary: { ok: number; with_issues: number; failed: number; pending: number };
  results: QcResult[];
};
export type NewDataset = Pick<Dataset, "name" | "period_label" | "period_kind" | "is_demo" | "spatial_reference" | "units">;

export type Issue = { code: string; line?: number | null; column?: string | null; value?: string | null };
export type ReferenceResult = { saved: number; ignored_examples: number; warnings: Issue[] };
export type ReferenceFailure = { errors: Issue[]; warnings: Issue[]; ignored_examples: number };

export class ApiError extends Error {
  constructor(message: string, readonly detail?: unknown) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    throw new ApiError(typeof detail === "string" ? detail : `Error ${response.status}`, detail);
  }
  return body as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  listDatasets: () => request<Dataset[]>("/api/v1/datasets"),
  createDataset: (body: NewDataset) => request<Dataset>("/api/v1/datasets", json("POST", body)),
  getDataset: (id: string) => request<DatasetDetail>(`/api/v1/datasets/${id}`),
  uploadFile: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<FileEntry>(`/api/v1/datasets/${id}/files`, { method: "POST", body: form });
  },
  finalize: (id: string) => request<Dataset>(`/api/v1/datasets/${id}/finalize`, { method: "POST" }),
  getQc: (id: string) => request<QcReport>(`/api/v1/datasets/${id}/qc`),
  startQc: (id: string) => request<QcRun>(`/api/v1/datasets/${id}/qc`, { method: "POST" }),
  qcCsvUrl: (id: string) => `/api/v1/datasets/${id}/qc.csv`,
  orientationTemplateUrl: "/api/v1/templates/orientation-reference",
  uploadOrientationReference: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<ReferenceResult>(`/api/v1/datasets/${id}/orientation-reference`, { method: "POST", body: form });
  },
  scene: (previous: string, current: string, key: string) =>
    request<SceneManifest>(`/api/v1/scene?previous=${previous}&current=${current}&key=${encodeURIComponent(key)}`),
  matches: (previous: string, current: string) =>
    request<Matches>(`/api/v1/matches?previous=${previous}&current=${current}`),
};
