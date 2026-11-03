import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { POLL_MS } from "../src/config";
import { describeRule, describeWarning } from "../src/format";

let sequences: Record<string, unknown[]> = {};

beforeEach(() => {
  POLL_MS.qc = 10;
  POLL_MS.characterization = 10;
  POLL_MS.comparison = 10;
  sequences = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      const queue = sequences[key];
      if (!queue) {
        if (/\/(qc|characterization)$/.test(url)) return { ok: true, status: 200, json: async () => ({ run: null, summary: { ok: 0, failed: 0, pending: 0, with_issues: 0 }, results: [] }) } as Response;
        throw new Error(`unmocked ${key}`);
      }
      const next = (queue.length > 1 ? queue.shift() : queue[0]) as any;
      const status = next && typeof next === "object" && "__status" in next ? next.__status : 200;
      return { ok: status < 400, status, json: async () => (status < 400 ? next : next.body) } as Response;
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const ds = (id: string, label: string) => ({ id, name: "Modelo", period_label: label, period_kind: "annual", revision: 1, is_demo: false, spatial_reference: null, units: null, state: "closed", created_at: "x", file_count: 4 });
const entry = (filename: string, key: string) => ({ filename, key, sha256: "0".repeat(64), size_bytes: 1 });
const detail = (id: string, label: string) => ({ ...ds(id, label), files: [entry("a.obj", "a")], incidents: [], counts: { files: 1, keys: 1 }, orientation_reference_count: 0 });
const matches = { pairs: [{ key: "a_3", previous: entry("a_3pt.obj", "a_3"), current: entry("a_3.obj", "a_3") }, { key: "b_3", previous: entry("b_3pt.obj", "b_3"), current: entry("b_3.obj", "b_3") }], only_previous: [entry("old.obj", "old")], only_current: [entry("new.obj", "new")], incidents: [] };
const url = "/api/v1/comparisons?previous=p&current=c";
const run = (state: string, done: number, extra: object = {}) => ({ id: "r", previous_id: "p", current_id: "c", state, total: 2, done, error: null, ...extra });
const base = (key: string, over: object) => ({
  key, previous_filename: `${key}pt.obj`, current_filename: `${key}.obj`, status: "ok", technical_status: "ok", state: "SIN CAMBIOS", subtype: "IDENTICO",
  description: "SIN CAMBIO: coincidencia prácticamente total (IoU 100.00 %).", events: [], checks: [], incidents: [], warnings: [], reasons: {},
  metrics: { iou_pct: 100, delta_volume_pct: 0, p95_m: 0, centroid_m: 0 }, volumes: {}, provisional: true, profile: "pilot-v1-provisional", ...over,
});
const summary = (o: object) => ({ "SIN CAMBIOS": 0, VARIABLE: 0, NUEVO: 0, ELIMINADO: 0, sin_clasificar: 0, pendientes: 0, ...o });
const nuevo = { ...base("new", { previous_filename: null, current_filename: "new.obj", status: "n/a", state: "NUEVO", subtype: null, metrics: null, description: "El sólido no existía en el periodo anterior. Se determina por nombre normalizado: si fue renombrado, puede ser un falso NUEVO y conviene revisarlo." }) };
const eliminado = { ...base("old", { previous_filename: "old.obj", current_filename: null, status: "n/a", state: "ELIMINADO", subtype: null, metrics: null, description: "El sólido existía en el periodo anterior pero no existe en el periodo actual. Se determina por nombre normalizado: si fue renombrado, puede ser un falso ELIMINADO y conviene revisarlo." }) };
const variable = base("b_3", {
  state: "VARIABLE", subtype: "VARIABLE", events: ["RECORTE"], description: "RECORTE: se eliminó parte del sólido (volumen removido 8.0 % del anterior; agregado 1.0 % del actual).",
  metrics: { iou_pct: 92.04, delta_volume_pct: -6.9, p95_m: 1.05, centroid_m: 0.5 },
  checks: [{ rule: "iou", group: "no_significativo", observed: 92.04, op: ">=", threshold: 90, passed: true, applicable: true }, { rule: "removido", group: "no_significativo", observed: 8.0, op: "<=", threshold: 10, passed: true, applicable: true }],
  warnings: ["inverted_orientation_normalized:previous", "self_intersections:current"],
});
const identical = base("a_3", {});
const full = (extra: object[] = []) => ({ run: run("completed", 2), provisional: true, profile: "pilot-v1-provisional", summary: summary({ "SIN CAMBIOS": 1, VARIABLE: 1, NUEVO: 1, ELIMINADO: 1 }), rows: [identical, variable, nuevo, eliminado, ...extra] });
const empty = { run: null, provisional: true, profile: "pilot-v1-provisional", summary: summary({ NUEVO: 1, ELIMINADO: 1, pendientes: 2 }), rows: [nuevo, eliminado, { ...base("a_3", { status: "pending", state: null, subtype: null, metrics: null, description: "Pendiente" }) }] };

async function ready() {
  sequences["GET /api/v1/datasets"] = [[ds("p", "2025"), ds("c", "2026")]];
  sequences["GET /api/v1/datasets/p"] = [detail("p", "2025")];
  sequences["GET /api/v1/datasets/c"] = [detail("c", "2026")];
  sequences["GET /api/v1/matches?previous=p&current=c"] = [matches];
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "p");
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "c");
  await screen.findByRole("region", { name: "Clasificación de cambios" });
  return user;
}
const panel = () => screen.getByRole("region", { name: "Clasificación de cambios" });

