import { useEffect, useMemo, useRef, useState } from "react";

import { api, type Matches } from "../api";
import { friendlyError } from "../format";
import { ClassificationPanel } from "./ClassificationPanel";
import { Viewer3D } from "./Viewer3D";

type Props = {
  previousId: string | null; currentId: string | null; previousLabel: string; currentLabel: string;
  reviewer: string; onReviewerChange: (name: string) => void;
};

export function Results({ previousId, currentId, previousLabel, currentLabel, reviewer, onReviewerChange }: Props) {
  const [matches, setMatches] = useState<Matches | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const viewerAnchor = useRef<HTMLElement>(null);

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

  return (
    <section className="card results" aria-labelledby="results-t">
      <h2 id="results-t">Comparación</h2>
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

          <ClassificationPanel previousId={previousId} currentId={currentId} previousLabel={previousLabel} currentLabel={currentLabel}
            onView={open} viewing={viewing} reviewer={reviewer} onReviewerChange={onReviewerChange} />

          <section ref={viewerAnchor} className="viewer-panel" aria-label="Visor 3D">
            <label className="field viewer-filter">
              <span>Filtrar sólido</span>
              <select value={viewing ?? ""} onChange={(e) => open(e.target.value || null)}>
                <option value="">Elige el sólido que vas a revisar…</option>
                {keys.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            {viewing
              ? <Viewer3D previousId={previousId} currentId={currentId} solidKey={viewing} />
              : <p className="note">Elige un sólido en la lista, o pulsa «Ver en 3D» en la tabla, para ver los dos periodos superpuestos.</p>}
          </section>
        </>
      )}
    </section>
  );
}
