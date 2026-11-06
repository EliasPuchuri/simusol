import type { PeriodOverlap, VolumeTotals } from "../api";
import { exclusionText, signed, signedPercent, volumeShort, volumeText } from "../dashboard";
import { plural } from "../format";

const NOTES: Record<string, string> = {
  sum_of_bodies_not_union: "Es la suma de los volúmenes de cada sólido, no el volumen de la unión.",
  overlap_not_evaluated: "La superposición entre sólidos no se evaluó: si dos sólidos se solapan, ese espacio se cuenta dos veces.",
  orientation_normalized: "Hay mallas con la orientación invertida: sus volúmenes se calcularon sobre una copia corregida (provisional).",
  excluded_solids: "Hay sólidos sin volumen válido: no entran en la suma.",
  duplicate_keys_excluded: "Hay nombres repetidos dentro de un periodo: esos sólidos no entran en la suma.",
};

const millions = (v: number) => `${(v / 1e6).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} M`;

function overlapNote(totals: Extract<VolumeTotals, { available: true }>): string | null {
  const text = (label: string, o: PeriodOverlap | undefined) =>
    o?.evaluated && o.pairs ? `${plural(o.pairs, "par", "pares")} en el periodo ${label} (${volumeShort(o.pairwise_common_m3)} m³ en común)` : null;
  const parts = [text("anterior", totals.previous.overlap), text("actual", totals.current.overlap)].filter(Boolean);
  return parts.length ? `Hay sólidos que se superponen: ${parts.join(" y ")}. Ese espacio se cuenta más de una vez en la suma.` : null;
}

export function TotalsCard({ totals, previousLabel, currentLabel }: { totals: VolumeTotals | undefined; previousLabel: string; currentLabel: string }) {
  if (!totals || !totals.available) return null;
  const excluded = [
    ...totals.previous.excluded.map((e) => ({ ...e, reason: e.reason.includes(":") ? e.reason : `${e.reason}:previous` })),
    ...totals.current.excluded.map((e) => ({ ...e, reason: e.reason.includes(":") ? e.reason : `${e.reason}:current` })),
  ];
  return (
    <section className="dash-card" aria-label="Volumen total">
      <h4>Volúmenes totales <small className="badge badge-demo">Provisional</small></h4>
      <div className="total-bars" aria-hidden="true">
        {([["prev", totals.previous.sum_m3, previousLabel], ["curr", totals.current.sum_m3, currentLabel]] as const).map(([k, v, label]) => (
          <div key={k} className="total-col">
            <span className="col-value">{millions(v)}</span>
            <span className={`col-bar col-${k}`} style={{ height: `${(100 * v) / Math.max(1, totals.previous.sum_m3, totals.current.sum_m3)}%` }} />
            <span className="col-label">{label}</span>
          </div>
        ))}
      </div>
      <dl className="totals">
        <div><dt>Periodo anterior</dt><dd>{`${volumeText(totals.previous.sum_m3)} m³`}</dd>
          <small>{totals.previous.counted} de {totals.previous.total} sólidos del periodo anterior con volumen válido</small></div>
        <div><dt>Periodo actual</dt><dd>{`${volumeText(totals.current.sum_m3)} m³`}</dd>
          <small>{totals.current.counted} de {totals.current.total} sólidos del periodo actual con volumen válido</small></div>
        <div><dt>Diferencia</dt>
          <dd>{`${signed(totals.difference_m3)} m³${totals.difference_pct == null ? "" : ` (${signedPercent(totals.difference_pct)})`}`}</dd>
          <small>actual menos anterior; el porcentaje es sobre el periodo anterior</small></div>
      </dl>
      <details className="notes-box">
        <summary>Cómo leer este total</summary>
        <ul className="notes">
          {totals.warnings.map((w) => (w === "overlap_found" ? overlapNote(totals) : NOTES[w]) && <li key={w}>{w === "overlap_found" ? overlapNote(totals) : NOTES[w]}</li>)}
        </ul>
      </details>
      {excluded.length > 0 && (
        <details>
          <summary>Ver sólidos sin volumen ({excluded.length})</summary>
          <ul>{excluded.map((e) => <li key={`${e.key}-${e.reason}`}>{e.key}: {exclusionText(e.reason)}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
