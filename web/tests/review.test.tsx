import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { POLL_MS } from "../src/config";

let sequences: Record<string, unknown[]> = {};
const calls: { key: string; body: any }[] = [];

beforeEach(() => {
  localStorage.clear();
  POLL_MS.qc = POLL_MS.characterization = POLL_MS.comparison = 10;
  sequences = {};
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.split("?")[0]}${url.includes("?") ? "?" : ""}`;
      const full = `${init?.method ?? "GET"} ${url}`;
      calls.push({ key: full, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      const queue = sequences[full] ?? sequences[key];
      if (!queue) {
        if (/\/(qc|characterization)$/.test(url)) return { ok: true, status: 200, json: async () => ({ run: null, summary: { ok: 0, failed: 0, pending: 0, with_issues: 0 }, results: [] }) } as Response;
        throw new Error(`unmocked ${full}`);
      }
      const next = (queue.length > 1 ? queue.shift() : queue[0]) as any;
      const status = next && typeof next === "object" && "__status" in next ? next.__status : 200;
      return { ok: status < 400, status, json: async () => (status < 400 ? next : next.body) } as Response;
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const ds = (id: string, label: string) => ({ id, name: "Modelo", period_label: label, period_kind: "annual", revision: 1, is_demo: false, spatial_reference: null, units: null, state: "closed", created_at: "x", file_count: 4, archived: false });
const entry = (filename: string, key: string) => ({ filename, key, sha256: "0".repeat(64), size_bytes: 1 });
const detail = (id: string, label: string) => ({ ...ds(id, label), files: [entry("a.obj", "a")], incidents: [], counts: { files: 1, keys: 1 }, orientation_reference_count: 0 });
const matches = { pairs: [{ key: "b_3", previous: entry("b_3pt.obj", "b_3"), current: entry("b_3.obj", "b_3") }], only_previous: [], only_current: [], incidents: [] };
const row = { key: "b_3", previous_filename: "b_3pt.obj", current_filename: "b_3.obj", status: "ok", technical_status: "ok", state: "VARIABLE", subtype: "VARIABLE", description: "RECORTE: se eliminó parte del sólido.", events: ["RECORTE"], checks: [], incidents: [], warnings: [], reasons: {}, metrics: { iou_pct: 92, delta_volume_pct: -6.9, p95_m: 1, centroid_m: 0.5 }, provisional: true, profile: "pilot-v1-provisional" };
const comparison = { run: { id: "r", previous_id: "p", current_id: "c", state: "completed", total: 1, done: 1, error: null }, provisional: true, profile: "pilot-v1-provisional", summary: { "SIN CAMBIOS": 0, VARIABLE: 1, NUEVO: 0, ELIMINADO: 0, sin_clasificar: 0, pendientes: 0 }, rows: [row] };

async function ready(reviews: object[] = []) {
  sequences["GET /api/v1/datasets"] = [[ds("p", "2025"), ds("c", "2026")]];
  sequences["GET /api/v1/datasets/p"] = [detail("p", "2025")];
  sequences["GET /api/v1/datasets/c"] = [detail("c", "2026")];
  sequences["GET /api/v1/matches?previous=p&current=c"] = [matches];
  sequences["GET /api/v1/comparisons?previous=p&current=c"] = [comparison];
  sequences["GET /api/v1/comparisons/reviews?"] = [{ reviews }];
  sequences["PUT /api/v1/comparisons/reviews"] = [{ saved: true }];
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "p");
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "c");
  await screen.findByRole("table", { name: "Clasificación por sólido" });
  return user;
}
const panel = () => screen.getByRole("region", { name: "Clasificación de cambios" });
const puts = () => calls.filter((c) => c.key.startsWith("PUT"));

describe("area reviews", () => {
  it("lets the reviewer disagree, say what was expected and send it", async () => {
    localStorage.setItem("simusol.reviewer", "Ingeniera");
    const user = await ready();
    await user.click(within(panel()).getByRole("button", { name: "Opinar: b_3" }));
    const form = screen.getByRole("form", { name: "Tu opinión sobre b_3" });
    expect(within(form).getByText(/Variable/)).toBeInTheDocument();
    await user.click(within(form).getByLabelText("No estoy de acuerdo"));
    await user.selectOptions(within(form).getByLabelText("Estado que esperabas"), "SIN CAMBIOS");
    await user.selectOptions(within(form).getByLabelText("Tipo de cuerpo que esperabas"), "TABULAR CURVO");
    await user.type(within(form).getByLabelText("Azimuth esperado"), "120,5");
    await user.type(within(form).getByLabelText("Dip esperado"), "30");
    await user.type(within(form).getByLabelText("Comentario"), "Es el mismo cuerpo");
    await user.click(within(form).getByRole("button", { name: "Guardar opinión" }));
    expect(await screen.findByText("Opinión guardada")).toBeInTheDocument();
    expect(puts()[0].body).toEqual({
      previous: "p", current: "c", key: "b_3", reviewer: "Ingeniera", agrees: false, expected_state: "SIN CAMBIOS",
      expected_body_type: "TABULAR CURVO", expected_azimuth: 120.5, expected_dip: 30, comment: "Es el mismo cuerpo",
    });
  });

  it("sends an agreement with one click", async () => {
    localStorage.setItem("simusol.reviewer", "Ingeniera");
    const user = await ready();
    await user.click(within(panel()).getByRole("button", { name: "Opinar: b_3" }));
    const form = screen.getByRole("form", { name: "Tu opinión sobre b_3" });
    await user.click(within(form).getByRole("button", { name: "Guardar opinión" }));
    expect(await screen.findByText("Opinión guardada")).toBeInTheDocument();
    expect(puts()[0].body).toMatchObject({ key: "b_3", agrees: true, expected_state: null });
  });

  it("asks for the reviewer's name once and remembers it", async () => {
    const user = await ready();
    await user.click(within(panel()).getByRole("button", { name: "Opinar: b_3" }));
    const form = screen.getByRole("form", { name: "Tu opinión sobre b_3" });
    const save = within(form).getByRole("button", { name: "Guardar opinión" });
    expect(save).toBeDisabled();
    await user.type(within(form).getByLabelText("Tu nombre"), "María");
    expect(save).toBeEnabled();
    await user.click(save);
    await screen.findByText("Opinión guardada");
    expect(localStorage.getItem("simusol.reviewer")).toBe("María");
  });

  it("does not let a disagreement be sent without saying what was expected", async () => {
    localStorage.setItem("simusol.reviewer", "Ingeniera");
    const user = await ready();
    await user.click(within(panel()).getByRole("button", { name: "Opinar: b_3" }));
    const form = screen.getByRole("form", { name: "Tu opinión sobre b_3" });
    await user.click(within(form).getByLabelText("No estoy de acuerdo"));
    const save = within(form).getByRole("button", { name: "Guardar opinión" });
    expect(save).toBeDisabled();
    await user.type(within(form).getByLabelText("Comentario"), "No me cuadra");
    expect(save).toBeEnabled();
  });

  it("shows which solids already have an opinion", async () => {
    localStorage.setItem("simusol.reviewer", "Ingeniera");
    await ready([{ key: "b_3", reviewer: "Ingeniera", agrees: false, comment: "x", expected_state: "SIN CAMBIOS" }]);
    expect(await within(panel()).findByText("Tu opinión: con observaciones")).toBeInTheDocument();
  });

  it("lets the reviewer write a general observation and download all opinions", async () => {
    localStorage.setItem("simusol.reviewer", "Ingeniera");
    const user = await ready();
    await user.click(within(panel()).getByRole("button", { name: "Escribir una observación general" }));
    const form = screen.getByRole("form", { name: "Observación general" });
    await user.type(within(form).getByLabelText("Comentario"), "Los umbrales de curvatura parecen bajos");
    await user.click(within(form).getByRole("button", { name: "Guardar opinión" }));
    await screen.findByText("Opinión guardada");
    expect(puts()[0].body).toMatchObject({ key: "*", agrees: true, comment: "Los umbrales de curvatura parecen bajos" });
    expect(within(panel()).getByRole("link", { name: /Descargar mis opiniones/ })).toHaveAttribute("href", "/api/v1/comparisons/reviews.csv?previous=p&current=c");
  });

  it("reports a failure to save without losing what was typed", async () => {
    localStorage.setItem("simusol.reviewer", "Ingeniera");
    const user = await ready();
    sequences["PUT /api/v1/comparisons/reviews"] = [{ __status: 500, body: { detail: "boom" } }];
    await user.click(within(panel()).getByRole("button", { name: "Opinar: b_3" }));
    const form = screen.getByRole("form", { name: "Tu opinión sobre b_3" });
    await user.click(within(form).getByLabelText("No estoy de acuerdo"));
    await user.type(within(form).getByLabelText("Comentario"), "texto importante");
    await user.click(within(form).getByRole("button", { name: "Guardar opinión" }));
    expect(await screen.findByText(/No se pudo guardar la opinión/)).toBeInTheDocument();
    expect(within(form).getByLabelText("Comentario")).toHaveValue("texto importante");
  });
});

describe("removing a period from the list", () => {
  async function loaded() {
    sequences["GET /api/v1/datasets"] = [[ds("p", "2025")]];
    sequences["GET /api/v1/datasets/p"] = [detail("p", "2025")];
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "p");
    await screen.findByText("Listo");
    return user;
  }

  it("asks for confirmation, explains nothing is deleted, and archives the period", async () => {
    sequences["POST /api/v1/datasets/p/archive"] = [{ ...ds("p", "2025"), archived: true }];
    const user = await loaded();
    await user.click(screen.getByRole("button", { name: "Quitar este periodo de la lista" }));
    expect(screen.getByText(/Los archivos se conservan en el servidor/)).toBeInTheDocument();
    expect(calls.some((c) => c.key.startsWith("POST") && c.key.includes("archive"))).toBe(false);
    sequences["GET /api/v1/datasets"] = [[]];
    await user.click(screen.getByRole("button", { name: "Sí, quitar" }));
    await waitFor(() => expect(calls.some((c) => c.key === "POST /api/v1/datasets/p/archive")).toBe(true));
    expect(await screen.findAllByText(/Arrastra aquí la carpeta/)).toHaveLength(2);
    expect(screen.queryByLabelText("Usar un periodo ya guardado")).not.toBeInTheDocument();
  });

  it("can be cancelled without touching anything", async () => {
    const user = await loaded();
    await user.click(screen.getByRole("button", { name: "Quitar este periodo de la lista" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.getByRole("button", { name: "Quitar este periodo de la lista" })).toBeInTheDocument();
    expect(calls.some((c) => c.key.includes("archive"))).toBe(false);
  });
});
