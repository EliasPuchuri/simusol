import { useEffect, useRef, useState } from "react";

import { api, type RegionInfo, type SceneLayer, type SceneRegions } from "../api";
import { exclusionText } from "../dashboard";
import { plural } from "../format";
import { DEFAULT_OPACITY } from "../viewer/defaults";
import { ThreeScene, WebGLUnavailableError, type Role } from "../viewer/ThreeScene";

type Props = { previousId: string; currentId: string; solidKey: string; onClose: () => void };
type LayerUi = { layer: SceneLayer; visible: boolean; opacity: number };

const NAMES: Record<"previous" | "current", { text: string; color: string; short: string }> = {
  previous: { text: "Periodo anterior", color: "naranja", short: "periodo anterior" },
  current: { text: "Periodo actual", color: "gris", short: "periodo actual" },
};
type Zone = "common" | "added" | "removed";
const ZONES: Record<Zone, { text: string; color: string; none: string }> = {
  common: { text: "Zona común", color: "verde", none: "No hay zona común: los dos periodos no se superponen." },
  added: { text: "Zona agregada", color: "azul", none: "No hay zona agregada: los dos periodos coinciden ahí." },
  removed: { text: "Zona removida", color: "violeta", none: "No hay zona removida: los dos periodos coinciden ahí." },
};
type RegionsState = { phase: "idle" | "loading" | "ready" | "error"; data: SceneRegions | null; message: string | null; visible: Record<Zone, boolean> };
const IDLE: RegionsState = { phase: "idle", data: null, message: null, visible: { common: true, added: true, removed: true } };

