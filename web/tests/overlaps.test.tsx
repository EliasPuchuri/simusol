import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { POLL_MS } from "../src/config";

let sequences: Record<string, unknown[]> = {};

beforeEach(() => {
  POLL_MS.qc = 10;
  sequences = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const queue = sequences[`${init?.method ?? "GET"} ${url}`];
      if (!queue) {
        if (/\/(qc|characterization)$/.test(url)) return { ok: true, status: 200, json: async () => ({ run: null, summary: { ok: 0, failed: 0, pending: 0, with_issues: 0 }, results: [] }) } as Response;
        throw new Error(`unmocked ${init?.method ?? "GET"} ${url}`);
      }
      const next = queue.length > 1 ? queue.shift() : queue[0];
      return { ok: true, status: 200, json: async () => next } as Response;
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const ds = { id: "p", name: "Modelo", period_label: "2025", period_kind: "annual", revision: 1, is_demo: false, spatial_reference: null, units: null, state: "closed", created_at: "x", file_count: 3 };
const entry = (filename: string) => ({ filename, key: filename.replace(".obj", ""), sha256: "0".repeat(64), size_bytes: 1024 });
const detail = { ...ds, files: [entry("a.obj"), entry("b.obj"), entry("c.obj")], incidents: [], counts: { files: 3, keys: 3 }, orientation_reference_count: 0 };
const run = (state: string, done: number) => ({ id: "o1", dataset_id: "p", state, total: 3, done, error: null });
const summary = (o: object = {}) => ({ solids: 3, pairs: 3, discarded: 2, overlapping: 0, contact: 0, disjoint: 0, not_evaluable: 0, failed: 0, pending: 0, unreadable: [], ...o });
const pair = (over: object = {}) => ({ a: "a.obj", b: "b.obj", key_a: "a", key_b: "b", status: "ok", relation: "overlap", common_m3: 0.678, common_pct_of_smaller: 0.000967, reason: null, warnings: [], ...over });
const idle = { run: null, evaluated: false, summary: summary({ pending: 0, discarded: 0, pairs: 0 }), pairs: [] };

async function open() {
  sequences["GET /api/v1/datasets"] = [[ds]];
  sequences["GET /api/v1/datasets/p"] = [detail];
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "p");
  await screen.findByText("Listo");
  return user;
}
const panel = () => screen.getByRole("region", { name: "Superposición entre sólidos" });

describe("overlap panel", () => {
  it("explains what it does and offers the search before it ran", async () => {
    sequences["GET /api/v1/datasets/p/overlaps"] = [idle];
    await open();
    expect(await screen.findByRole("button", { name: "Buscar superposiciones" })).toBeEnabled();
    expect(within(panel()).getByText(/cuenta ese espacio dos veces/)).toBeInTheDocument();
  });

  it("shows progress while it runs and then the pairs that share volume with both solids named", async () => {
    sequences["GET /api/v1/datasets/p/overlaps"] = [idle, { ...idle, run: run("running", 1) }, { ...idle, run: run("running", 2) },
      { run: run("completed", 3), evaluated: true, summary: summary({ overlapping: 1, contact: 1 }), pairs: [pair(), pair({ a: "b.obj", b: "c.obj", key_a: "b", key_b: "c", relation: "contact", common_m3: 0, common_pct_of_smaller: 0 })] }];
    sequences["POST /api/v1/datasets/p/overlaps"] = [run("queued", 0)];
    const user = await open();
    await user.click(await screen.findByRole("button", { name: "Buscar superposiciones" }));
    expect(await screen.findByText(/Buscando: \d de 3 pares/)).toBeInTheDocument();
    expect(await within(panel()).findByText("1 par de sólidos comparte volumen.")).toBeInTheDocument();
    const list = within(panel()).getByRole("list", { name: "Pares con superposición" });
    expect(list).toHaveTextContent("a y b comparten 0.68 m³ (< 0.01 % del menor)");
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);              // the contact is counted, not listed as an overlap
    expect(within(panel()).getByText(/1 par solo se toca en una superficie/)).toBeInTheDocument();
  });

  it("says so plainly when nothing overlaps", async () => {
    sequences["GET /api/v1/datasets/p/overlaps"] = [{ run: run("completed", 3), evaluated: true, summary: summary(), pairs: [] }];
    await open();
    expect(await within(await screen.findByRole("region", { name: "Superposición entre sólidos" })).findByText(/Ningún sólido se superpone con otro \(3 pares revisados\)/)).toBeInTheDocument();
    expect(within(panel()).queryByRole("list", { name: "Pares con superposición" })).not.toBeInTheDocument();
  });

  it("lists what could not be evaluated instead of counting it as no overlap", async () => {
    sequences["GET /api/v1/datasets/p/overlaps"] = [{ run: run("completed_with_issues", 3), evaluated: true, summary: summary({ not_evaluable: 1, unreadable: ["x.obj"] }),
      pairs: [pair({ relation: "not_evaluable", common_m3: null, common_pct_of_smaller: null, reason: "not_watertight:a" })] }];
    await open();
    const p = await screen.findByRole("region", { name: "Superposición entre sólidos" });
    expect(await within(p).findByText(/No se pudo evaluar 2 pares o sólidos/)).toBeInTheDocument();
    expect(within(p).getByText(/Sin leer: x\.obj/)).toBeInTheDocument();
    expect(within(p).getByText(/no se pudo evaluar \(superficie no cerrada\)/)).toBeInTheDocument();
  });

  it("offers a retry after an interruption", async () => {
    sequences["GET /api/v1/datasets/p/overlaps"] = [{ ...idle, run: { ...run("failed", 1), error: "interrupted by a restart" } }];
    await open();
    expect(await screen.findByText(/La búsqueda se interrumpió/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar la búsqueda" })).toBeEnabled();
  });
});