describe("classification panel", () => {
  it("explains that results are provisional and invites the user to calculate", async () => {
    sequences[`GET ${url}`] = [empty];
    await ready();
    expect(await screen.findByRole("button", { name: "Calcular cambios entre los dos periodos" })).toBeEnabled();
    expect(screen.getByText(/Resultados provisionales/)).toBeInTheDocument();
    expect(screen.getByText(/orientación de las caras normalizada/)).toBeInTheDocument();
  });

  it("lists every solid before calculating, knows new and removed by name, and shows no counts yet", async () => {
    sequences[`GET ${url}`] = [empty];
    await ready();
    const table = await screen.findByRole("table", { name: "Clasificación por sólido" });
    const rowOf = (k: string) => within(table).getAllByRole("row").find((r) => within(r).queryByText(k, { exact: true }))!;
    expect(within(rowOf("new")).getByText("Nuevo")).toBeInTheDocument();
    expect(within(rowOf("old")).getByText("Eliminado")).toBeInTheDocument();
    expect(within(rowOf("a_3")).getByText("Pendiente")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Resumen de resultados" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Conteo de sólidos" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Resumen de resultados (pendiente)" })).toBeInTheDocument();
  });

  it("shows progress and then the four states with their counts", async () => {
    sequences[`GET ${url}`] = [empty, ...Array(12).fill({ ...empty, run: run("running", 1) }), full()];
    sequences["POST /api/v1/comparisons"] = [run("queued", 0)];
    const user = await ready();
    await user.click(await screen.findByRole("button", { name: "Calcular cambios entre los dos periodos" }));
    expect(await screen.findByText(/1 de 2 pares listos/)).toBeInTheDocument();
    const cards = await screen.findByRole("region", { name: "Resumen de resultados" });
    for (const label of ["Sin cambios", "Variables", "Nuevos", "Eliminados"])
      expect(within(cards).getByText(label).closest("li")).toHaveTextContent(/1\s*25 %/);
  });

  it("lists every solid with its state as text and a plain-language description", async () => {
    sequences[`GET ${url}`] = [full()];
    await ready();
    const table = await screen.findByRole("table", { name: "Clasificación por sólido" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(5);
    const byKey = (k: string) => rows.find((r) => within(r).queryByText(k, { exact: true }))!;
    expect(within(byKey("b_3")).getByText("Variable")).toBeInTheDocument();
    expect(within(byKey("b_3")).getByText("-6.90")).toBeInTheDocument();
    expect(within(byKey("new")).getByText("Nuevo")).toBeInTheDocument();
    expect(within(byKey("old")).getByText("Eliminado")).toBeInTheDocument();
    expect(within(byKey("a_3")).getByText("Sin cambios")).toBeInTheDocument();
    expect(table.textContent).not.toMatch(/NaN|null|undefined/);
  });

  it("keeps the plain-language description of a solid one click away", async () => {
    sequences[`GET ${url}`] = [full()];
    const user = await ready();
    await screen.findByRole("table", { name: "Clasificación por sólido" });
    await user.click(screen.getByRole("button", { name: "Por qué: b_3" }));
    expect(within(screen.getByRole("region", { name: "Por qué: b_3" })).getByText(/RECORTE: se eliminó parte del sólido/)).toBeInTheDocument();
  });

  it("never shows a negative zero for a tiny volume change", async () => {
    const tiny = base("a_3", { metrics: { iou_pct: 100, delta_volume_pct: -0.0004, p95_m: 0, centroid_m: 0 } });
    sequences[`GET ${url}`] = [{ ...full(), rows: [tiny, variable, nuevo, eliminado] }];
    await ready();
    const table = await screen.findByRole("table", { name: "Clasificación por sólido" });
    expect(table.textContent).not.toMatch(/-0\.00/);
  });

  it("filters by state", async () => {
    sequences[`GET ${url}`] = [full()];
    const user = await ready();
    await screen.findByRole("table", { name: "Clasificación por sólido" });
    await user.click(within(panel()).getByRole("button", { name: /^Variables \(1\)$/ }));
    expect(within(screen.getByRole("table", { name: "Clasificación por sólido" })).getAllByRole("row")).toHaveLength(2);
    await user.click(within(panel()).getByRole("button", { name: /^Todos \(4\)$/ }));
    expect(within(screen.getByRole("table", { name: "Clasificación por sólido" })).getAllByRole("row")).toHaveLength(5);
  });

  it("explains why: every rule with its observed value and threshold, and the reliability warnings", async () => {
    sequences[`GET ${url}`] = [full()];
    const user = await ready();
    await screen.findByRole("table", { name: "Clasificación por sólido" });
    await user.click(screen.getByRole("button", { name: "Por qué: b_3" }));
    const why = screen.getByRole("region", { name: "Por qué: b_3" });
    expect(within(why).getByText(/Coincidencia \(IoU\)/)).toBeInTheDocument();
    expect(within(why).getByText(/92\.0 %.*mínimo 90\.0 %/)).toBeInTheDocument();
    expect(within(why).getByText(/El periodo anterior tiene la orientación invertida/)).toBeInTheDocument();
    expect(within(why).getByText(/El periodo actual tiene caras que se cruzan/)).toBeInTheDocument();
  });

  it("keeps a failed pair out of the four states and says so", async () => {
    const failed = base("x_3", { status: "failed", technical_status: "failed", state: null, subtype: null, metrics: null, description: "No se pudo clasificar: el análisis del par falló (timeout after 300 s).", incidents: [{ code: "pair_failed" }] });
    sequences[`GET ${url}`] = [{ ...full([failed]), run: run("completed_with_issues", 3), summary: summary({ "SIN CAMBIOS": 1, VARIABLE: 1, NUEVO: 1, ELIMINADO: 1, sin_clasificar: 1 }) }];
    await ready();
    expect(await screen.findByText(/1 sin clasificar/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Clasificación por sólido" });
    expect(within(table).getByText("Sin clasificar")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Por qué: x_3" }));
    expect(within(screen.getByRole("region", { name: "Por qué: x_3" })).getByText(/tardó demasiado/)).toBeInTheDocument();
  });

  it("offers the CSV report and a retry after an interruption", async () => {
    sequences[`GET ${url}`] = [{ ...full(), run: run("failed", 1, { error: "interrupted by a restart" }) }];
    await ready();
    expect(await screen.findByText(/El cálculo se interrumpió/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar el cálculo" })).toBeEnabled();
    const link = screen.getByRole("link", { name: /Descargar reporte de comparación/ });
    expect(link).toHaveAttribute("href", "/api/v1/comparisons/report.csv?previous=p&current=c");
  });

  it("opens the 3D view from a row of the classification", async () => {
    sequences[`GET ${url}`] = [full()];
    sequences["GET /api/v1/scene?previous=p&current=c&key=b_3"] = [{ key: "b_3", origin: null, axes: "y", layers: [] }];
    const user = await ready();
    await screen.findByRole("table", { name: "Clasificación por sólido" });
    await user.click(within(panel()).getByRole("button", { name: "Ver en 3D: b_3" }));
    expect(await screen.findByRole("heading", { name: /Vista 3D · b_3/ })).toBeInTheDocument();
  });

  it("describes rules and warnings in Spanish", () => {
    expect(describeRule({ rule: "iou", group: "no_significativo", observed: 93, op: ">=", threshold: 90, passed: true, applicable: true })).toBe("Coincidencia (IoU): 93.0 % (mínimo 90.0 %)");
    expect(describeRule({ rule: "p95", group: "identico", observed: 0.2, op: "<=", threshold: 0.1, passed: false, applicable: true })).toBe("Distancia entre superficies (P95): 0.20 m (máximo 0.10 m)");
    expect(describeRule({ rule: "orientacion", group: "identico", observed: null, op: "<=", threshold: null, passed: true, applicable: false })).toMatch(/no aplica/);
    expect(describeWarning("inverted_orientation_normalized:current")).toMatch(/periodo actual tiene la orientación invertida/);
    expect(describeWarning("algo_nuevo")).toBe("algo_nuevo");
  });
});