export function Viewer3D({ previousId, currentId, solidKey, onClose }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const scene = useRef<ThreeScene | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerUi[]>([]);
  const [regions, setRegions] = useState<RegionsState>(IDLE);
  const regionsToken = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let created: ThreeScene | null = null;
    setStatus("loading");
    setMessage(null);
    setLayers([]);
    regionsToken.current += 1; // a zones request of the previous solid must not touch this one
    setRegions(IDLE);

    (async () => {
      let manifest;
      try {
        manifest = await api.scene(previousId, currentId, solidKey);
      } catch (e) {
        if (!cancelled) {
          setStatus("error");
          setMessage((e as Error).message);
        }
        return;
      }
      if (cancelled) return; // a newer selection replaced this one
      try {
        created = new ThreeScene(container.current!);
      } catch (e) {
        setStatus("error");
        setMessage(
          e instanceof WebGLUnavailableError
            ? "Tu navegador no pudo iniciar la vista 3D. Prueba con otro navegador o activa la aceleración por hardware."
            : "No se pudo iniciar la vista 3D.",
        );
        return;
      }
      scene.current = created;
      const ui: LayerUi[] = manifest.layers.map((layer) => ({ layer, visible: true, opacity: DEFAULT_OPACITY[layer.role] }));
      setLayers(ui);

      for (const item of ui) {
        if (item.layer.status !== "ok" || !item.layer.url) continue;
        try {
          await created.setLayer(item.layer.role, item.layer.url);
        } catch {
          item.layer = { ...item.layer, status: "failed" };
        }
        if (cancelled) return;
        setLayers([...ui]);
      }
      if (!cancelled) setStatus("ready");
    })();

    return () => {
      cancelled = true;
      created?.dispose();
      if (scene.current === created) scene.current = null;
    };
  }, [previousId, currentId, solidKey]);

  const update = (role: Role, patch: Partial<LayerUi>) =>
    setLayers((all) => all.map((l) => (l.layer.role === role ? { ...l, ...patch } : l)));

  const single = layers.length === 1 ? layers[0].layer.role : null;
  const hasBoth = layers.length === 2 && layers.every((l) => l.layer.status === "ok") && status === "ready";

  async function loadRegions() {
    const token = ++regionsToken.current;
    const live = scene.current;
    setRegions({ ...IDLE, phase: "loading" });
    try {
      const data = await api.sceneRegions(previousId, currentId, solidKey);
      if (token !== regionsToken.current || scene.current !== live || !live) return; // another solid was opened meanwhile
      if (data.status !== "ok" || !data.regions) {
        setRegions({ ...IDLE, phase: "error", message: "No se pudieron calcular las zonas de este sólido. Inténtalo de nuevo." });
        return;
      }
      const shown = { ...IDLE.visible };
      for (const zone of Object.keys(ZONES) as Zone[]) {
        const info = data.regions[zone];
        if (info.status !== "ok" || !info.url) continue;
        try {
          await live.setLayer(zone, info.url);
        } catch {
          data.regions[zone] = { status: "unavailable", reason: "boolean_failed" };
        }
      }
      if (token !== regionsToken.current) return;
      (["previous", "current"] as const).forEach((role) => live.setVisible(role, false)); // show the zones, not the shells around them
      setLayers((all) => all.map((l) => ({ ...l, visible: false })));
      setRegions({ phase: "ready", data, message: null, visible: shown });
    } catch (e) {
      if (token !== regionsToken.current) return;
      const busy = /heavy calculation/.test((e as Error).message);
      setRegions({ ...IDLE, phase: "error", message: busy ? "Hay otro cálculo en curso; vuelve a intentarlo en un momento." : "No se pudieron calcular las zonas de este sólido. Inténtalo de nuevo." });
    }
  }

  function toggleZone(zone: Zone, on: boolean) {
    setRegions((r) => ({ ...r, visible: { ...r.visible, [zone]: on } }));
    scene.current?.setVisible(zone, on);
  }

  return (
    <section className="card viewer" aria-labelledby="viewer-title">
      <div className="viewer-head">
        <h2 id="viewer-title">Vista 3D · {solidKey}</h2>
        <button type="button" onClick={onClose}>Cerrar vista 3D</button>
      </div>

      {message && <p role="alert" className="alert alert-error">{message}</p>}
      {status === "loading" && <p role="status">Preparando la vista 3D… La primera vez puede tardar unos segundos.</p>}

      <div className="viewer-body">
        <div ref={container} className="canvas" aria-label="Vista 3D de los sólidos" />
        <div className="viewer-side">
          {single && <p className="note">Este sólido solo existe en el {NAMES[single].short}.</p>}
          {layers.map(({ layer, visible, opacity }) => {
            const info = NAMES[layer.role];
            if (layer.status === "failed")
              return <p key={layer.role} role="alert" className="alert alert-warn">No se pudo preparar el {info.short} para la vista 3D.</p>;
            return (
              <div key={layer.role} className="layer">
                <label className="inline">
                  <input type="checkbox" checked={visible}
                    onChange={(e) => { update(layer.role, { visible: e.target.checked }); scene.current?.setVisible(layer.role, e.target.checked); }} />
                  <span className={`swatch swatch-${layer.role}`} aria-hidden="true" />
                  {info.text} ({info.color})
                </label>
                <small>{layer.filename}{layer.triangles ? ` · ${plural(layer.triangles, "triángulo", "triángulos")}` : ""}</small>
                <label className="slider">
                  <span>Opacidad</span>
                  <input type="range" min="0.1" max="1" step="0.05" value={opacity}
                    aria-label={`Opacidad del ${info.short}`}
                    onChange={(e) => { const v = Number(e.target.value); update(layer.role, { opacity: v }); scene.current?.setOpacity(layer.role, v); }} />
                </label>
              </div>
            );
          })}
          <button type="button" onClick={() => scene.current?.resetView()}>Restablecer vista</button>
          <p className="note">Donde ves naranja, el periodo anterior sobresale del actual; donde ves gris, el actual coincide o sobresale.</p>
          <p className="note">Arrastra para girar, usa la rueda para acercar y clic derecho (o Mayús + arrastrar) para mover.</p>
          <p className="note">Ejes: Este (rojo), Elevación (verde) y Norte (azul, hacia el fondo de la pantalla). Ambos periodos comparten el mismo origen, así que cualquier desplazamiento real se ve.</p>
          {hasBoth && (
            <div className="zones">
              <strong>Zonas de diferencia</strong>
              {regions.phase !== "ready" && (
                <button type="button" disabled={regions.phase === "loading"} onClick={loadRegions}>
                  {regions.phase === "loading" ? "Calculando zonas…" : "Ver zonas común, agregada y removida"}
                </button>
              )}
              {regions.phase === "error" && regions.message && <p role="alert" className="alert alert-warn">{regions.message}</p>}
              {regions.phase === "ready" && regions.data?.regions && (
                <>
                  {(Object.keys(ZONES) as Zone[]).map((zone) => {
                    const info: RegionInfo = regions.data!.regions![zone];
                    if (info.status === "ok")
                      return (
                        <label key={zone} className="inline">
                          <input type="checkbox" checked={regions.visible[zone]} onChange={(e) => toggleZone(zone, e.target.checked)} />
                          <span className={`swatch swatch-${zone}`} aria-hidden="true" />
                          {`${ZONES[zone].text} (${ZONES[zone].color}) · ${Math.round(info.volume_m3 ?? 0).toLocaleString("es-PE")} m³`}
                        </label>
                      );
                    if (info.status === "empty") return <p key={zone} className="note">{ZONES[zone].none}</p>;
                    return <p key={zone} className="note">{`${ZONES[zone].text}: no disponible (${exclusionText(info.reason ?? "")}).`}</p>;
                  })}
                  <p className="note">Provisional: las zonas se calcularon sobre una copia con la orientación de las caras normalizada. Se ocultaron los dos periodos para verlas; actívalos si los necesitas.</p>
                </>
              )}
              {regions.phase === "idle" && <p className="note">Muestra qué parte del sólido se mantiene, cuál se agregó y cuál se quitó entre los dos periodos. La primera vez puede tardar unos segundos.</p>}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
