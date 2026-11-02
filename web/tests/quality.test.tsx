import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { POLL_MS } from "../src/config";
import { describeProblem } from "../src/format";

type Json = unknown;
let sequences: Record<string, Json[]> = {};
const calls: string[] = [];

beforeEach(() => {
  POLL_MS.qc = 10;
  sequences = {};
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      calls.push(key);
      const queue = sequences[key];
      if (!queue) throw new Error(`unmocked ${key}`);
      const next = queue.length > 1 ? queue.shift() : queue[0];
      const out = next as any;
      const status = out && typeof out === "object" && "__status" in out ? out.__status : 200;
      return { ok: status < 400, status, json: async () => (status < 400 ? out : out.body) } as Response;
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const ds = { id: "p", name: "Modelo", period_label: "2025", period_kind: "annual", revision: 1, is_demo: false, spatial_reference: null, units: null, state: "closed", created_at: "x", file_count: 2 };
const entry = (filename: string) => ({ filename, key: filename.replace(".obj", ""), sha256: "0".repeat(64), size_bytes: 1024 });
const detail = { ...ds, files: [entry("a.obj"), entry("b.obj")], incidents: [], counts: { files: 2, keys: 2 }, orientation_reference_count: 0 };
const run = (state: string, done: number, extra: object = {}) => ({ id: "r1", dataset_id: "p", state, total: 2, done, error: null, ...extra });
const metric = (value: number | null, reason: string | null = null) => ({ value, validity: value === null ? "unavailable" : "valid", reason });
const clean = (filename: string) => ({ ...entry(filename), status: "ok", problems: [], error: null, signed_volume_m3: 10, volume_m3: metric(10), orientation: "outward", open_edges: 0, non_manifold_edges: 0, self_intersections: metric(0), components: metric(1) });
const inverted = (filename: string) => ({ ...entry(filename), status: "with_issues", problems: ["inverted_orientation", "self_intersections"], error: null, signed_volume_m3: -984844.8, volume_m3: metric(null, "inverted_orientation"), orientation: "inverted", open_edges: 0, non_manifold_edges: 0, self_intersections: metric(75), components: metric(1) });
const failedFile = (filename: string) => ({ ...entry(filename), status: "failed", problems: [], error: "timeout after 180 s" });
const summary = (o: object) => ({ ok: 0, with_issues: 0, failed: 0, pending: 0, ...o });

async function openPeriod() {
  sequences["GET /api/v1/datasets"] = [[ds]];
  sequences["GET /api/v1/datasets/p"] = [detail];
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "p");
  await screen.findByText("Listo");
  return user;
}
const pending = { run: null, summary: summary({ pending: 2 }), results: [{ ...entry("a.obj"), status: "pending", problems: [], error: null }, { ...entry("b.obj"), status: "pending", problems: [], error: null }] };

describe("quality panel", () => {
  it("invites the user to review the meshes before anything was reviewed", async () => {
    sequences["GET /api/v1/datasets/p/qc"] = [pending];
    await openPeriod();
    expect(await screen.findByRole("button", { name: "Revisar calidad de las mallas" })).toBeEnabled();
    expect(screen.getByText(/Todavía no se revisó/)).toBeInTheDocument();
  });

  it("starts the review, shows progress and then a plain-language summary", async () => {
    sequences["GET /api/v1/datasets/p/qc"] = [
      pending,
      { run: run("running", 1), summary: summary({ pending: 1, ok: 1 }), results: [clean("a.obj"), { ...entry("b.obj"), status: "pending", problems: [], error: null }] },
      { run: run("completed", 2), summary: summary({ ok: 1, with_issues: 1 }), results: [clean("a.obj"), inverted("b.obj")] },
    ];
    sequences["POST /api/v1/datasets/p/qc"] = [run("queued", 0)];
    const user = await openPeriod();
    await user.click(await screen.findByRole("button", { name: "Revisar calidad de las mallas" }));
    expect(await screen.findByText(/1 de 2 listas/)).toBeInTheDocument();
    expect(await screen.findByText(/2 sólidos revisados/)).toBeInTheDocument();
    expect(screen.getByText(/1 sin observaciones/)).toBeInTheDocument();
    expect(screen.getByText(/1 con observaciones/)).toBeInTheDocument();
    expect(screen.getByText(/orientación invertida.*volumen no se puede confirmar/i)).toBeInTheDocument();
  });

  it("explains each solid's problems in Spanish and never shows a volume that is not confirmed", async () => {
    sequences["GET /api/v1/datasets/p/qc"] = [{ run: run("completed", 2), summary: summary({ ok: 1, with_issues: 1 }), results: [clean("a.obj"), inverted("b.obj")] }];
    const user = await openPeriod();
    await user.click(await screen.findByText(/Ver detalle por sólido/));
    const table = screen.getByRole("table", { name: "Calidad por sólido" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText("Sin observaciones")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Con observaciones")).toBeInTheDocument();
    expect(within(rows[2]).getByText(/La orientación global está invertida/)).toBeInTheDocument();
    expect(within(rows[2]).getByText(/75 caras se cruzan entre sí/)).toBeInTheDocument();
    expect(within(rows[2]).getByText(/Volumen: no confirmado/)).toBeInTheDocument();
    expect(within(rows[2]).queryByText(/984/)).not.toBeInTheDocument();
  });

  it("reports a file that could not be reviewed without hiding the others", async () => {
    sequences["GET /api/v1/datasets/p/qc"] = [{ run: run("completed_with_issues", 2), summary: summary({ ok: 1, failed: 1 }), results: [clean("a.obj"), failedFile("b.obj")] }];
    const user = await openPeriod();
    expect(await screen.findByText(/1 no se pudo revisar/)).toBeInTheDocument();
    await user.click(screen.getByText(/Ver detalle por sólido/));
    expect(screen.getByText("No se pudo revisar")).toBeInTheDocument();
    expect(screen.getByText(/tardó demasiado/)).toBeInTheDocument();
  });

  it("offers the CSV report once there are results", async () => {
    sequences["GET /api/v1/datasets/p/qc"] = [{ run: run("completed", 2), summary: summary({ ok: 2 }), results: [clean("a.obj"), clean("b.obj")] }];
    await openPeriod();
    const link = await screen.findByRole("link", { name: /Descargar reporte/ });
    expect(link).toHaveAttribute("href", "/api/v1/datasets/p/qc.csv");
    expect(link).toHaveAttribute("download");
  });

  it("keeps following a review that was already running when the page opened", async () => {
    sequences["GET /api/v1/datasets/p/qc"] = [
      { run: run("running", 1), summary: summary({ ok: 1, pending: 1 }), results: [clean("a.obj"), { ...entry("b.obj"), status: "pending", problems: [], error: null }] },
      { run: run("completed", 2), summary: summary({ ok: 2 }), results: [clean("a.obj"), clean("b.obj")] },
    ];
    await openPeriod();
    expect(await screen.findByText(/1 de 2 listas/)).toBeInTheDocument();
    expect(await screen.findByText(/2 sólidos revisados/)).toBeInTheDocument();
  });

  it("lets the user retry when the review was interrupted", async () => {
    sequences["GET /api/v1/datasets/p/qc"] = [{ run: run("failed", 1, { error: "interrupted by a restart" }), summary: summary({ ok: 1, pending: 1 }), results: [clean("a.obj"), { ...entry("b.obj"), status: "pending", problems: [], error: null }] }];
    await openPeriod();
    expect(await screen.findByText(/La revisión se interrumpió/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar la revisión" })).toBeEnabled();
  });

  it("shows a clear message when the review cannot start", async () => {
    sequences["GET /api/v1/datasets/p/qc"] = [pending];
    sequences["POST /api/v1/datasets/p/qc"] = [{ __status: 500, body: { detail: "boom" } }];
    const user = await openPeriod();
    await user.click(await screen.findByRole("button", { name: "Revisar calidad de las mallas" }));
    expect(await screen.findByText(/No se pudo iniciar la revisión/)).toBeInTheDocument();
  });

  it("describes problems with counts in plain Spanish", () => {
    expect(describeProblem("open_edges", { open_edges: 12 })).toBe("Tiene 12 bordes abiertos (huecos en la superficie).");
    expect(describeProblem("non_manifold_edges", { non_manifold_edges: 3 })).toMatch(/3 aristas/);
    expect(describeProblem("multiple_components", { components: { value: 4 } })).toBe("Está formado por 4 partes separadas.");
    expect(describeProblem("self_intersections", { self_intersections: { value: 1 } })).toBe("1 cara se cruza con otra (autointersección).");
    expect(describeProblem("something_new", {})).toBe("something_new");
  });
});
