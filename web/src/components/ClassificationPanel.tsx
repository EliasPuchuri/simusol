import { Fragment, useCallback, useEffect, useState } from "react";

import { api, type ComparisonRow, type Review } from "../api";
import { degreeText, diffPercent, diffText, filterRows, latestOrientation, typeText, volumeExact } from "../dashboard";
import type { Comparison } from "../useComparison";
import { describeRowFailure, describeRule, describeWarning, plural } from "../format";
import { ReviewForm } from "./ReviewForm";
import { SpatialNotice } from "./SpatialNotice";

type Props = {
  comparison: Comparison; previousId: string; currentId: string; previousLabel: string; currentLabel: string;
  onView: (key: string) => void; viewing: string | null; reviewer: string; onReviewerChange: (name: string) => void;
};
type Expanded = { kind: "why" | "review" | "general"; key: string } | null;
type Filter = "all" | "SIN CAMBIOS" | "VARIABLE" | "NUEVO" | "ELIMINADO" | "unassigned" | "pending";

const LABEL = { "SIN CAMBIOS": "Sin cambios", VARIABLE: "Variable", NUEVO: "Nuevo", ELIMINADO: "Eliminado" } as const;

function stateLabel(r: ComparisonRow): string {
  if (r.state) return LABEL[r.state];
  return r.status === "pending" ? "Pendiente" : "Sin clasificar";
}

