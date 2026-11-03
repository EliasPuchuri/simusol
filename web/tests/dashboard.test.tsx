import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { diffPercent, diffText, filterRows, percentOf, periodCounts } from "../src/dashboard";
import { POLL_MS } from "../src/config";

let sequences: Record<string, unknown[]> = {};

beforeEach(() => {
  localStorage.clear();
  POLL_MS.qc = POLL_MS.characterization = POLL_MS.comparison = 10;
  sequences = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const queue = sequences[`${init?.method ?? "GET"} ${url}`];
      if (!queue) {
        if (/\/(qc|characterization)$/.test(url)) return { ok: true, status: 200, json: async () => ({ run: null, summary: { ok: 0, failed: 0, pending: 0, with_issues: 0 }, results: [] }) } as Response;
        throw new Error(`unmocked ${init?.method ?? "GET"} ${url}`);
      }
      const next = (queue.length > 1 ? queue.shift() : queue[0]) as any;
      return { ok: true, status: 200, json: async () => next } as Response;
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const ds = (id: string, label: string) => ({ id, name: "Modelo", period_label: label, period_kind: "annual", revision: 1, is_demo: false, spatial_reference: null, units: null, state: "closed", created_at: "x", file_count: 4, archived: false });
const entry = (filename: string, key: string) => ({ filename, key, sha256: "0".repeat(64), size_bytes: 1 });
const detail = (id: string, label: string) => ({ ...ds(id, label), files: [entry("a.obj", "a")], incidents: [], counts: { files: 1, keys: 1 }, orientation_reference_count: 0 });
const matches = { pairs: [{ key: "a_3", previous: entry("a_3pt.obj", "a_3"), current: entry("a_3.obj", "a_3") }, { key: "b_3", previous: entry("b_3pt.obj", "b_3"), current: entry("b_3.obj", "b_3") }], only_previous: [entry("old.obj", "old")], only_current: [entry("new.obj", "new")], incidents: [] };
const char = (type: string, orient: object) => ({ status: "ok", body_type: type, orientation: orient });
const planar = (az: number, dip: number) => ({ type: "planar", azimuth: az, dip, note: null, reason: null });
const axial = (az: number, dip: number) => ({ type: "axial", azimuth: az, dip, note: null, reason: null });
const base = { status: "ok", technical_status: "ok", events: [], checks: [], incidents: [], warnings: [], reasons: {}, provisional: true, profile: "pilot-v1-provisional", subtype: null };
const rows = [
  { ...base, key: "a_3", previous_filename: "a_3pt.obj", current_filename: "a_3.obj", state: "SIN CAMBIOS", subtype: "IDENTICO", description: "SIN CAMBIO: coincidencia prácticamente total (IoU 100.00 %).", metrics: { iou_pct: 100, delta_volume_pct: 0, p95_m: 0, centroid_m: 0 }, volumes: { previous_m3: 1000, current_m3: 1000 }, characterization: { previous: char("TABULAR", planar(193, 70.3)), current: char("TABULAR", planar(193, 70.3)) } },
  { ...base, key: "b_3", previous_filename: "b_3pt.obj", current_filename: "b_3.obj", state: "VARIABLE", subtype: "VARIABLE", description: "RECORTE: se eliminó parte del sólido.", metrics: { iou_pct: 83.4, delta_volume_pct: -4.8, p95_m: 2.49, centroid_m: 2.81 }, volumes: { previous_m3: 1034768, current_m3: 984845 }, characterization: { previous: char("TABULAR", planar(81, 43)), current: char("TABULAR CURVO", planar(82, 44)) } },
  { ...base, key: "new", previous_filename: null, current_filename: "new.obj", status: "n/a", state: "NUEVO", description: "El sólido no existía en el periodo anterior.", metrics: null, volumes: { previous_m3: null, current_m3: 729 }, characterization: { current: char("GLOBULAR", axial(60, 20)) } },
  { ...base, key: "old", previous_filename: "old.obj", current_filename: null, status: "n/a", state: "ELIMINADO", description: "El sólido existía en el periodo anterior pero no existe en el periodo actual.", metrics: null, volumes: { previous_m3: 343, current_m3: null }, characterization: { previous: char("GLOBULAR", { type: "no_interpretable", azimuth: null, dip: null, note: null, reason: "similar_eigenvalues" }) } },
] as any[];
const totals = { available: true, provisional: true, previous: { sum_m3: 1036111, counted: 3, total: 3, excluded: [] }, current: { sum_m3: 986574, counted: 3, total: 3, excluded: [] }, difference_m3: -49537, difference_pct: -4.78, warnings: ["sum_of_bodies_not_union", "overlap_not_evaluated", "orientation_normalized"] };
const comparison = (over: object = {}) => ({ run: { id: "r", previous_id: "p", current_id: "c", state: "completed", total: 4, done: 4, error: null }, provisional: true, profile: "pilot-v1-provisional", summary: { "SIN CAMBIOS": 1, VARIABLE: 1, NUEVO: 1, ELIMINADO: 1, sin_clasificar: 0, pendientes: 0 }, totals, rows, ...over });

async function ready(over: object = {}) {
  sequences["GET /api/v1/datasets"] = [[ds("p", "2025"), ds("c", "2026")]];
  sequences["GET /api/v1/datasets/p"] = [detail("p", "2025")];
  sequences["GET /api/v1/datasets/c"] = [detail("c", "2026")];
  sequences["GET /api/v1/matches?previous=p&current=c"] = [matches];
  sequences["GET /api/v1/comparisons?previous=p&current=c"] = [comparison(over)];
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "p");
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "c");
  await screen.findByRole("table", { name: "Clasificación por sólido" });
  return user;
}
const panel = () => screen.getByRole("region", { name: "Clasificación de cambios" });

