import { useState } from "react";

import type { ComparisonRow } from "../api";
import { deltaVolumes, signed } from "../dashboard";
import { plural } from "../format";

const LABEL = { "SIN CAMBIOS": "Sin cambios", VARIABLE: "Variable", NUEVO: "Nuevo", ELIMINADO: "Eliminado" } as const;
const LIMIT = 12;

export function VolumeChart({ rows }: { rows: ComparisonRow[] }) {
  const [all, setAll] = useState(false);
  const data = deltaVolumes(rows);
  const shown = all ? data : data.slice(0, LIMIT);
  const max = Math.max(1, ...data.map((d) => Math.abs(d.delta)));
  return (
    <section className="dash-card" aria-label="Diferencia de volumen por sólido">
      <h4>Diferencia de volumen por sólido <small className="badge badge-demo">Provisional</small></h4>
      {data.length === 0 ? <p className="note">Ningún sólido cambió de volumen, o todavía no hay volúmenes calculados.</p> : (
        <>
          <p className="note">Izquierda: el volumen disminuyó. Derecha: aumentó. Los sólidos nuevos suman su volumen y los eliminados lo restan. Unidades en m³.</p>
          <ul className="bars">
            {shown.map((d) => (
              <li key={d.key}>
                <span className="bar-key">{d.key}{d.state && <small className="bar-state">{LABEL[d.state]}</small>}</span>
                <span className="bar-track bar-left">{d.delta < 0 && <span className={`bar bar-${d.state ?? "none"}`} style={{ width: `${(100 * Math.abs(d.delta)) / max}%` }} />}</span>
                <span className="bar-track bar-right">{d.delta > 0 && <span className={`bar bar-${d.state ?? "none"}`} style={{ width: `${(100 * d.delta) / max}%` }} />}</span>
                <span className="bar-value">{`${signed(d.delta)} m³`}</span>
              </li>
            ))}
          </ul>
          {data.length > LIMIT && (
            <button type="button" className="link" onClick={() => setAll(!all)}>
              {all ? "Mostrar solo los más grandes" : `Mostrar los ${plural(data.length - LIMIT, "restante", "restantes")}`}
            </button>
          )}
        </>
      )}
    </section>
  );
}
