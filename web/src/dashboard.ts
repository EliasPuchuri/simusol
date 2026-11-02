import type { ComparisonRow, Orientation } from "./api";

type Row = ComparisonRow;
export type Scope = "any" | "previous" | "current";
export type Filters = { state: string; type: string; scope: Scope; min: number | null; max: number | null; query: string };
export type DeltaVolume = { key: string; state: Row["state"]; delta: number; previous: number | null; current: number | null };

const int = (v: number) => Math.round(v).toLocaleString("es-PE");
export const volumeText = (v: number | null | undefined) => (v == null ? "—" : int(v));
export const signed = (v: number, unit = "") => `${v < 0 ? "−" : v > 0 ? "+" : ""}${int(Math.abs(v))}${unit}`;
export const signedPercent = (v: number) => `${v < 0 ? "−" : v > 0 ? "+" : ""}${Math.abs(v).toFixed(1)} %`;

export function percentOf(n: number, base: number): string {
  return base > 0 ? `${Math.round((100 * n) / base)} %` : "—";
}

export function polarPoint(azimuth: number, dip: number, radius: number): { x: number; y: number } {
  const r = (radius * dip) / 90;
  const a = (azimuth * Math.PI) / 180;
  return { x: r * Math.sin(a), y: -r * Math.cos(a) }; // North up, East right; distance from the centre = dip
}

export function deltaVolumes(rows: Row[]): DeltaVolume[] {
  const out: DeltaVolume[] = [];
  for (const r of rows) {
    const prev = r.volumes?.previous_m3 ?? null;
    const curr = r.volumes?.current_m3 ?? null;
    let delta: number | null = null;
    if (r.state === "NUEVO" && curr != null) delta = curr;
    else if (r.state === "ELIMINADO" && prev != null) delta = -prev;
    else if (r.status === "ok" && prev != null && curr != null) delta = curr - prev;
    if (delta != null && Math.abs(delta) > 0.0005) out.push({ key: r.key, state: r.state, delta, previous: prev, current: curr });
  }
  return out.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
}

const bodyType = (r: Row, role: "previous" | "current") => r.characterization?.[role]?.body_type ?? null;

export function filterRows(rows: Row[], f: Filters): Row[] {
  const q = f.query.trim().toLowerCase();
  return rows.filter((r) => {
    if (f.state === "unassigned" ? !(r.state === null && r.status !== "pending") : f.state === "pending" ? r.status !== "pending" : f.state !== "all" && r.state !== f.state) return false;
    if (f.type) {
      const types = f.scope === "any" ? [bodyType(r, "previous"), bodyType(r, "current")] : [bodyType(r, f.scope)];
      if (!types.includes(f.type)) return false;
    }
    if (f.min !== null || f.max !== null) {
      const vols = f.scope === "any" ? [r.volumes?.previous_m3, r.volumes?.current_m3] : [r.volumes?.[`${f.scope}_m3`]];
      if (!vols.some((v) => v != null && (f.min === null || v >= f.min) && (f.max === null || v <= f.max))) return false;
    }
    if (q && ![r.key, r.previous_filename, r.current_filename].some((t) => t?.toLowerCase().includes(q))) return false;
    return true;
  });
}

const deg = (v: number) => `${v.toFixed(1)}°`;

export function shortOrientation(o: Orientation | null | undefined): string {
  if (!o) return "—";
  if (o.type === "no_interpretable" || o.azimuth == null || o.dip == null) return "sin orientación interpretable";
  return o.type === "axial" ? `Eje: Trend ${deg(o.azimuth)} · Plunge ${deg(o.dip)}` : `Azimuth ${deg(o.azimuth)} · Dip ${deg(o.dip)}`;
}

const TYPE_LABEL: Record<string, string> = { TABULAR: "Tabular", "TABULAR CURVO": "Tabular curvo", GLOBULAR: "Globular" };
export function typeText(r: Row): string {
  const a = TYPE_LABEL[bodyType(r, "previous") ?? ""], b = TYPE_LABEL[bodyType(r, "current") ?? ""];
  if (a && b) return a === b ? a : `${a} → ${b}`;
  return a ?? b ?? "—";
}

export function latestOrientation(r: Row): Orientation | null {
  return r.characterization?.current?.orientation ?? r.characterization?.previous?.orientation ?? null;
}

export const EXCLUSION_REASONS: Record<string, string> = {
  not_watertight: "superficie no cerrada", inconsistent_winding: "caras con sentido inconsistente",
  zero_volume: "volumen nulo", single_failed: "el cálculo falló", pair_failed: "el cálculo del par falló",
};
export function exclusionText(reason: string): string {
  const [kind, role] = reason.split(":");
  const where = role === "previous" ? " (periodo anterior)" : role === "current" ? " (periodo actual)" : "";
  return `${EXCLUSION_REASONS[kind] ?? kind}${where}`;
}