describe("dashboard helpers", () => {
  it("computes percentages over a stated base", () => {
    expect(percentOf(1, 4)).toBe("25 %");
    expect(percentOf(1, 3)).toBe("33 %");
    expect(percentOf(0, 0)).toBe("—");
  });

  it("counts solids per period: a removed solid only exists before, a new one only after", () => {
    const c = periodCounts(rows);
    expect(c.previous).toEqual({ total: 3, sinCambios: 1, variables: 1, nuevos: 0, eliminados: 1 });
    expect(c.current).toEqual({ total: 3, sinCambios: 1, variables: 1, nuevos: 1, eliminados: 0 });
  });

  it("counts a solid without a state only in the total", () => {
    const pending = { ...rows[0], key: "p_3", state: null, status: "pending" };
    expect(periodCounts([pending as any]).current).toEqual({ total: 1, sinCambios: 0, variables: 0, nuevos: 0, eliminados: 0 });
  });

  it("shows the volume difference: removed is -100, new has no base, never '-0.00'", () => {
    expect(diffPercent(rows[3])).toBe(-100);
    expect(diffPercent(rows[2])).toBeNull();
    expect(diffPercent(rows[1])).toBe(-4.8);
    expect(diffText(-4.8)).toBe("-4.80");
    expect(diffText(-0.001)).toBe("0.00");
    expect(diffText(null)).toBe("—");
  });

  it("filters by state and name", () => {
    const f = (o: object) => filterRows(rows, { state: "all", query: "", ...o }).map((r) => r.key);
    expect(f({ state: "VARIABLE" })).toEqual(["b_3"]);
    expect(f({ query: "NEW" })).toEqual(["new"]);
    expect(f({ state: "NUEVO", query: "a_3" })).toEqual([]);
  });
});

