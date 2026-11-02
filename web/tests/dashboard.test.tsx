import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { deltaVolumes, filterRows, percentOf, polarPoint } from "../src/dashboard";
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
  it("builds volume differences per solid, signed, excluding the ones without a volume", () => {
    const d = deltaVolumes(rows);
    expect(d.map((x) => [x.key, Math.round(x.delta)])).toEqual([["b_3", -49923], ["new", 729], ["old", -343]]); // a_3 changed by 0: kept out of the ranking
    expect(deltaVolumes([{ ...rows[1], volumes: { previous_m3: null, current_m3: 5 } } as any])).toEqual([]);
  });
  it("places a solid on the polar plot: azimuth is the angle from North, dip the distance from the centre", () => {
    const north = polarPoint(0, 90, 100), east = polarPoint(90, 90, 100), centre = polarPoint(123, 0, 100);
    expect(north.x).toBeCloseTo(0);
    expect(north.y).toBeCloseTo(-100);
    expect(east.x).toBeCloseTo(100);
    expect(east.y).toBeCloseTo(0);
    expect(centre.x).toBeCloseTo(0);
    expect(centre.y).toBeCloseTo(0);
  });
  it("filters by state, body type in a chosen period, volume range and name", () => {
    const f = (o: object) => filterRows(rows, { state: "all", type: "", scope: "any", min: null, max: null, query: "", ...o }).map((r) => r.key);
    expect(f({ state: "VARIABLE" })).toEqual(["b_3"]);
    expect(f({ type: "TABULAR CURVO", scope: "current" })).toEqual(["b_3"]);
    expect(f({ type: "TABULAR CURVO", scope: "previous" })).toEqual([]);
    expect(f({ type: "TABULAR CURVO", scope: "any" })).toEqual(["b_3"]);
    expect(f({ min: 500, max: 2000, scope: "current" })).toEqual(["a_3", "new"]);
    expect(f({ min: 300, max: 400, scope: "previous" })).toEqual(["old"]);
    expect(f({ query: "NEW" })).toEqual(["new"]);
  });
});

describe("dashboard panel", () => {
  it("shows counts and percentages over the solids that have a state, and says the base", async () => {
    await ready();
    const chips = screen.getByRole("list", { name: "Resumen de estados" });
    expect(within(chips).getByText("1 sin cambios (25 %)")).toBeInTheDocument();
    expect(within(chips).getByText("1 variable (25 %)")).toBeInTheDocument();
    expect(within(chips).getByText("1 nuevo (25 %)")).toBeInTheDocument();
    expect(within(chips).getByText("1 eliminado (25 %)")).toBeInTheDocument();
    expect(within(panel()).getByText(/Porcentajes sobre 4 sólidos con estado/)).toBeInTheDocument();
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

  it("draws the volume difference of every solid as readable bars, new and removed included", async () => {
    await ready();
    const chart = within(panel()).getByRole("region", { name: "Diferencia de volumen por sólido" });
    const items = within(chart).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      expect.stringContaining("b_3"), expect.stringContaining("new"), expect.stringContaining("old"),
    ]);
    expect(within(items[0]).getByText(/−49,923 m³/)).toBeInTheDocument();
    expect(within(items[0]).getByText("Variable")).toBeInTheDocument();
    expect(within(items[1]).getByText(/\+729 m³/)).toBeInTheDocument();
    expect(within(items[2]).getByText("Eliminado")).toBeInTheDocument();
  });

  it("plots Azimuth and Dip of both periods and opens the 3D view from a point", async () => {
    sequencesFor3d();
    const user = await ready();
    const chart = within(panel()).getByRole("region", { name: "Orientación de los sólidos" });
    const svg = within(chart).getByRole("img", { name: /Azimuth.*Dip/ });
    expect(svg.querySelectorAll("circle[data-period]").length).toBe(5); // a_3 x2, b_3 x2, new x1 (old has no interpretable orientation)
    expect(within(chart).getByText(/1 sólido sin orientación interpretable/)).toBeInTheDocument();
    await user.click(within(chart).getByRole("button", { name: /Ver b_3 en el visor 3D/ }));
    expect(await screen.findByRole("heading", { name: /Vista 3D · b_3/ })).toBeInTheDocument();
  });

  it("shows type, volumes and orientation in the table and filters by type, volume range and name", async () => {
    const user = await ready();
    const table = () => within(panel()).getByRole("table", { name: "Clasificación por sólido" });
    const rowOf = (k: string) => within(table()).getAllByRole("row").find((r) => within(r).queryByText(k, { exact: true }))!;
    expect(within(rowOf("b_3")).getByText("Tabular → Tabular curvo")).toBeInTheDocument();
    expect(within(rowOf("b_3")).getByText("1,034,768 → 984,845")).toBeInTheDocument();
    expect(within(rowOf("b_3")).getByText("Azimuth 82.0° · Dip 44.0°")).toBeInTheDocument();
    expect(within(rowOf("new")).getByText("Eje: Trend 60.0° · Plunge 20.0°")).toBeInTheDocument();
    expect(within(rowOf("old")).getByText("sin orientación interpretable")).toBeInTheDocument();

    await user.selectOptions(within(panel()).getByLabelText("Tipo de cuerpo"), "GLOBULAR");
    expect(within(table()).getAllByRole("row")).toHaveLength(3);
    expect(within(panel()).getByText("2 de 4 sólidos")).toBeInTheDocument();
    await user.selectOptions(within(panel()).getByLabelText("Tipo de cuerpo"), "");
    await user.selectOptions(within(panel()).getByLabelText("Aplicar tipo y volumen al periodo"), "previous");
    await user.type(within(panel()).getByLabelText("Volumen mínimo (m³)"), "500");
    expect(within(table()).getAllByRole("row")).toHaveLength(3); // a_3 (1,000) and b_3 (1,034,768)
    expect(within(panel()).getByText(/volumen del periodo anterior/i)).toBeInTheDocument();
    await user.clear(within(panel()).getByLabelText("Volumen mínimo (m³)"));
    await user.type(within(panel()).getByLabelText("Buscar en la clasificación"), "old");
    expect(within(table()).getAllByRole("row")).toHaveLength(2);
  });
});

function sequencesFor3d() {
  sequences["GET /api/v1/scene?previous=p&current=c&key=b_3"] = [{ key: "b_3", origin: null, axes: "y", layers: [] }];
}
