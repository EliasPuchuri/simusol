import { Fragment, useCallback, useEffect, useState } from "react";

import { api, type ComparisonReport, type ComparisonRow, type Review } from "../api";
import { POLL_MS } from "../config";
import { filterRows, latestOrientation, percentOf, shortOrientation, typeText, volumeText, type Scope } from "../dashboard";
import { describeRowFailure, describeRule, describeWarning, plural } from "../format";
import { OrientationChart } from "./OrientationChart";
import { ReviewForm } from "./ReviewForm";
import { TotalsCard } from "./TotalsCard";
import { VolumeChart } from "./VolumeChart";

type Props = { previousId: string; currentId: string; onView: (key: string) => void; reviewer: string; onReviewerChange: (name: string) => void };
type Expanded = { kind: "why" | "review" | "general"; key: string } | null;
type Filter = "all" | "SIN CAMBIOS" | "VARIABLE" | "NUEVO" | "ELIMINADO" | "unassigned" | "pending";

const LABEL = { "SIN CAMBIOS": "Sin cambios", VARIABLE: "Variable", NUEVO: "Nuevo", ELIMINADO: "Eliminado" } as const;
const pct = (v: number | null | undefined, signed = false) => {
  if (v == null) return "—";
  const r = Math.abs(v) < 0.05 ? 0 : v; // never show "-0.0 %"
  return `${signed && r > 0 ? "+" : ""}${r.toFixed(1)} %`;
};
const meters = (v: number | null | undefined) => (v == null ? "—" : `${v.toFixed(2)} m`);

function stateLabel(r: ComparisonRow): string {
  if (r.state) return LABEL[r.state];
  return r.status === "pending" ? "Pendiente" : "Sin clasificar";
}