describe("board", () => {
  it("counts the solids per state with the percentage over the solids that have a state", async () => {
    await ready();
    const cards = within(panel()).getByRole("region", { name: "Resumen de resultados" });
    for (const [label, n] of [["Sin cambios", "1"], ["Variables", "1"], ["Nuevos", "1"], ["Eliminados", "1"]]) {
      const card = within(cards).getByText(label).closest("li")!;
      expect(card).toHaveTextContent(n);
      expect(card).toHaveTextContent("25 %");
    }
    expect(within(cards).getByText(/Porcentajes sobre 4 sólidos con estado/)).toBeInTheDocument();
  });

  it("charts the count of both periods for every situation, with the period names", async () => {
    await ready();
    const chart = within(panel()).getByRole("region", { name: "Conteo de sólidos" });
    expect(within(chart).getByLabelText("Total: 3 en 2025, 3 en 2026")).toBeInTheDocument();
    expect(within(chart).getByLabelText("Nuevos: 0 en 2025, 1 en 2026")).toBeInTheDocument();
    expect(within(chart).getByLabelText("Eliminados: 1 en 2025, 0 en 2026")).toBeInTheDocument();
  });

  it("compares the total volumes of both periods with the absolute and percentual difference", async () => {
    await ready();
    const card = within(panel()).getByRole("region", { name: "Volumen total" });
    expect(within(card).getByText(/Periodo anterior/)).toBeInTheDocument();
    expect(within(card).getByText("1,036,111 m³")).toBeInTheDocument();
    expect(within(card).getByText("986,574 m³")).toBeInTheDocument();
    expect(within(card).getByText(/−49,537 m³ \(−4\.8 %\)/)).toBeInTheDocument();
    expect(within(card).getByText(/suma de los volúmenes de cada sólido/i)).toBeInTheDocument();
    expect(within(card).getByText(/superposición entre sólidos no se evaluó/i)).toBeInTheDocument();
    expect(within(card).getByText(/orientación invertida/i)).toBeInTheDocument();
  });

  it("lists the solids left out of the totals", async () => {
    const t = { ...totals, previous: { ...totals.previous, counted: 2, excluded: [{ key: "x_3", reason: "not_watertight:previous" }] }, warnings: [...totals.warnings, "excluded_solids"] };
    const user = await ready({ totals: t });
    const card = within(panel()).getByRole("region", { name: "Volumen total" });
    expect(within(card).getByText(/2 de 3 sólidos del periodo anterior/)).toBeInTheDocument();
    await user.click(within(card).getByText(/Ver sólidos sin volumen/));
    expect(within(card).getByText(/x_3.*superficie no cerrada/)).toBeInTheDocument();
  });

  it("does not show totals until the comparison was calculated", async () => {
    await ready({ totals: { available: false, reason: "pending" } });
    expect(within(panel()).queryByRole("region", { name: "Volumen total" })).not.toBeInTheDocument();
  });

  it("has one table: type, state, both volumes, difference, Azimuth and Dip", async () => {
    await ready();
    const table = within(panel()).getByRole("table", { name: "Clasificación por sólido" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Sólido", "Tipo de cuerpo", "Estado", "Volumen (m³)2025", "Volumen (m³)2026", "Dif. %", "Azimuth (°)", "Dip (°)", "Acciones"]);
    const cells = (k: string) => within(within(table).getAllByRole("row").find((r) => within(r).queryByText(k, { exact: true }))!).getAllByRole("cell").map((c) => c.textContent);
    expect(cells("b_3").slice(0, 8)).toEqual(["b_3", "Tabular → Tabular curvo", "Variable", "1,034,768.000", "984,845.000", "-4.80", "82.00", "44.00"]);
    expect(cells("a_3").slice(2, 6)).toEqual(["Sin cambios", "1,000.000", "1,000.000", "0.00"]);
    expect(cells("new").slice(3, 8)).toEqual(["—", "729.000", "—", "60.00eje", "20.00"]);
    expect(cells("old").slice(2, 8)).toEqual(["Eliminado", "343.000", "—", "-100.00", "—", "—"]);
  });

  it("filters the table by state and by name", async () => {
    const user = await ready();
    const table = () => within(panel()).getByRole("table", { name: "Clasificación por sólido" });
    await user.click(within(panel()).getByRole("button", { name: /Variables \(1\)/ }));
    expect(within(table()).getAllByRole("row")).toHaveLength(2);
    await user.click(within(panel()).getByRole("button", { name: /Todos/ }));
    await user.type(within(panel()).getByLabelText("Buscar en la clasificación"), "old");
    expect(within(table()).getAllByRole("row")).toHaveLength(2);
    expect(within(panel()).getByText("1 de 4 sólidos")).toBeInTheDocument();
  });

  it("lets the reviewer pick the solid to inspect from a list, and opens it in 3D", async () => {
    sequencesFor3d();
    const user = await ready();
    const select = screen.getByLabelText("Filtrar sólido");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Elige el sólido que vas a revisar…", "a_3", "b_3", "new", "old"]);
    await user.selectOptions(select, "b_3");
    expect(await screen.findByRole("heading", { name: /Vista 3D · b_3/ })).toBeInTheDocument();
    await user.selectOptions(select, "");
    expect(screen.queryByRole("heading", { name: /Vista 3D/ })).not.toBeInTheDocument();
  });
});

function sequencesFor3d() {
  sequences["GET /api/v1/scene?previous=p&current=c&key=b_3"] = [{ key: "b_3", origin: null, axes: "y", layers: [] }];
}
