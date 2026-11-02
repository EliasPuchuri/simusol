import type { VolumeTotals } from "../api";
import { exclusionText, signed, signedPercent, volumeText } from "../dashboard";

const NOTES: Record<string, string> = {
  sum_of_bodies_not_union: "Es la suma de los volúmenes de cada sólido, no el volumen de la unión.",
  overlap_not_evaluated: "La superposición entre sólidos no se evaluó: si dos sólidos se solapan, ese espacio se cuenta dos veces.",
  orientation_normalized: "Hay mallas con la orientación invertida: sus volúmenes se calcularon sobre una copia corregida (provisional).",
  excluded_solids: "Hay sólidos sin volumen válido: no entran en la suma.",
  duplicate_keys_excluded: "Hay nombres repetidos dentro de un periodo: esos sólidos no entran en la suma.",
};

export function TotalsCard({ totals }: { totals: VolumeTotals | undefined }) {
  if (!totals || !totals.available) return null;
  const excluded = [
    ...totals.previous.excluded.map((e) => ({ ...e, reason: e.reason.includes(":") ? e.reason : `${e.reason}:previous` })),
    ...totals.current.excluded.map((e) => ({ ...e, reason: e.reason.includes(":") ? e.reason : `${e.reason}:current` })),
  ];
  return (
    <section className="dash-card" aria-label="Volumen total">
      <h4>Volumen total <small className="badge badge-demo">Provisional</small></h4>
      <dl className="totals">
        <div><dt>Periodo anterior</dt><dd>{`${volumeText(totals.previous.sum_m3)} m³`}</dd>
          <small>{totals.previous.counted} de {totals.previous.total} sólidos del periodo anterior con volumen válido</small></div>
        <div><dt>Periodo actual</dt><dd>{`${volumeText(totals.current.sum_m3)} m³`}</dd>
          <small>{totals.current.counted} de {totals.current.total} sólidos del periodo actual con volumen válido</small></div>
        <div><dt>Diferencia</dt>
          <dd>{`${signed(totals.difference_m3)} m³${totals.difference_pct == null ? "" : ` (${signedPercent(totals.difference_pct)})`}`}</dd>
          <small>actual menos anterior; el porcentaje es sobre el periodo anterior</small></div>
      </dl>
      <ul className="notes">{totals.warnings.map((w) => NOTES[w] && <li key={w}>{NOTES[w]}</li>)}</ul>
      {excluded.length > 0 && (
        <details>
          <summary>Ver sólidos sin volumen ({excluded.length})</summary>
          <ul>{excluded.map((e) => <li key={`${e.key}-${e.reason}`}>{e.key}: {exclusionText(e.reason)}</li>)}</ul>
        </details>
      )}
    </section>
  );
}
