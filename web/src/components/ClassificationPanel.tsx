import { Fragment, useCallback, useEffect, useState } from "react";

import { api, type ComparisonReport, type ComparisonRow } from "../api";
import { POLL_MS } from "../config";
import { describeRowFailure, describeRule, describeWarning, plural } from "../format";

type Props = { previousId: string; currentId: string; onView: (key: string) => void };
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

export function ClassificationPanel({ previousId, currentId, onView }: Props) {
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);

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
  const visible = rows.filter((r) =>
    filter === "all" ? true : filter === "unassigned" ? r.state === null && r.status !== "pending"
      : filter === "pending" ? r.status === "pending" : r.state === filter);
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
            {calculated && <li className="chip chip-both">{`${counts["SIN CAMBIOS"]} sin cambios`}</li>}
            {calculated && <li className="chip chip-var">{`${counts.VARIABLE} ${counts.VARIABLE === 1 ? "variable" : "variables"}`}</li>}
            <li className="chip chip-new">{`${counts.NUEVO} ${counts.NUEVO === 1 ? "nuevo" : "nuevos"}`}</li>
            <li className="chip chip-del">{`${counts.ELIMINADO} ${counts.ELIMINADO === 1 ? "eliminado" : "eliminados"}`}</li>
          </ul>
          {counts.unassigned > 0 && <p className="alert alert-error">{counts.unassigned} sin clasificar: el cálculo falló para esos pares; no se les asignó ningún estado.</p>}
          {counts.pending > 0 && <p className="note">{plural(counts.pending, "par pendiente", "pares pendientes")} de calcular.</p>}

          <div className="tabs" role="group" aria-label="Filtrar por estado">
            {tabs.map(([k, text]) => <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>{text}</button>)}
          </div>

          <div className="table-wrap">
            <table aria-label="Clasificación por sólido">
              <thead><tr><th>Sólido</th><th>Estado</th><th>Qué cambió</th><th>Coincidencia (IoU)</th><th>Variación de volumen</th><th>Distancia P95</th><th>Centro</th><th>Acciones</th></tr></thead>
              <tbody>
                {visible.map((r) => (
                  <Fragment key={r.key}>
                    <tr>
                      <td>{r.key}</td>
                      <td><span className={`pill pill-state-${r.state ?? (r.status === "pending" ? "pending" : "none")}`}>{stateLabel(r)}</span></td>
                      <td>{r.status === "failed" || r.status === "incident" ? describeRowFailure(r.description) : r.description}</td>
                      <td>{pct(r.metrics?.iou_pct)}</td><td>{pct(r.metrics?.delta_volume_pct, true)}</td>
                      <td>{meters(r.metrics?.p95_m)}</td><td>{meters(r.metrics?.centroid_m)}</td>
                      <td className="row-actions">
                        <button type="button" aria-label={`Ver en 3D: ${r.key}`} onClick={() => onView(r.key)}>Ver en 3D</button>
                        {r.checks.length > 0 && (
                          <button type="button" aria-label={`Por qué: ${r.key}`} aria-expanded={open === r.key} onClick={() => setOpen(open === r.key ? null : r.key)}>Por qué</button>
                        )}
                      </td>
                    </tr>
                    {open === r.key && (
                      <tr>
                        <td colSpan={8}>
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
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <p><a className="button" href={api.comparisonCsvUrl(previousId, currentId)} download>Descargar reporte de comparación (CSV)</a></p>
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
