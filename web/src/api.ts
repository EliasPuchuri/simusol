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
export type Orientation = {
  type: "planar" | "axial" | "no_interpretable";
  azimuth: number | null;
  dip: number | null;
  note: string | null;
  reason: string | null;
};
export type ReferenceComparison =
  | { comparable: true; delta_azimuth_deg: number | null; delta_dip_deg: number | null }
  | { comparable: false; reason: string };
export type ReferenceInfo = {
  method: string;
  azimuth: number | null;
  dip: number | null;
  comparison: ReferenceComparison;
};
export type CharResult = {
  filename: string;
  key: string;
  size_bytes: number;
  status: "ok" | "failed" | "pending";
  error: string | null;
  body_type?: string | null;
  orientation?: Orientation | null;
  eigenvalues?: number[] | null;
  reference?: ReferenceInfo | null;
};
export type CharReport = {
  run: QcRun | null;
  summary: { ok: number; failed: number; pending: number };
  results: CharResult[];
};
export type RuleCheck = {
  rule: string;
  group: string;
  observed: number | string | null;
  op: string;
  threshold: number | string | null;
  passed: boolean;
  applicable: boolean;
};
export type CharLite = { status: string; body_type: string | null; orientation: Orientation | null };
export type VolumeTotals =
  | { available: false; reason?: string }
  | {
      available: true;
      provisional: boolean;
      previous: PeriodTotal;
      current: PeriodTotal;
      difference_m3: number;
      difference_pct: number | null;
      warnings: string[];
    };
export type PeriodOverlap = { evaluated: boolean; pairs: number | null; pairwise_common_m3: number | null };
export type PeriodTotal = { sum_m3: number; counted: number; total: number; excluded: { key: string; reason: string }[]; overlap?: PeriodOverlap };
export type OverlapPair = {
  a: string; b: string; key_a: string; key_b: string; status: string; relation: "overlap" | "contact" | "not_evaluable" | null;
  common_m3: number | null; common_pct_of_smaller: number | null; reason: string | null; warnings: string[];
};
export type OverlapReport = {
  run: QcRun | null; evaluated: boolean;
  summary: { solids: number; pairs: number; discarded: number; overlapping: number; contact: number; disjoint: number; not_evaluable: number; failed: number; pending: number; unreadable: string[] };
  pairs: OverlapPair[];
};
export type ComparisonRow = {
  key: string;
  previous_filename: string | null;
  current_filename: string | null;
  status: "ok" | "failed" | "pending" | "n/a" | "incident";
  technical_status: string;
  state: "SIN CAMBIOS" | "VARIABLE" | "NUEVO" | "ELIMINADO" | null;
  subtype: string | null;
  description: string;
  events: string[];
  checks: RuleCheck[];
  incidents: { code: string }[];
  warnings: string[];
  metrics: { iou_pct: number | null; delta_volume_pct: number | null; p95_m: number | null; centroid_m: number | null } | null;
  volumes?: { previous_m3: number | null; current_m3: number | null } | null;
  reasons?: Record<string, string>;
  characterization?: { previous?: CharLite | null; current?: CharLite | null } | null;
  provisional: boolean;
  profile: string;
  error?: string | null;
};
export type SpatialCheck = {
  status: "compatible" | "undeclared" | "mismatch" | "extent_disjoint";
  issues: string[]; extent_checked: boolean;
  declared: Record<"previous" | "current", { spatial_reference: string | null; units: string | null }>;
};
export type ComparisonReport = {
  run: (QcRun & { previous_id?: string; current_id?: string }) | null;
  provisional: boolean;
  profile: string;
  summary: { "SIN CAMBIOS": number; VARIABLE: number; NUEVO: number; ELIMINADO: number; sin_clasificar: number; pendientes: number };
  totals?: VolumeTotals;
  spatial?: SpatialCheck;
  rows: ComparisonRow[];
};
export type Review = {
  key: string;
  reviewer: string;
  agrees: boolean;
  comment: string;
  expected_state: string | null;
  expected_body_type: string | null;
  expected_azimuth: number | null;
  expected_dip: number | null;
};
export type ReviewInput = {
  previous: string;
  current: string;
  key: string;
  reviewer: string;
  agrees: boolean;
  expected_state: string | null;
  expected_body_type: string | null;
  expected_azimuth: number | null;
  expected_dip: number | null;
  comment: string;
};
export type RegionInfo = { status: "ok" | "empty" | "unavailable"; volume_m3?: number; triangles?: number; url?: string; reason?: string };
export type SceneRegions = {
  status: "ok" | "failed";
  error: string | null;
  provisional: boolean;
  warnings: string[];
  regions: Record<"common" | "added" | "removed", RegionInfo> | null;
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
  getOverlaps: (id: string) => request<OverlapReport>(`/api/v1/datasets/${id}/overlaps`),
  startOverlaps: (id: string) => request<QcRun>(`/api/v1/datasets/${id}/overlaps`, { method: "POST" }),
  getCharacterization: (id: string) => request<CharReport>(`/api/v1/datasets/${id}/characterization`),
  startCharacterization: (id: string) => request<QcRun>(`/api/v1/datasets/${id}/characterization`, { method: "POST" }),
  characterizationCsvUrl: (id: string) => `/api/v1/datasets/${id}/characterization.csv`,
  getComparison: (previous: string, current: string) =>
    request<ComparisonReport>(`/api/v1/comparisons?previous=${previous}&current=${current}`),
  startComparison: (previous: string, current: string) =>
    request<QcRun>("/api/v1/comparisons", json("POST", { previous, current })),
  comparisonCsvUrl: (previous: string, current: string) =>
    `/api/v1/comparisons/report.csv?previous=${previous}&current=${current}`,
  putReview: (input: ReviewInput) => request<{ saved: boolean }>("/api/v1/comparisons/reviews", json("PUT", input)),
  listReviews: (previous: string, current: string, reviewer: string) =>
    request<{ reviews: Review[] }>(`/api/v1/comparisons/reviews?previous=${previous}&current=${current}&reviewer=${encodeURIComponent(reviewer)}`),
  reviewsCsvUrl: (previous: string, current: string) => `/api/v1/comparisons/reviews.csv?previous=${previous}&current=${current}`,
  archiveDataset: (id: string) => request<Dataset>(`/api/v1/datasets/${id}/archive`, { method: "POST" }),
  qcCsvUrl: (id: string) => `/api/v1/datasets/${id}/qc.csv`,
  orientationTemplateUrl: "/api/v1/templates/orientation-reference",
  uploadOrientationReference: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<ReferenceResult>(`/api/v1/datasets/${id}/orientation-reference`, { method: "POST", body: form });
  },
  scene: (previous: string, current: string, key: string) =>
    request<SceneManifest>(`/api/v1/scene?previous=${previous}&current=${current}&key=${encodeURIComponent(key)}`),
  sceneRegions: (previous: string, current: string, key: string) =>
    request<SceneRegions>(`/api/v1/scene/regions?previous=${previous}&current=${current}&key=${encodeURIComponent(key)}`),
  matches: (previous: string, current: string) =>
    request<Matches>(`/api/v1/matches?previous=${previous}&current=${current}`),
};