export function ClassificationPanel({ comparison, previousId, currentId, previousLabel, currentLabel, onView, viewing, reviewer, onReviewerChange }: Props) {
  const { report, rows, error, starting, running, calculated, interrupted, start } = comparison;
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<Expanded>(null);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [query, setQuery] = useState("");

  useEffect(() => {
    setOpen(null);
  }, [previousId, currentId]);

  const loadReviews = useCallback(async () => {
    if (!reviewer.trim()) return setReviews({});
    try {
      const { reviews: list } = await api.listReviews(previousId, currentId, reviewer.trim());
      setReviews(Object.fromEntries(list.map((r) => [r.key, r])));
    } catch {
      /* opinions are optional: the table keeps working without the badges */
    }
  }, [previousId, currentId, reviewer]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews]);

  const s = report?.summary;
  const counts = {
    all: rows.length,
    "SIN CAMBIOS": s?.["SIN CAMBIOS"] ?? 0, VARIABLE: s?.VARIABLE ?? 0, NUEVO: s?.NUEVO ?? 0, ELIMINADO: s?.ELIMINADO ?? 0,
    unassigned: s?.sin_clasificar ?? 0, pending: s?.pendientes ?? 0,
  };
  const visible = filterRows(rows, { state: filter, query });
  const tabs: [Filter, string][] = [
    ["all", `Todos (${counts.all})`], ["SIN CAMBIOS", `Sin cambios (${counts["SIN CAMBIOS"]})`], ["VARIABLE", `Variables (${counts.VARIABLE})`],
    ["NUEVO", `Nuevos (${counts.NUEVO})`], ["ELIMINADO", `Eliminados (${counts.ELIMINADO})`],
    ...(counts.unassigned > 0 ? [["unassigned", `Sin clasificar (${counts.unassigned})`] as [Filter, string]] : []),
    ...(counts.pending > 0 ? [["pending", `Pendientes (${counts.pending})`] as [Filter, string]] : []),
  ];

  return (
    <section className="classification" aria-labelledby="class-title">
      <h3 id="class-title">Clasificación de cambios</h3>
      <details className="alert alert-warn provisional">
        <summary><strong>Resultados provisionales</strong></summary>
        <p>
          Los volúmenes se calcularon sobre una copia con la orientación de las caras normalizada
          (las mallas recibidas la tienen invertida) y los umbrales de clasificación son de trabajo. Falta la aprobación del área.
        </p>
      </details>

      <SpatialNotice spatial={report?.spatial} />

      {running && report?.run && (
        <div role="status" aria-live="polite" className="progress">
          <progress max={report.run.total} value={report.run.done} />
          <span>Comparando: {report.run.done} de {report.run.total} pares listos…</span>
        </div>
      )}
      {interrupted && <p role="alert" className="alert alert-warn">El cálculo se interrumpió antes de terminar. Puedes volver a iniciarlo: lo ya calculado no se repite.</p>}
      {error && <p role="alert" className="alert alert-error">{error}</p>}

      {!running && !calculated && !interrupted && report && (
        <p className="note">Todavía no se calcularon los cambios de forma, volumen y orientación entre los dos periodos. «Nuevo» y «Eliminado» ya se conocen por los nombres.</p>
      )}

      {!running && report && (
        <p className="actions">
          <button type="button" disabled={starting} onClick={start} className={!calculated && !interrupted ? "primary" : undefined}>
            {interrupted ? "Reintentar el cálculo" : calculated ? "Volver a calcular" : "Calcular cambios entre los dos periodos"}
          </button>
        </p>
      )}

      {counts.unassigned > 0 && <p className="alert alert-error">{counts.unassigned} sin clasificar: el cálculo falló para esos pares; no se les asignó ningún estado.</p>}
      {counts.pending > 0 && !running && calculated && <p className="note">{plural(counts.pending, "par pendiente", "pares pendientes")} de calcular.</p>}

      {report && rows.length > 0 && (
        <>
          <div className="toolbar">
            <div className="tabs" role="group" aria-label="Filtrar por estado">
              {tabs.map(([k, text]) => <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>{text}</button>)}
            </div>
            <label className="search">
              <span className="sr-only">Buscar en la clasificación</span>
              <input type="search" aria-label="Buscar en la clasificación" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Buscar sólido…" />
            </label>
          </div>

          <div className="table-wrap">
            <table aria-label="Clasificación por sólido">
              <thead>
                <tr>
                  <th>Sólido</th><th>Tipo de cuerpo</th><th>Estado</th>
                  <th className="numeric">Volumen (m³)<small className="th-sub">{previousLabel}</small></th><th className="numeric">Volumen (m³)<small className="th-sub">{currentLabel}</small></th>
                  <th className="numeric">Dif. %</th><th className="numeric">Azimuth (°)</th><th className="numeric">Dip (°)</th><th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => {
                  const orientation = latestOrientation(r);
                  const usable = orientation && orientation.azimuth != null && orientation.dip != null;
                  return (
                    <Fragment key={r.key}>
                      <tr className={viewing === r.key ? "row-selected" : undefined}>
                        <td className="cell-name">{r.key}</td>
                        <td data-label="Tipo de cuerpo">{typeText(r)}</td>
                        <td className="cell-state">
                          <span className={`pill pill-state-${r.state ?? (r.status === "pending" ? "pending" : "none")}`}>{stateLabel(r)}</span>
                          {reviews[r.key] && <small className="badge badge-demo">{reviews[r.key].agrees ? "Tu opinión: de acuerdo" : "Tu opinión: con observaciones"}</small>}
                        </td>
                        <td className="numeric" data-label={`Vol. ${previousLabel} (m³)`}>{volumeExact(r.volumes?.previous_m3)}</td>
                        <td className="numeric" data-label={`Vol. ${currentLabel} (m³)`}>{volumeExact(r.volumes?.current_m3)}</td>
                        <td className="numeric" data-label="Dif. %">{diffText(diffPercent(r))}</td>
                        <td className="numeric" data-label="Azimuth (°)">
                          {usable ? degreeText(orientation.azimuth) : "—"}
                          {usable && orientation.type === "axial" && <small className="axis-tag" title="Es un eje: Trend y Plunge, no un plano">eje</small>}
                        </td>
                        <td className="numeric" data-label="Dip (°)">{usable ? degreeText(orientation.dip) : "—"}</td>
                        <td className="cell-wide">
                          <div className="row-actions">
                          <button type="button" aria-label={`Ver en 3D: ${r.key}`} aria-pressed={viewing === r.key} onClick={() => onView(r.key)}>Ver en 3D</button>
                          <button type="button" aria-label={`Por qué: ${r.key}`} aria-expanded={open?.kind === "why" && open.key === r.key}
                            onClick={() => setOpen(open?.kind === "why" && open.key === r.key ? null : { kind: "why", key: r.key })}>Por qué</button>
                          <button type="button" aria-label={`Opinar: ${r.key}`} aria-expanded={open?.kind === "review" && open.key === r.key}
                            onClick={() => setOpen(open?.kind === "review" && open.key === r.key ? null : { kind: "review", key: r.key })}>Opinar</button>
                          </div>
                        </td>
                      </tr>
                      {open?.kind === "why" && open.key === r.key && (
                        <tr>
                          <td colSpan={9}>
                            <section aria-label={`Por qué: ${r.key}`} className="why">
                              <p>{r.status === "failed" || r.status === "incident" ? describeRowFailure(r.description) : r.description}</p>
                              {(["identico", "no_significativo"] as const).map((group) => r.checks.some((c) => c.group === group) && (
                                <div key={group}>
                                  <strong>{group === "identico" ? "Para ser prácticamente idéntico" : "Para ser un cambio no significativo"}</strong>
                                  <ul>
                                    {r.checks.filter((c) => c.group === group).map((c, n) => (
                                      <li key={n} className={c.applicable ? (c.passed ? "ok" : "bad") : "na"}>
                                        <span aria-hidden="true">{c.applicable ? (c.passed ? "✓" : "✗") : "–"}</span> {describeRule(c)}
                                        <span className="sr-only">{c.applicable ? (c.passed ? " (cumple)" : " (no cumple)") : ""}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ))}
                              {r.metrics && (
                                <p className="note">
                                  Medidas: IoU {r.metrics.iou_pct == null ? "—" : `${r.metrics.iou_pct.toFixed(1)} %`} · distancia P95 {r.metrics.p95_m == null ? "—" : `${r.metrics.p95_m.toFixed(2)} m`} · centro desplazado {r.metrics.centroid_m == null ? "—" : `${r.metrics.centroid_m.toFixed(2)} m`}
                                </p>
                              )}
                              {r.warnings.length > 0 && <ul className="warnings">{r.warnings.map((w) => <li key={w}>{describeWarning(w)}</li>)}</ul>}
                            </section>
                          </td>
                        </tr>
                      )}
                      {open?.kind === "review" && open.key === r.key && (
                        <tr>
                          <td colSpan={9}>
                            <ReviewForm title={`Tu opinión sobre ${r.key}`} rowKey={r.key} systemLabel={stateLabel(r)} reviewer={reviewer}
                              onReviewerChange={onReviewerChange} previousId={previousId} currentId={currentId} onSaved={loadReviews} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
            {visible.length === 0 && <p className="empty">Ningún sólido coincide con lo buscado.</p>}
          </div>
          <p className="note">{`${visible.length} de ${rows.length} sólidos`}</p>
          <p className="actions">
            <a className="button" href={api.comparisonCsvUrl(previousId, currentId)} download>Descargar reporte de comparación (CSV)</a>
            <button type="button" onClick={() => setOpen(open?.kind === "general" ? null : { kind: "general", key: "*" })}>Escribir una observación general</button>
            <a className="button" href={api.reviewsCsvUrl(previousId, currentId)} download>Descargar mis opiniones (CSV)</a>
          </p>
          {open?.kind === "general" && (
            <ReviewForm title="Observación general" rowKey="*" reviewer={reviewer} onReviewerChange={onReviewerChange}
              previousId={previousId} currentId={currentId} onSaved={loadReviews} />
          )}
        </>
      )}
    </section>
  );
}
