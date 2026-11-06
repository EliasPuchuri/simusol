import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import { describeIssue, folderLabel, formatBytes, friendlyError, plural } from "../src/format";

type Reply = unknown | { status: number; body: unknown };
const calls: { url: string; method: string; body?: any }[] = [];
let routes: Record<string, (init?: RequestInit) => Reply> = {};

beforeEach(() => {
  calls.length = 0;
  routes = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
      calls.push({ url, method, body });
      const handler = routes[`${method} ${url}`];
      if (!handler) throw new Error(`unmocked ${method} ${url}`);
      const out = handler(init) as any;
      const wrapped = out && typeof out === "object" && "status" in out && "body" in out;
      const status = wrapped ? out.status : 200;
      return { ok: status < 400, status, json: async () => (wrapped ? out.body : out) } as Response;
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const ds = (over: object = {}) => ({
  id: "d1", name: "Modelo", period_label: "2025", period_kind: "annual", revision: 1,
  is_demo: false, spatial_reference: null, units: null, state: "open", created_at: "2026-11-01T00:00:00+00:00",
  file_count: 0, ...over,
});
const file = (name: string, folder?: string) => {
  const f = new File(["v 0 0 0\nf 1 1 1\n"], name);
  if (folder) Object.defineProperty(f, "webkitRelativePath", { value: `${folder}/${name}` });
  return f;
};
const entry = (filename: string, key: string) => ({ filename, key, sha256: "0".repeat(64), size_bytes: 2048 });
const detail = (over: object = {}) => ({ ...ds(), files: [], incidents: [], counts: { files: 0, keys: 0 }, ...over });

describe("helpers", () => {
  it("formats sizes and plurals in plain language", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(plural(1, "sólido", "sólidos")).toBe("1 sólido");
    expect(plural(28, "sólido", "sólidos")).toBe("28 sólidos");
  });
  it("derives the period name from the picked folder", () => {
    expect(folderLabel([file("a.obj", "2025-Prueba")])).toBe("2025-Prueba");
    expect(folderLabel([file("a.obj")])).toBe("");
  });
  it("translates server errors", () => {
    expect(friendlyError("content is not a valid OBJ (needs vertices and faces)")).toMatch(/geometría/);
    expect(friendlyError("only .obj files are accepted")).toMatch(/\.obj/);
    expect(friendlyError("file 'a.obj' already exists in this dataset")).toMatch(/Ya se había cargado/);
    expect(friendlyError("algo raro")).toBe("algo raro");
  });
});

describe("first visit", () => {
  it("explains what to do without any manual", async () => {
    routes["GET /api/v1/datasets"] = () => [];
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Compara dos periodos de sólidos" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Periodo anterior" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Periodo actual" })).toBeInTheDocument();
    expect(screen.getAllByText(/Arrastra aquí la carpeta/)).toHaveLength(2);
    expect(screen.getByText(/Carga los dos periodos para ver la comparación/)).toBeInTheDocument();
  });
});

describe("loading a period", () => {
  async function loadFolder(files: File[], over: object = {}, listed: string[] = files.map((f) => f.name).filter((n) => n.endsWith(".obj"))) {
    routes["GET /api/v1/datasets"] = () => [];
    routes["POST /api/v1/datasets"] = () => ({ status: 201, body: ds() });
    routes["GET /api/v1/datasets/d1"] = () =>
      detail({ files: listed.map((n) => entry(n, n.replace(/\.obj$/, ""))), counts: { files: listed.length, keys: listed.length }, ...over });
    const user = userEvent.setup();
    render(<App />);
    await user.upload(await screen.findByLabelText("Carpeta del periodo anterior"), files);
    return user;
  }

  it("creates the period from the folder name and uploads every file", async () => {
    routes["POST /api/v1/datasets/d1/files"] = () => ({ status: 201, body: {} });
    await loadFolder([file("a_3pt.obj", "2025-Prueba"), file("b_3pt.obj", "2025-Prueba")]);
    expect(await screen.findByText("2 sólidos cargados")).toBeInTheDocument();
    const create = calls.find((c) => c.method === "POST" && c.url === "/api/v1/datasets")!;
    expect(create.body).toMatchObject({ period_label: "2025-Prueba", period_kind: "annual", name: "Modelo" });
    expect(calls.filter((c) => c.url.endsWith("/files"))).toHaveLength(2);
  });

  it("sends the declared spatial reference and units when the period is created", async () => {
    routes["POST /api/v1/datasets/d1/files"] = () => ({ status: 201, body: {} });
    const user = userEvent.setup();
    routes["GET /api/v1/datasets"] = () => [];
    routes["POST /api/v1/datasets"] = () => ds();
    routes["GET /api/v1/datasets/d1"] = () => detail({ files: [entry("a.obj", "a")], counts: { files: 1, keys: 1 } });
    render(<App />);
    await user.click(screen.getByText("Ajustes"));
    await user.type(screen.getByLabelText(/Referencia espacial de los periodos/), "UTM 18S WGS84");
    await user.type(screen.getByLabelText(/^Unidades/), "m");
    await user.upload(await screen.findByLabelText("Carpeta del periodo anterior"), [file("a.obj", "2025")]);
    await screen.findByText("1 sólido cargado");
    const create = calls.find((c) => c.method === "POST" && c.url === "/api/v1/datasets")!;
    expect(create.body).toMatchObject({ spatial_reference: "UTM 18S WGS84", units: "m" });
  });

  it("leaves them empty (null) when nothing was declared", async () => {
    routes["POST /api/v1/datasets/d1/files"] = () => ({ status: 201, body: {} });
    await loadFolder([file("a.obj", "2025")]);
    await screen.findByText("1 sólido cargado");
    const create = calls.find((c) => c.method === "POST" && c.url === "/api/v1/datasets")!;
    expect(create.body).toMatchObject({ spatial_reference: null, units: null });
  });

  it("ignores non-OBJ files and says so", async () => {
    routes["POST /api/v1/datasets/d1/files"] = () => ({ status: 201, body: {} });
    await loadFolder([file("a.obj", "P"), file("rev.rmproj", "P")]);
    expect(await screen.findByText("1 sólido cargado")).toBeInTheDocument();
    expect(calls.filter((c) => c.url.endsWith("/files"))).toHaveLength(1);
    expect(screen.getByText(/1 archivo que no es \.obj/)).toBeInTheDocument();
  });

  it("keeps going after a failure and lists what was not loaded in plain words", async () => {
    let n = 0;
    routes["POST /api/v1/datasets/d1/files"] = () =>
      ++n === 2 ? { status: 422, body: { detail: "content is not a valid OBJ (needs vertices and faces)" } } : { status: 201, body: {} };
    await loadFolder([file("a.obj", "P"), file("b.obj", "P"), file("c.obj", "P")], {}, ["a.obj", "c.obj"]);
    expect(await screen.findByText(/1 archivo no se pudo usar/)).toBeInTheDocument();
    expect(screen.getByText(/b\.obj/)).toBeInTheDocument();
    expect(screen.getByText(/no tiene geometría válida/)).toBeInTheDocument();
    expect(calls.filter((c) => c.url.endsWith("/files"))).toHaveLength(3);
  });

  it("warns in plain language when two files would be paired as the same solid", async () => {
    routes["POST /api/v1/datasets/d1/files"] = () => ({ status: 201, body: {} });
    await loadFolder([file("x_3pt.obj", "P"), file("x_3.obj", "P")], {
      incidents: [{ code: "duplicate_key", message: "", detail: { key: "x_3", filenames: ["x_3pt.obj", "x_3.obj"] } }],
    });
    expect(await screen.findByText(/x_3pt\.obj y x_3\.obj/)).toBeInTheDocument();
    expect(screen.getByText(/mismo sólido/)).toBeInTheDocument();
  });

  it("asks for confirmation wording and closes the period", async () => {
    routes["POST /api/v1/datasets/d1/files"] = () => ({ status: 201, body: {} });
    const user = await loadFolder([file("a.obj", "2025")]);
    routes["POST /api/v1/datasets/d1/finalize"] = () => ds({ state: "closed" });
    routes["GET /api/v1/datasets/d1"] = () => detail({ state: "closed", files: [entry("a.obj", "a")], counts: { files: 1, keys: 1 } });
    expect(await screen.findByText(/Después no se podrá modificar/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Está completo, continuar" }));
    expect(await screen.findByText("Listo")).toBeInTheDocument();
    expect(screen.getByText(/2025 · 1 sólido/)).toBeInTheDocument();
  });
});

describe("reusing saved periods", () => {
  it("lets the user pick a period that was already loaded", async () => {
    routes["GET /api/v1/datasets"] = () => [ds({ id: "s1", period_label: "Enero", state: "closed", file_count: 28 })];
    routes["GET /api/v1/datasets/s1"] = () => detail({ id: "s1", period_label: "Enero", state: "closed", files: [entry("a.obj", "a")], counts: { files: 1, keys: 1 } });
    const user = userEvent.setup();
    render(<App />);
    const select = (await screen.findAllByLabelText("Usar un periodo ya guardado"))[0];
    await user.selectOptions(select, "s1");
    expect(await screen.findByText("Listo")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});

describe("comparison", () => {
  const closed = (id: string, label: string) => ds({ id, period_label: label, state: "closed", file_count: 2 });
  async function ready() {
    routes["GET /api/v1/datasets"] = () => [closed("p", "2025"), closed("c", "2026")];
    for (const [id, label] of [["p", "2025"], ["c", "2026"]])
      routes[`GET /api/v1/datasets/${id}`] = () => detail({ id, period_label: label, state: "closed", files: [entry("a.obj", "a")], counts: { files: 1, keys: 1 } });
    routes["GET /api/v1/matches?previous=p&current=c"] = () => ({
      pairs: [{ key: "a_3", previous: entry("a_3pt.obj", "a_3"), current: entry("a_3.obj", "a_3") }],
      only_previous: [entry("old.obj", "old")],
      only_current: [entry("new.obj", "new"), entry("new2.obj", "new2")],
      incidents: [],
    });
    const user = userEvent.setup();
    render(<App />);
    const selects = await screen.findAllByLabelText("Usar un periodo ya guardado");
    await user.selectOptions(selects[0], "p");
    await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "c");
    return user;
  }

  it("compares automatically once both periods are ready and warns about renamed solids", async () => {
    await ready();
    expect(await screen.findByText(/renombrado/)).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar sólido")).toBeInTheDocument();
  });

  it("offers every solid of both periods in the list to inspect", async () => {
    await ready();
    const select = await screen.findByLabelText("Filtrar sólido");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Elige el sólido que vas a revisar…", "a_3", "new", "new2", "old"]);
  });
});

describe("orientation reference table", () => {
  async function openCard(over: object = {}) {
    routes["GET /api/v1/datasets"] = () => [ds({ id: "s1", period_label: "Enero", state: "closed", file_count: 1 })];
    routes["GET /api/v1/datasets/s1"] = () =>
      detail({ id: "s1", period_label: "Enero", state: "closed", files: [entry("a.obj", "a")], counts: { files: 1, keys: 1 }, orientation_reference_count: 0, ...over });
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "s1");
    await screen.findByText("Listo");
    await user.click(screen.getByText(/Valores de referencia de orientación/));
    return user;
  }
  const csv = () => new File(["archivo;..."], "tabla.csv", { type: "text/csv" });

  it("offers the template as a download and explains it in plain words", async () => {
    await openCard();
    const link = screen.getByRole("link", { name: /Descargar plantilla/ });
    expect(link).toHaveAttribute("href", "/api/v1/templates/orientation-reference");
    expect(link).toHaveAttribute("download");
    expect(screen.getByText(/Studio RM o Leapfrog/)).toBeInTheDocument();
  });

  it("uploads the filled table and confirms what was saved", async () => {
    routes["POST /api/v1/datasets/s1/orientation-reference"] = () => ({ saved: 2, ignored_examples: 3, warnings: [{ code: "not_in_dataset", line: 3, column: "archivo", value: "b.obj" }] });
    const user = await openCard();
    await user.upload(screen.getByLabelText("Tabla de orientación del periodo anterior"), csv());
    expect(await screen.findByText(/Se guardaron 2 filas de referencia/)).toBeInTheDocument();
    expect(screen.getByText(/Se ignoraron 3 filas de ejemplo/)).toBeInTheDocument();
    expect(screen.getByText(/Línea 3: «b\.obj» no está en los archivos de este periodo/)).toBeInTheDocument();
  });

  it("lists every problem with its line and saves nothing", async () => {
    routes["POST /api/v1/datasets/s1/orientation-reference"] = () => ({
      status: 422,
      body: { detail: { errors: [{ code: "azimuth_range", line: 4, column: "azimuth_grados", value: "400" }, { code: "bad_type", line: 5, column: "tipo_orientacion", value: "oblicuo" }], warnings: [], ignored_examples: 0 } },
    });
    const user = await openCard();
    await user.upload(screen.getByLabelText("Tabla de orientación del periodo anterior"), csv());
    expect(await screen.findByText(/No se guardó nada: corrige 2 problemas y vuelve a subir el archivo/)).toBeInTheDocument();
    expect(screen.getByText(/Línea 4: el azimuth 400 debe estar entre 0 y 360/)).toBeInTheDocument();
    expect(screen.getByText(/Línea 5: el tipo «oblicuo» no es válido/)).toBeInTheDocument();
  });

  it("shows when a table is already stored", async () => {
    await openCard({ orientation_reference_count: 12 });
    expect(screen.getByText(/Ya hay 12 filas de referencia guardadas/)).toBeInTheDocument();
  });

  it("describes issues in Spanish", () => {
    expect(describeIssue({ code: "missing_column", line: 6, column: "dip_grados" })).toBe("Falta la columna «dip_grados».");
    expect(describeIssue({ code: "no_rows" })).toMatch(/Rellena la plantilla/);
    expect(describeIssue({ code: "must_be_empty", line: 9, column: "dip_grados", value: "20" })).toMatch(/Línea 9.*vacío/);
  });
});
