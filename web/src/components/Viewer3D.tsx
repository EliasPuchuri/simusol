import { useEffect, useRef, useState } from "react";

import { api, type SceneLayer } from "../api";
import { plural } from "../format";
import { DEFAULT_OPACITY } from "../viewer/defaults";
import { ThreeScene, WebGLUnavailableError, type Role } from "../viewer/ThreeScene";

type Props = { previousId: string; currentId: string; solidKey: string; onClose: () => void };
type LayerUi = { layer: SceneLayer; visible: boolean; opacity: number };

const NAMES: Record<Role, { text: string; color: string; short: string }> = {
  previous: { text: "Periodo anterior", color: "naranja", short: "periodo anterior" },
  current: { text: "Periodo actual", color: "gris", short: "periodo actual" },
};

export function Viewer3D({ previousId, currentId, solidKey, onClose }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const scene = useRef<ThreeScene | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerUi[]>([]);

  useEffect(() => {
    let cancelled = false;
    let created: ThreeScene | null = null;
    setStatus("loading");
    setMessage(null);
    setLayers([]);

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
          <p className="note">Las zonas comunes, agregadas y removidas aparecerán aquí cuando esté disponible el cálculo de volúmenes.</p>
        </div>
      </div>
    </section>
  );
}
