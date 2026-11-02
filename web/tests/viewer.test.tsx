import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ instances: [] as any[], failInit: false }));

vi.mock("../src/viewer/ThreeScene", () => {
  class WebGLUnavailableError extends Error {}
  class ThreeScene {
    setLayer = vi.fn(async () => {});
    setVisible = vi.fn();
    setOpacity = vi.fn();
    resetView = vi.fn();
    dispose = vi.fn();
    constructor() {
      if (mocks.failInit) throw new WebGLUnavailableError("no webgl");
      mocks.instances.push(this);
    }
  }
  return { ThreeScene, WebGLUnavailableError };
});

import App from "../src/App";

const ds = (id: string, label: string) => ({
  id, name: "Modelo", period_label: label, period_kind: "annual", revision: 1, is_demo: false,
  spatial_reference: null, units: null, state: "closed", created_at: "x", file_count: 3,
});
const entry = (filename: string, key: string) => ({ filename, key, sha256: "0".repeat(64), size_bytes: 1 });
const layer = (role: string, filename: string, over: object = {}) => ({
  role, filename, status: "ok", url: `/api/v1/scene/assets/${role}-${filename}.glb`, vertices: 8, triangles: 12, ...over,
});
const manifest = (key: string, layers: object[]) => ({ key, origin: { east: 1, north: 2, elevation: 3 }, axes: "y_up", layers });

let scenes: Record<string, () => unknown> = {};
let regionsReply: { status?: number; body: unknown } | null = null;
const regionsRequested: string[] = [];
const scenePromises: Record<string, Promise<unknown>> = {};
const requested: string[] = [];

