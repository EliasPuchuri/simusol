import { periodCounts, type PeriodCounts } from "../dashboard";
import type { ComparisonRow } from "../api";

const GROUPS: { label: string; pick: (c: PeriodCounts) => number }[] = [
  { label: "Total", pick: (c) => c.total },
  { label: "Sin cambios", pick: (c) => c.sinCambios },
  { label: "Variables", pick: (c) => c.variables },
  { label: "Nuevos", pick: (c) => c.nuevos },
  { label: "Eliminados", pick: (c) => c.eliminados },
];

export function CountsChart({ rows, previousLabel, currentLabel }: { rows: ComparisonRow[]; previousLabel: string; currentLabel: string }) {
  const { previous, current } = periodCounts(rows);
  const max = Math.max(1, ...GROUPS.flatMap((g) => [g.pick(previous), g.pick(current)]));
  return (
    <section className="dash-card" aria-label="Conteo de sólidos">
      <h4>Verificación de sólidos</h4>
      <ul className="legend-inline" aria-hidden="true">
        <li><span className="swatch swatch-prev" /> {previousLabel}</li>
        <li><span className="swatch swatch-curr" /> {currentLabel}</li>
      </ul>
      <ul className="columns">
        {GROUPS.map((g) => (
          <li key={g.label} aria-label={`${g.label}: ${g.pick(previous)} en ${previousLabel}, ${g.pick(current)} en ${currentLabel}`}>
            <div className="pair" aria-hidden="true">
              {([["prev", g.pick(previous)], ["curr", g.pick(current)]] as const).map(([k, n]) => (
                <div key={k} className="col">
                  <span className="col-value">{n}</span>
                  <span className={`col-bar col-${k}`} style={{ height: `${(100 * n) / max}%` }} />
                </div>
              ))}
            </div>
            <span className="col-label" aria-hidden="true">{g.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
