import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { POLL_MS } from "../src/config";
import { bodyTypeLabel, describeOrientation, describeReference } from "../src/format";

let sequences: Record<string, unknown[]> = {};

beforeEach(() => {
  POLL_MS.qc = 10;
  POLL_MS.characterization = 10;
  sequences = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      const queue = sequences[key];
      if (!queue) {
        if (url.endsWith("/qc")) return { ok: true, status: 200, json: async () => ({ run: null, summary: { ok: 0, with_issues: 0, failed: 0, pending: 2 }, results: [] }) } as Response;
        throw new Error(`unmocked ${key}`);
      }
      const next = (queue.length > 1 ? queue.shift() : queue[0]) as any;
      const status = next && typeof next === "object" && "__status" in next ? next.__status : 200;
      return { ok: status < 400, status, json: async () => (status < 400 ? next : next.body) } as Response;
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const ds = { id: "p", name: "Modelo", period_label: "2025", period_kind: "annual", revision: 1, is_demo: false, spatial_reference: null, units: null, state: "closed", created_at: "x", file_count: 3 };
const entry = (filename: string) => ({ filename, key: filename.replace(".obj", ""), sha256: "0".repeat(64), size_bytes: 1024 });
const detail = { ...ds, files: [entry("a.obj"), entry("b.obj"), entry("c.obj")], incidents: [], counts: { files: 3, keys: 3 }, orientation_reference_count: 0 };
const run = (state: string, done: number, extra: object = {}) => ({ id: "r", dataset_id: "p", state, total: 3, done, error: null, ...extra });
const planar = (az: number, dip: number) => ({ type: "planar", azimuth: az, dip, note: null, reason: null });
const result = (filename: string, body_type: string, orientation: object, extra: object = {}) => ({ ...entry(filename), status: "ok", error: null, body_type, orientation, eigenvalues: [900, 300, 1], reference: null, volume_m3: { value: null, reason: "qc_pendiente" }, ...extra });
const summary = (o: object) => ({ ok: 0, failed: 0, pending: 0, ...o });
const pending = { run: null, summary: summary({ pending: 3 }), results: [] };

async function openPeriod() {
  sequences["GET /api/v1/datasets"] = [[ds]];
  sequences["GET /api/v1/datasets/p"] = [detail];
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "p");
  await screen.findByText("Listo");
  return user;
}

describe("type and orientation panel", () => {
  it("invites the user to calculate before anything was calculated", async () => {
    sequences["GET /api/v1/datasets/p/characterization"] = [pending];
    await openPeriod();
    expect(await screen.findByRole("button", { name: "Calcular tipo y orientación" })).toBeEnabled();
    expect(screen.getByText(/Todavía no se calculó/)).toBeInTheDocument();
  });

  it("shows progress and then how many solids of each type there are", async () => {
    sequences["GET /api/v1/datasets/p/characterization"] = [
      pending,
      { run: run("running", 1), summary: summary({ ok: 1, pending: 2 }), results: [] },
      { run: run("completed", 3), summary: summary({ ok: 3 }), results: [result("a.obj", "TABULAR", planar(193, 70.3)), result("b.obj", "TABULAR CURVO", planar(234.1, 73.2)), result("c.obj", "GLOBULAR", { type: "axial", azimuth: 60, dip: 20, note: null, reason: null })] },
    ];
    sequences["POST /api/v1/datasets/p/characterization"] = [run("queued", 0)];
    const user = await openPeriod();
    await user.click(await screen.findByRole("button", { name: "Calcular tipo y orientación" }));
    expect(await screen.findByText(/1 de 3 listos/)).toBeInTheDocument();
    expect(await screen.findByText(/3 sólidos caracterizados/)).toBeInTheDocument();
    expect(screen.getByText(/1 tabular, 1 tabular curvo, 1 globular/)).toBeInTheDocument();
    expect(screen.getByText(/umbrales.*provisionales/i)).toBeInTheDocument();
  });

  it("describes each orientation in plain words, never showing blanks or NaN", async () => {
    sequences["GET /api/v1/datasets/p/characterization"] = [{
      run: run("completed", 3), summary: summary({ ok: 3 }),
      results: [
        result("a.obj", "TABULAR", planar(193, 70.3)),
        result("b.obj", "GLOBULAR", { type: "axial", azimuth: 60, dip: 20, note: null, reason: null }),
        result("c.obj", "GLOBULAR", { type: "no_interpretable", azimuth: null, dip: null, note: null, reason: "similar_eigenvalues" }),
      ],
    }];
    const user = await openPeriod();
    await user.click(await screen.findByText(/Ver detalle por sólido/));
    const table = screen.getByRole("table", { name: "Tipo y orientación por sólido" });
    const rows = within(table).getAllByRole("row");
    expect(within(rows[1]).getByText("Tabular")).toBeInTheDocument();
    expect(within(rows[1]).getByText(/Azimuth 193.0° · Dip 70.3°/)).toBeInTheDocument();
    expect(within(rows[2]).getByText(/Eje: Trend 60.0° · Plunge 20.0°/)).toBeInTheDocument();
    expect(within(rows[3]).getByText(/No interpretable.*muy parecidos/)).toBeInTheDocument();
    expect(table.textContent).not.toMatch(/NaN|null|undefined/);
  });

  it("contrasts the computed orientation with the reference table and summarises the differences", async () => {
    const ref = (az: number, dip: number, comparison: object) => ({ filename: "x.obj", orientation_type: "planar", azimuth: az, dip, method: "Studio RM", observations: "", comparison });
    sequences["GET /api/v1/datasets/p/characterization"] = [{
      run: run("completed", 3), summary: summary({ ok: 3 }),
      results: [
        result("a.obj", "TABULAR", planar(193, 70), { reference: ref(195, 69, { comparable: true, delta_azimuth_deg: 2, delta_dip_deg: 1 }) }),
        result("b.obj", "TABULAR", planar(10, 40), { reference: ref(15, 38, { comparable: true, delta_azimuth_deg: 5, delta_dip_deg: 2 }) }),
        result("c.obj", "GLOBULAR", { type: "no_interpretable", azimuth: null, dip: null, note: null, reason: "similar_eigenvalues" }, { reference: ref(1, 2, { comparable: false, reason: "not_interpretable" }) }),
      ],
    }];
    const user = await openPeriod();
    expect(await screen.findByText(/2 de 3 sólidos comparables con la referencia/)).toBeInTheDocument();
    expect(screen.getByText(/diferencia máxima de 5.0° en azimuth y de 2.0° en dip/)).toBeInTheDocument();
    await user.click(screen.getByText(/Ver detalle por sólido/));
    expect(screen.getByText(/Studio RM: 195.0° \/ 69.0° → diferencia 2.0° \/ 1.0°/)).toBeInTheDocument();
    expect(screen.getByText(/No comparable: la orientación calculada no es interpretable/)).toBeInTheDocument();
  });

  it("reports a failed solid without hiding the rest and lets the user download the report", async () => {
    sequences["GET /api/v1/datasets/p/characterization"] = [{
      run: run("completed_with_issues", 3), summary: summary({ ok: 2, failed: 1 }),
      results: [result("a.obj", "TABULAR", planar(1, 2)), result("b.obj", "TABULAR", planar(3, 4)), { ...entry("c.obj"), status: "failed", error: "timeout after 180 s", body_type: null, orientation: null, eigenvalues: null, reference: null, volume_m3: null }],
    }];
    await openPeriod();
    expect(await screen.findByText(/1 no se pudo calcular/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Descargar reporte de orientación/ });
    expect(link).toHaveAttribute("href", "/api/v1/datasets/p/characterization.csv");
  });

  it("lets the user retry when the calculation was interrupted", async () => {
    sequences["GET /api/v1/datasets/p/characterization"] = [{ run: run("failed", 1, { error: "interrupted by a restart" }), summary: summary({ ok: 1, pending: 2 }), results: [] }];
    await openPeriod();
    expect(await screen.findByText(/El cálculo se interrumpió/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar el cálculo" })).toBeEnabled();
  });

  it("formats labels and orientations", () => {
    expect(bodyTypeLabel("TABULAR CURVO")).toBe("Tabular curvo");
    expect(bodyTypeLabel("GLOBULAR")).toBe("Globular");
    expect(describeOrientation(planar(5, 6.04))).toBe("Azimuth 5.0° · Dip 6.0°");
    expect(describeOrientation({ type: "planar", azimuth: null, dip: 0, note: "horizontal_plane", reason: "horizontal_plane" })).toMatch(/plano horizontal/i);
    expect(describeOrientation({ type: "planar", azimuth: 10, dip: 90, note: "vertical_plane_direction_ambiguous", reason: null })).toMatch(/plano vertical/);
    expect(describeReference({ method: "Leapfrog", azimuth: 1, dip: 2, comparison: { comparable: false, reason: "different_orientation_type" } })).toMatch(/tipos de orientación distintos/);
  });
});