beforeEach(() => {
  mocks.instances.length = 0;
  mocks.failInit = false;
  scenes = {};
  regionsReply = null;
  regionsRequested.length = 0;
  requested.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
      if (url === "/api/v1/datasets") return json([ds("p", "2025"), ds("c", "2026")]);
      if (url === "/api/v1/datasets/p" || url === "/api/v1/datasets/c")
        return json({ ...ds(url.endsWith("p") ? "p" : "c", "x"), files: [entry("a.obj", "a")], incidents: [], counts: { files: 1, keys: 1 } });
      if (url === "/api/v1/matches?previous=p&current=c")
        return json({
          pairs: [{ key: "a_3", previous: entry("a_3pt.obj", "a_3"), current: entry("a_3.obj", "a_3") }],
          only_previous: [entry("old.obj", "old")], only_current: [entry("new.obj", "new")], incidents: [],
        });
      if (url.startsWith("/api/v1/scene/regions?")) {
        regionsRequested.push(url);
        const reply = regionsReply ?? { body: {} };
        const status = reply.status ?? 200;
        return { ok: status < 400, status, json: async () => (status < 400 ? reply.body : { detail: reply.body }) } as Response;
      }
      if (url.startsWith("/api/v1/scene?")) {
        requested.push(url);
        const key = new URL(url, "http://x").searchParams.get("key")!;
        const out = await (scenePromises[key] ?? Promise.resolve(scenes[key]?.()));
        if (!out) throw new Error(`unmocked ${url}`);
        return json(out);
      }
      throw new Error(`unmocked ${url}`);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

async function openResults() {
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "p");
  await user.selectOptions((await screen.findAllByLabelText("Usar un periodo ya guardado"))[0], "c");
  await screen.findByRole("table");
  return user;
}
const view = (user: ReturnType<typeof userEvent.setup>, name: string) =>
  user.click(screen.getByRole("button", { name: `Ver en 3D: ${name}` }));

describe("3D viewer", () => {
  it("opens the pair, loads both layers and explains the colors in words", async () => {
    scenes["a_3"] = () => manifest("a_3", [layer("previous", "a_3pt.obj"), layer("current", "a_3.obj")]);
    const user = await openResults();
    await view(user, "a_3");
    expect(await screen.findByRole("heading", { name: /Vista 3D · a_3/ })).toBeInTheDocument();
    expect(requested).toEqual(["/api/v1/scene?previous=p&current=c&key=a_3"]);
    await waitFor(() => expect(mocks.instances[0].setLayer).toHaveBeenCalledTimes(2));
    expect(mocks.instances[0].setLayer).toHaveBeenCalledWith("previous", "/api/v1/scene/assets/previous-a_3pt.obj.glb");
    expect(screen.getByLabelText(/Periodo anterior \(naranja\)/)).toBeChecked();
    expect(screen.getByLabelText(/Periodo actual \(gris\)/)).toBeChecked();
    expect(screen.getByText(/Ejes/)).toBeInTheDocument();
  });

  it("controls visibility, opacity and view reset per layer", async () => {
    scenes["a_3"] = () => manifest("a_3", [layer("previous", "a_3pt.obj"), layer("current", "a_3.obj")]);
    const user = await openResults();
    await view(user, "a_3");
    await user.click(await screen.findByLabelText(/Periodo anterior \(naranja\)/));
    expect(mocks.instances[0].setVisible).toHaveBeenCalledWith("previous", false);
    const slider = screen.getByLabelText("Opacidad del periodo actual");
    fireEvent.change(slider, { target: { value: "0.3" } });
    expect(mocks.instances[0].setOpacity).toHaveBeenCalledWith("current", 0.3);
    await user.click(screen.getByRole("button", { name: "Restablecer vista" }));
    expect(mocks.instances[0].resetView).toHaveBeenCalled();
  });

  it("shows only the existing mesh for a solid present in one period", async () => {
    scenes["old"] = () => manifest("old", [layer("previous", "old.obj")]);
    const user = await openResults();
    await view(user, "old");
    expect(await screen.findByText(/solo existe en el periodo anterior/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Periodo actual \(gris\)/)).not.toBeInTheDocument();
  });

  it("keeps the healthy layer when the other one cannot be prepared", async () => {
    scenes["a_3"] = () => manifest("a_3", [layer("previous", "a_3pt.obj", { status: "failed", url: undefined, reason: "bad" }), layer("current", "a_3.obj")]);
    const user = await openResults();
    await view(user, "a_3");
    expect(await screen.findByText(/No se pudo preparar el periodo anterior/)).toBeInTheDocument();
    await waitFor(() => expect(mocks.instances[0].setLayer).toHaveBeenCalledTimes(1));
    expect(mocks.instances[0].setLayer).toHaveBeenCalledWith("current", expect.any(String));
  });

  it("ignores a late answer for a solid that is no longer selected", async () => {
    let release!: (v: unknown) => void;
    scenePromises["a_3"] = new Promise((resolve) => (release = resolve));
    scenes["old"] = () => manifest("old", [layer("previous", "old.obj")]);
    const user = await openResults();
    await view(user, "a_3");
    await view(user, "old");
    expect(await screen.findByRole("heading", { name: /Vista 3D · old/ })).toBeInTheDocument();
    release(manifest("a_3", [layer("previous", "a_3pt.obj"), layer("current", "a_3.obj")]));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByRole("heading", { name: /Vista 3D · old/ })).toBeInTheDocument();
    const urls = mocks.instances.flatMap((i) => i.setLayer.mock.calls.map((c: unknown[]) => c[1]));
    expect(urls.some((u: string) => u.includes("a_3"))).toBe(false);
  });

  it("releases the previous scene when another solid is opened and when closing", async () => {
    scenes["a_3"] = () => manifest("a_3", [layer("previous", "a_3pt.obj"), layer("current", "a_3.obj")]);
    scenes["old"] = () => manifest("old", [layer("previous", "old.obj")]);
    const user = await openResults();
    await view(user, "a_3");
    await screen.findByRole("heading", { name: /Vista 3D · a_3/ });
    await waitFor(() => expect(mocks.instances).toHaveLength(1));
    await view(user, "old");
    await waitFor(() => expect(mocks.instances[0].dispose).toHaveBeenCalled());
    await screen.findByRole("heading", { name: /Vista 3D · old/ });
    await user.click(screen.getByRole("button", { name: "Cerrar vista 3D" }));
    await waitFor(() => expect(mocks.instances.at(-1).dispose).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: /Vista 3D/ })).not.toBeInTheDocument();
  });

  it("explains when the browser cannot start WebGL", async () => {
    mocks.failInit = true;
    scenes["a_3"] = () => manifest("a_3", [layer("previous", "a_3pt.obj"), layer("current", "a_3.obj")]);
    const user = await openResults();
    await view(user, "a_3");
    expect(await screen.findByText(/no pudo iniciar la vista 3D/i)).toBeInTheDocument();
  });

  it("offers the difference zones for a solid that exists in both periods", async () => {
    scenes["a_3"] = () => manifest("a_3", [layer("previous", "a_3pt.obj"), layer("current", "a_3.obj")]);
    const user = await openResults();
    await view(user, "a_3");
    expect(await screen.findByRole("button", { name: "Ver zonas común, agregada y removida" })).toBeEnabled();
  });
});


const zones = (over: object = {}) => ({
  status: "ok", error: null, provisional: true, warnings: ["inverted_orientation_normalized:previous"], origin: { east: 1, north: 2, elevation: 3 },
  regions: {
    common: { status: "ok", volume_m3: 500, triangles: 12, url: "/api/v1/scene/assets/z_common.glb" },
    added: { status: "ok", volume_m3: 500, triangles: 12, url: "/api/v1/scene/assets/z_added.glb" },
    removed: { status: "ok", volume_m3: 500, triangles: 12, url: "/api/v1/scene/assets/z_removed.glb" },
    ...over,
  },
});
const bothLayers = () => manifest("a_3", [layer("previous", "a_3pt.obj"), layer("current", "a_3.obj")]);

