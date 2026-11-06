import type { ComparisonRow, Orientation } from "./api";

type Row = ComparisonRow;
export type Filters = { state: string; query: string };
export type PeriodCounts = { total: number; sinCambios: number; variables: number; nuevos: number; eliminados: number };

const int = (v: number) => Math.round(v).toLocaleString("es-PE");
export const volumeText = (v: number | null | undefined) => (v == null ? "—" : int(v));
export const signed = (v: number, unit = "") => `${v < 0 ? "−" : v > 0 ? "+" : ""}${int(Math.abs(v))}${unit}`;
export const signedPercent = (v: number) => `${v < 0 ? "−" : v > 0 ? "+" : ""}${Math.abs(v).toFixed(1)} %`;

export function percentOf(n: number, base: number): string {
  return base > 0 ? `${Math.round((100 * n) / base)} %` : "—";
}

/** Counts of solids per period. A solid without a state yet (pending, failed) only counts in the total. */
export function periodCounts(rows: Row[]): { previous: PeriodCounts; current: PeriodCounts } {
  const empty = (): PeriodCounts => ({ total: 0, sinCambios: 0, variables: 0, nuevos: 0, eliminados: 0 });
  const out = { previous: empty(), current: empty() };
  for (const r of rows) {
    for (const role of ["previous", "current"] as const) {
      if (!(role === "previous" ? r.previous_filename : r.current_filename)) continue;
      const c = out[role];
      c.total++;
      if (r.state === "SIN CAMBIOS") c.sinCambios++;
      else if (r.state === "VARIABLE") c.variables++;
      else if (r.state === "NUEVO") c.nuevos++;
      else if (r.state === "ELIMINADO") c.eliminados++;
    }
  }
  return out;
}

const bodyType = (r: Row, role: "previous" | "current") => r.characterization?.[role]?.body_type ?? null;

export function filterRows(rows: Row[], f: Filters): Row[] {
  const q = f.query.trim().toLowerCase();
  return rows.filter((r) => {
    if (f.state === "unassigned" ? !(r.state === null && r.status !== "pending") : f.state === "pending" ? r.status !== "pending" : f.state !== "all" && r.state !== f.state) return false;
    if (q && ![r.key, r.previous_filename, r.current_filename].some((t) => t?.toLowerCase().includes(q))) return false;
    return true;
  });
}

const decimals = (v: number, n: number) => v.toLocaleString("es-PE", { minimumFractionDigits: n, maximumFractionDigits: n });
/** Volume for text where small values matter (shared overlaps): decimals under 10 m³, whole numbers above. */
export const volumeShort = (v: number | null | undefined) => (v == null ? "—" : v < 10 ? v.toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : int(v));
export const volumeExact = (v: number | null | undefined) => (v == null ? "—" : decimals(v, 3));

/** Volume difference as the table shows it: a removed solid lost all of it; a new one has no base to compare with. */
export function diffPercent(r: Row): number | null {
  if (r.state === "ELIMINADO") return -100;
  if (r.state === "NUEVO") return null;
  return r.metrics?.delta_volume_pct ?? null;
}
export function diffText(v: number | null): string {
  if (v == null) return "—";
  const r = Math.abs(v) < 0.005 ? 0 : v; // never show "-0.00"
  return decimals(r, 2);
}
export const degreeText = (v: number | null | undefined) => (v == null ? "—" : decimals(v, 2));

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
  zero_volume: "volumen nulo", boolean_failed: "la operación geométrica falló", single_failed: "el cálculo falló", pair_failed: "el cálculo del par falló",
};
export function exclusionText(reason: string): string {
  const [kind, role] = reason.split(":");
  const where = role === "previous" ? " (periodo anterior)" : role === "current" ? " (periodo actual)" : "";
  return `${EXCLUSION_REASONS[kind] ?? kind}${where}`;
}
