import type { ComparisonRow, Orientation } from "../api";
import { polarPoint } from "../dashboard";
import { plural } from "../format";

const R = 100;
const usable = (o: Orientation | null | undefined): o is Orientation & { azimuth: number; dip: number } =>
  !!o && o.type !== "no_interpretable" && o.azimuth != null && o.dip != null;

export function OrientationChart({ rows, onView }: { rows: ComparisonRow[]; onView: (key: string) => void }) {
  const items = rows.map((r) => ({ key: r.key, prev: r.characterization?.previous?.orientation, curr: r.characterization?.current?.orientation }))
    .filter((i) => usable(i.prev) || usable(i.curr));
  const without = rows.filter((r) => ![r.characterization?.previous?.orientation, r.characterization?.current?.orientation].some(usable)
    && (r.characterization?.previous || r.characterization?.current)).length;
  const dot = (o: Orientation & { azimuth: number; dip: number }, period: "previous" | "current") => {
    const { x, y } = polarPoint(o.azimuth, o.dip, R);
    return <circle data-period={period} data-kind={o.type} cx={x} cy={y} r={4.5} className={`pt pt-${period}${o.type === "axial" ? " pt-axial" : ""}`} />;
  };
  return (
    <section className="dash-card" aria-label="Orientación de los sólidos">
      <h4>Orientación de los sólidos</h4>
      <svg viewBox="-125 -125 250 250" role="img" aria-label="Gráfico polar de Azimuth y Dip de los sólidos" className="polar">
        {[30, 60, 90].map((d) => <circle key={d} cx={0} cy={0} r={(R * d) / 90} className="ring" />)}
        <line x1={0} y1={-R} x2={0} y2={R} className="axis" /><line x1={-R} y1={0} x2={R} y2={0} className="axis" />
        <text x={0} y={-R - 6} textAnchor="middle" className="compass">N</text><text x={R + 8} y={4} textAnchor="middle" className="compass">E</text>
        <text x={0} y={R + 14} textAnchor="middle" className="compass">S</text><text x={-R - 9} y={4} textAnchor="middle" className="compass">O</text>
        {[30, 60].map((d) => <text key={d} x={3} y={-(R * d) / 90 - 2} className="ringlabel">{d}°</text>)}
        {items.map((i) => {
          const a = usable(i.prev) ? polarPoint(i.prev.azimuth, i.prev.dip, R) : null;
          const b = usable(i.curr) ? polarPoint(i.curr.azimuth, i.curr.dip, R) : null;
          return (
            <g key={i.key} role="button" tabIndex={0} aria-label={`Ver ${i.key} en el visor 3D`} className="pt-group"
              onClick={() => onView(i.key)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onView(i.key)}>
              <title>{i.key}{usable(i.prev) ? ` · anterior: Azimuth ${i.prev.azimuth.toFixed(1)}°, Dip ${i.prev.dip.toFixed(1)}°` : ""}{usable(i.curr) ? ` · actual: Azimuth ${i.curr.azimuth.toFixed(1)}°, Dip ${i.curr.dip.toFixed(1)}°` : ""}</title>
              {a && b && <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="link-line" />}
              {usable(i.prev) && dot(i.prev, "previous")}{usable(i.curr) && dot(i.curr, "current")}
            </g>
          );
        })}
      </svg>
      <ul className="legend">
        <li><span className="swatch swatch-previous" aria-hidden="true" /> Periodo anterior (naranja)</li>
        <li><span className="swatch swatch-current" aria-hidden="true" /> Periodo actual (gris)</li>
        <li>Círculo lleno: plano (Azimuth y Dip). Círculo vacío: eje (Trend y Plunge).</li>
      </ul>
      <p className="note">El ángulo es el Azimuth (dirección de buzamiento, desde el Norte hacia el Este) y la distancia al centro es el Dip: 0° en el centro, 90° en el borde. Una línea une el mismo sólido en los dos periodos. Haz clic en un punto para verlo en 3D.</p>
      {without > 0 && <p className="note">{plural(without, "sólido sin orientación interpretable", "sólidos sin orientación interpretable")}: no se dibujan.</p>}
    </section>
  );
}