describe("difference zones", () => {
  it("loads the common, added and removed zones on request and hides the two periods to show them", async () => {
    scenes["a_3"] = bothLayers;
    regionsReply = { body: zones() };
    const user = await openResults();
    await view(user, "a_3");
    await user.click(await screen.findByRole("button", { name: "Ver zonas común, agregada y removida" }));
    await waitFor(() => expect(mocks.instances[0].setLayer).toHaveBeenCalledWith("common", "/api/v1/scene/assets/z_common.glb"));
    expect(regionsRequested).toEqual(["/api/v1/scene/regions?previous=p&current=c&key=a_3"]);
    expect(mocks.instances[0].setLayer).toHaveBeenCalledWith("added", "/api/v1/scene/assets/z_added.glb");
    expect(mocks.instances[0].setLayer).toHaveBeenCalledWith("removed", "/api/v1/scene/assets/z_removed.glb");
    expect(mocks.instances[0].setVisible).toHaveBeenCalledWith("previous", false);
    expect(mocks.instances[0].setVisible).toHaveBeenCalledWith("current", false);
    expect(await screen.findByLabelText(/Zona común \(verde\)/)).toBeChecked();
    expect(screen.getByLabelText(/Zona agregada \(azul\)/)).toBeChecked();
    expect(screen.getByLabelText(/Zona removida \(violeta\)/)).toBeChecked();
    expect(screen.getAllByText(/500 m³/).length).toBeGreaterThanOrEqual(3);
    expect(within(screen.getByRole("region", { name: /Vista 3D · a_3/ })).getByText(/Provisional:/)).toBeInTheDocument();
  });

  it("lets the user toggle each zone", async () => {
    scenes["a_3"] = bothLayers;
    regionsReply = { body: zones() };
    const user = await openResults();
    await view(user, "a_3");
    await user.click(await screen.findByRole("button", { name: "Ver zonas común, agregada y removida" }));
    await user.click(await screen.findByLabelText(/Zona agregada \(azul\)/));
    expect(mocks.instances[0].setVisible).toHaveBeenCalledWith("added", false);
  });

  it("says so when a zone is empty and why when it is unavailable, without drawing anything for them", async () => {
    scenes["a_3"] = bothLayers;
    regionsReply = { body: zones({ added: { status: "empty", volume_m3: 0 }, removed: { status: "unavailable", reason: "not_watertight:previous" } }) };
    const user = await openResults();
    await view(user, "a_3");
    await user.click(await screen.findByRole("button", { name: "Ver zonas común, agregada y removida" }));
    expect(await screen.findByText(/No hay zona agregada: los dos periodos coinciden ahí/)).toBeInTheDocument();
    expect(screen.getByText(/Zona removida: no disponible \(superficie no cerrada \(periodo anterior\)\)/)).toBeInTheDocument();
    const urls = mocks.instances[0].setLayer.mock.calls.map((c: unknown[]) => c[0]);
    expect(urls).not.toContain("added");
    expect(urls).not.toContain("removed");
  });

  it("is not offered for a solid that exists in one period only", async () => {
    scenes["old"] = () => manifest("old", [layer("previous", "old.obj")]);
    const user = await openResults();
    await view(user, "old");
    await screen.findByText(/solo existe en el periodo anterior/i);
    expect(screen.queryByRole("button", { name: "Ver zonas común, agregada y removida" })).not.toBeInTheDocument();
  });

  it("explains a failed calculation and a busy server", async () => {
    scenes["a_3"] = bothLayers;
    regionsReply = { body: { status: "failed", error: "process ended unexpectedly", regions: null, warnings: [] } };
    const user = await openResults();
    await view(user, "a_3");
    await user.click(await screen.findByRole("button", { name: "Ver zonas común, agregada y removida" }));
    expect(await screen.findByText(/No se pudieron calcular las zonas/)).toBeInTheDocument();
    regionsReply = { status: 409, body: "a heavy calculation is running" };
    await user.click(screen.getByRole("button", { name: "Ver zonas común, agregada y removida" }));
    expect(await screen.findByText(/Hay otro cálculo en curso/)).toBeInTheDocument();
  });

  it("ignores a late answer for a solid that is no longer open", async () => {
    scenes["a_3"] = bothLayers;
    scenes["old"] = () => manifest("old", [layer("previous", "old.obj")]);
    let release!: (v: unknown) => void;
    const original = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/scene/regions?") && url.includes("key=a_3"))
        return new Promise((resolve) => (release = () => resolve({ ok: true, status: 200, json: async () => zones() } as Response)));
      return original(url, init);
    }));
    const user = await openResults();
    await view(user, "a_3");
    await user.click(await screen.findByRole("button", { name: "Ver zonas común, agregada y removida" }));
    await view(user, "old");
    await screen.findByRole("heading", { name: /Vista 3D · old/ });
    release(undefined);
    await new Promise((r) => setTimeout(r, 20));
    const loaded = mocks.instances.flatMap((i) => i.setLayer.mock.calls.map((c: unknown[]) => c[1]));
    expect(loaded.some((u: string) => u.includes("z_common"))).toBe(false);
  });
});