export function ClassificationPanel({ previousId, currentId, onView, reviewer, onReviewerChange }: Props) {
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<Expanded>(null);
  const [reviews, setReviews] = useState<Record<string, Review>>({});
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [scope, setScope] = useState<Scope>("any");
  const [minText, setMinText] = useState("");
  const [maxText, setMaxText] = useState("");

  const load = useCallback(async () => {
    try {
      setReport(await api.getComparison(previousId, currentId));
      setError(null);
    } catch {
      setError("No se pudo consultar el estado de la comparación.");
    }
  }, [previousId, currentId]);

  useEffect(() => {
    setReport(null);
    setOpen(null);
    void load();
  }, [load]);

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

  const running = report?.run?.state === "queued" || report?.run?.state === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => void load(), POLL_MS.comparison);
    return () => clearInterval(timer);
  }, [running, load]);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      await api.startComparison(previousId, currentId);
      await load();
    } catch {
      setError("No se pudo iniciar el cálculo. Inténtalo de nuevo.");
    } finally {
      setStarting(false);
    }
  }

  const rows = report?.rows ?? [];
  const calculated = rows.some((r) => r.status === "ok" || r.status === "failed");
  const interrupted = report?.run?.state === "failed";
  const s = report?.summary;
  const counts = {
    all: rows.length,
    "SIN CAMBIOS": s?.["SIN CAMBIOS"] ?? 0, VARIABLE: s?.VARIABLE ?? 0, NUEVO: s?.NUEVO ?? 0, ELIMINADO: s?.ELIMINADO ?? 0,
    unassigned: s?.sin_clasificar ?? 0, pending: s?.pendientes ?? 0,
  };
  const num = (t: string) => {
    const n = Number(t.trim().replace(",", "."));
    return t.trim() === "" || !Number.isFinite(n) ? null : n;
  };
  const min = num(minText), max = num(maxText);
  const visible = filterRows(rows, { state: filter, type, scope, min, max, query });
  const base = counts["SIN CAMBIOS"] + counts.VARIABLE + counts.NUEVO + counts.ELIMINADO;
  const share = (n: number) => (calculated ? ` (${percentOf(n, base)})` : "");
  const scopeText = scope === "previous" ? "del periodo anterior" : scope === "current" ? "del periodo actual" : "de cualquiera de los dos periodos";
  const tabs: [Filter, string][] = [
    ["all", `Todos (${counts.all})`], ["SIN CAMBIOS", `Sin cambios (${counts["SIN CAMBIOS"]})`], ["VARIABLE", `Variables (${counts.VARIABLE})`],
    ["NUEVO", `Nuevos (${counts.NUEVO})`], ["ELIMINADO", `Eliminados (${counts.ELIMINADO})`],
    ...(counts.unassigned > 0 ? [["unassigned", `Sin clasificar (${counts.unassigned})`] as [Filter, string]] : []),
    ...(counts.pending > 0 ? [["pending", `Pendientes (${counts.pending})`] as [Filter, string]] : []),
  ];

  return (
    <section className="classification" aria-labelledby="class-title">
      <h3 id="class-title">Clasificación de cambios</h3>
      <p className="alert alert-warn">
        <strong>Resultados provisionales.</strong> Los volúmenes se calcularon sobre una copia con la orientación de las caras normalizada
        (las mallas recibidas la tienen invertida) y los umbrales de clasificación son de trabajo. Falta la aprobación del área.
      </p>

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

      {report && rows.length > 0 && (calculated || counts.NUEVO + counts.ELIMINADO > 0) && !running && (
        <>
          <ul className="chips" aria-label="Resumen de estados">
            {calculated && <li className="chip chip-both">{`${counts["SIN CAMBIOS"]} sin cambios${share(counts["SIN CAMBIOS"])}`}</li>}
            {calculated && <li className="chip chip-var">{`${counts.VARIABLE} ${counts.VARIABLE === 1 ? "variable" : "variables"}${share(counts.VARIABLE)}`}</li>}
            <li className="chip chip-new">{`${counts.NUEVO} ${counts.NUEVO === 1 ? "nuevo" : "nuevos"}${share(counts.NUEVO)}`}</li>
            <li className="chip chip-del">{`${counts.ELIMINADO} ${counts.ELIMINADO === 1 ? "eliminado" : "eliminados"}${share(counts.ELIMINADO)}`}</li>
          </ul>
          {calculated && <p className="note">Porcentajes sobre {plural(base, "sólido", "sólidos")} con estado; los sin clasificar y los pendientes se cuentan aparte.</p>}
          {calculated && report && (
            <div className="dash">
              <TotalsCard totals={report.totals} />
              <VolumeChart rows={rows} />
              <OrientationChart rows={rows} onView={onView} />
            </div>
          )}
          {counts.unassigned > 0 && <p className="alert alert-error">{counts.unassigned} sin clasificar: el cálculo falló para esos pares; no se les asignó ningún estado.</p>}
          {counts.pending > 0 && <p className="note">{plural(counts.pending, "par pendiente", "pares pendientes")} de calcular.</p>}

          <div className="tabs" role="group" aria-label="Filtrar por estado">
            {tabs.map(([k, text]) => <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>{text}</button>)}
          </div>

          <div className="filters">
            <label className="field"><span>Buscar en la clasificación</span><input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Nombre del sólido…" /></label>
            <label className="field"><span>Tipo de cuerpo</span>
              <select value={type} onChange={(e) => setType(e.target.value)}>
                <option value="">Todos</option><option value="TABULAR">Tabular</option><option value="TABULAR CURVO">Tabular curvo</option><option value="GLOBULAR">Globular</option>
              </select></label>
            <label className="field"><span>Aplicar tipo y volumen al periodo</span>
              <select value={scope} onChange={(e) => setScope(e.target.value as Scope)}>
                <option value="any">Cualquiera</option><option value="previous">Anterior</option><option value="current">Actual</option>
              </select></label>
            <label className="field"><span>Volumen mínimo (m³)</span><input inputMode="decimal" value={minText} onChange={(e) => setMinText(e.target.value)} /></label>
            <label className="field"><span>Volumen máximo (m³)</span><input inputMode="decimal" value={maxText} onChange={(e) => setMaxText(e.target.value)} /></label>
          </div>
          <p className="note">
            <span>{`${visible.length} de ${rows.length} sólidos`}</span>
            {(min !== null || max !== null) && <span> · Filtrando por el volumen {scopeText}.</span>}
          </p>

          <div className="table-wrap">
            <table aria-label="Clasificación por sólido">
              <thead><tr><th>Sólido</th><th>Estado</th><th>Tipo de cuerpo</th><th>Volumen (anterior → actual, m³)</th><th>Orientación</th><th>Qué cambió</th><th>Coincidencia (IoU)</th><th>Variación de volumen</th><th>Distancia P95</th><th>Centro</th><th>Acciones</th></tr></thead>
              <tbody>
                {visible.map((r) => (
                  <Fragment key={r.key}>
                    <tr>
                      <td>{r.key}</td>
                      <td>
                        <span className={`pill pill-state-${r.state ?? (r.status === "pending" ? "pending" : "none")}`}>{stateLabel(r)}</span>
                        {reviews[r.key] && <small className="badge badge-demo">{reviews[r.key].agrees ? "Tu opinión: de acuerdo" : "Tu opinión: con observaciones"}</small>}
                      </td>
                      <td>{typeText(r)}</td>
                      <td>{r.volumes ? `${volumeText(r.volumes.previous_m3)} → ${volumeText(r.volumes.current_m3)}` : "—"}</td>
                      <td>{shortOrientation(latestOrientation(r))}</td>
                      <td>{r.status === "failed" || r.status === "incident" ? describeRowFailure(r.description) : r.description}</td>
                      <td>{pct(r.metrics?.iou_pct)}</td><td>{pct(r.metrics?.delta_volume_pct, true)}</td>
                      <td>{meters(r.metrics?.p95_m)}</td><td>{meters(r.metrics?.centroid_m)}</td>
                      <td className="row-actions">
                        <button type="button" aria-label={`Ver en 3D: ${r.key}`} onClick={() => onView(r.key)}>Ver en 3D</button>
                        {r.checks.length > 0 && (
                          <button type="button" aria-label={`Por qué: ${r.key}`} aria-expanded={open?.kind === "why" && open.key === r.key}
                            onClick={() => setOpen(open?.kind === "why" && open.key === r.key ? null : { kind: "why", key: r.key })}>Por qué</button>
                        )}
                        <button type="button" aria-label={`Opinar: ${r.key}`} aria-expanded={open?.kind === "review" && open.key === r.key}
                          onClick={() => setOpen(open?.kind === "review" && open.key === r.key ? null : { kind: "review", key: r.key })}>Opinar</button>
                      </td>
                    </tr>
                    {open?.kind === "why" && open.key === r.key && (
                      <tr>
                        <td colSpan={11}>
                          <section aria-label={`Por qué: ${r.key}`} className="why">
                            {(["identico", "no_significativo"] as const).map((group) => (
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
                            {r.warnings.length > 0 && <ul className="warnings">{r.warnings.map((w) => <li key={w}>{describeWarning(w)}</li>)}</ul>}
                          </section>
                        </td>
                      </tr>
                    )}
                    {open?.kind === "review" && open.key === r.key && (
                      <tr>
                        <td colSpan={11}>
                          <ReviewForm title={`Tu opinión sobre ${r.key}`} rowKey={r.key} systemLabel={stateLabel(r)} reviewer={reviewer}
                            onReviewerChange={onReviewerChange} previousId={previousId} currentId={currentId} onSaved={loadReviews} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
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

      {!running && report && (
        <button type="button" disabled={starting} onClick={start} className={!calculated && !interrupted ? "primary" : undefined}>
          {interrupted ? "Reintentar el cálculo" : calculated ? "Volver a calcular" : "Calcular cambios entre los dos periodos"}
        </button>
      )}
    </section>
  );
}
