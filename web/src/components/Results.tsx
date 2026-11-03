import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, type Matches } from "../api";
import { friendlyError } from "../format";
import { useComparison } from "../useComparison";
import { ClassificationPanel } from "./ClassificationPanel";
import { CountsChart } from "./CountsChart";
import { SummaryCards } from "./SummaryCards";
import { TotalsCard } from "./TotalsCard";

// Three.js is most of the bundle: it is fetched only when a solid is opened.
const Viewer3D = lazy(() => import("./Viewer3D").then((m) => ({ default: m.Viewer3D })));

type Props = {
  periods: ReactNode;
  previousId: string | null; currentId: string | null; previousLabel: string; currentLabel: string;
  reviewer: string; onReviewerChange: (name: string) => void;
};

export function Results({ periods, previousId, currentId, previousLabel, currentLabel, reviewer, onReviewerChange }: Props) {
  const [matches, setMatches] = useState<Matches | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const viewerAnchor = useRef<HTMLElement>(null);
  const comparison = useComparison(previousId, currentId);

  useEffect(() => {
    setMatches(null);
    setError(null);
    setViewing(null);
    if (!previousId || !currentId) return;
    let cancelled = false;
    api.matches(previousId, currentId)
      .then((m) => !cancelled && setMatches(m))
      .catch((e) => !cancelled && setError(friendlyError((e as Error).message)));
    return () => {
      cancelled = true;
    };
  }, [previousId, currentId]);

  const keys = useMemo(() => {
    if (!matches) return [];
    return [...matches.pairs, ...matches.only_previous, ...matches.only_current].map((e) => ("key" in e ? e.key : "")).sort((a, b) => a.localeCompare(b));
  }, [matches]);

  function open(key: string | null) {
    setViewing(key);
    if (key) viewerAnchor.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  const showCharts = comparison.calculated && !comparison.running && comparison.report;
  const totals = showCharts ? comparison.report!.totals : undefined;
  const waiting = (title: string) => (
    <section className="dash-card waiting" aria-label={`${title} (pendiente)`}>
      <h4>{title}</h4>
      <p className="note">Se llena cuando cargues los dos periodos y calcules los cambios.</p>
    </section>
  );

  return (
    <div className="board">
      <section className="card board-load" aria-label="Carga de carpetas">{periods}</section>

      <div className="board-counts">
        {showCharts ? <CountsChart rows={comparison.rows} previousLabel={previousLabel} currentLabel={currentLabel} /> : waiting("Verificación de sólidos")}
      </div>
      <div className="board-summary">
        {showCharts
          ? <SummaryCards counts={{ sin: comparison.report!.summary["SIN CAMBIOS"], variable: comparison.report!.summary.VARIABLE, nuevo: comparison.report!.summary.NUEVO, eliminado: comparison.report!.summary.ELIMINADO }} />
          : waiting("Resumen de resultados")}
      </div>

      <section className="card board-table" aria-labelledby="results-t">
        <h2 id="results-t">Tabla de sólidos</h2>
        {!previousId || !currentId ? (
          <p className="empty">Carga los dos periodos para ver la comparación. Aparecerá aquí automáticamente.</p>
        ) : error ? (
          <p role="alert" className="alert alert-error">{error}</p>
        ) : !matches ? (
          <p role="status">Comparando…</p>
        ) : (
          <>
            <p className="note">
              Los sólidos se emparejan por nombre (se ignora «pt» al final). Si un sólido fue renombrado, aparecerá a la vez como «eliminado» y «nuevo»: conviene revisarlo manualmente.
            </p>
            {matches.incidents.map((i, n) => (
              <p key={n} role="alert" className="alert alert-warn">
                {((i.detail.filenames as string[]) ?? []).join(" y ")} corresponderían al mismo sólido en el periodo {i.detail.period === "previous" ? "anterior" : "actual"}; no se compararon.
              </p>
            ))}
            <ClassificationPanel comparison={comparison} previousId={previousId} currentId={currentId} previousLabel={previousLabel} currentLabel={currentLabel}
              onView={open} viewing={viewing} reviewer={reviewer} onReviewerChange={onReviewerChange} />
          </>
        )}
      </section>

      <section ref={viewerAnchor} className="card board-viewer" aria-label="Visor 3D">
        <h2>Visor 3D de sólidos superpuestos</h2>
        {previousId && currentId && matches ? (
          <>
            <label className="field viewer-filter">
              <span>Filtrar sólido</span>
              <select value={viewing ?? ""} onChange={(e) => open(e.target.value || null)}>
                <option value="">Elige el sólido que vas a revisar…</option>
                {keys.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            {viewing
              ? (
                <Suspense fallback={<p role="status">Preparando la vista 3D…</p>}>
                  <Viewer3D previousId={previousId} currentId={currentId} solidKey={viewing} />
                </Suspense>
              )
              : <p className="note">Elige un sólido en la lista, o pulsa «Ver en 3D» en la tabla, para ver los dos periodos superpuestos.</p>}
          </>
        ) : <p className="note">Se activa cuando cargues los dos periodos.</p>}
      </section>

      <div className="board-totals">
        {totals?.available ? <TotalsCard totals={totals} previousLabel={previousLabel} currentLabel={currentLabel} /> : waiting("Volúmenes totales")}
      </div>
    </div>
  );
}
