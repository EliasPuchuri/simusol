import { useEffect, useMemo, useState } from "react";

import { api, type Matches } from "../api";
import { friendlyError, plural } from "../format";
import { ClassificationPanel } from "./ClassificationPanel";
import { Viewer3D } from "./Viewer3D";

type Kind = "both" | "previous" | "current";
type Row = { kind: Kind; name: string; previous?: string; current?: string };
const LABEL: Record<Kind, string> = { both: "En ambos", previous: "Solo en el anterior", current: "Solo en el actual" };

export function Results({ previousId, currentId, reviewer, onReviewerChange }: { previousId: string | null; currentId: string | null; reviewer: string; onReviewerChange: (name: string) => void }) {
  const [matches, setMatches] = useState<Matches | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Kind | "all">("all");
  const [query, setQuery] = useState("");
  const [viewing, setViewing] = useState<string | null>(null);

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

  const rows = useMemo<Row[]>(() => {
    if (!matches) return [];
    return [
      ...matches.pairs.map((p): Row => ({ kind: "both", name: p.key, previous: p.previous.filename, current: p.current.filename })),
      ...matches.only_previous.map((e): Row => ({ kind: "previous", name: e.key, previous: e.filename })),
      ...matches.only_current.map((e): Row => ({ kind: "current", name: e.key, current: e.filename })),
    ].sort((a, b) => a.name.localeCompare(b.name));
  }, [matches]);

  const counts = { both: 0, previous: 0, current: 0 };
  rows.forEach((r) => counts[r.kind]++);
  const q = query.trim().toLowerCase();
  const visible = rows.filter(
    (r) => (filter === "all" || r.kind === filter) &&
      (!q || [r.name, r.previous, r.current].some((v) => v?.toLowerCase().includes(q))),
  );

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
          <ul className="stats">
            <li className="stat stat-both">
              <strong>{counts.both}</strong>{" "}
              <span>{counts.both === 1 ? "sólido está en ambos periodos" : "sólidos están en ambos periodos"}</span>
            </li>
            <li className="stat stat-previous">
              <strong>{counts.previous}</strong>{" "}
              <span>{counts.previous === 1 ? "sólido solo está en el periodo anterior" : "sólidos solo están en el periodo anterior"}</span>
            </li>
            <li className="stat stat-current">
              <strong>{counts.current}</strong>{" "}
              <span>{counts.current === 1 ? "sólido solo está en el periodo actual" : "sólidos solo están en el periodo actual"}</span>
            </li>
          </ul>
          <p className="note">
            Los sólidos se emparejan por nombre (se ignora «pt» al final). Si un sólido fue renombrado, aparecerá a la vez como «solo en el anterior» y «solo en el actual»: conviene revisarlo manualmente.
          </p>
          {matches.incidents.map((i, n) => (
            <p key={n} role="alert" className="alert alert-warn">
              {((i.detail.filenames as string[]) ?? []).join(" y ")} corresponderían al mismo sólido en el periodo {i.detail.period === "previous" ? "anterior" : "actual"}; no se compararon.
            </p>
          ))}

          {previousId && currentId && <ClassificationPanel previousId={previousId} currentId={currentId} onView={setViewing} reviewer={reviewer} onReviewerChange={onReviewerChange} />}

          <div className="toolbar">
            <div className="tabs" role="group" aria-label="Filtrar por situación">
              {([["all", `Todos (${rows.length})`], ["both", `En ambos (${counts.both})`],
                ["previous", `Solo en el anterior (${counts.previous})`], ["current", `Solo en el actual (${counts.current})`]] as const).map(([k, text]) => (
                <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>{text}</button>
              ))}
            </div>
            <label className="search">
              <span className="sr-only">Buscar sólido</span>
              <input type="search" aria-label="Buscar sólido" placeholder="Buscar sólido…" value={query} onChange={(e) => setQuery(e.target.value)} />
            </label>
          </div>

          <div className="table-wrap">
            <table>
              <thead><tr><th>Sólido</th><th>Periodo anterior</th><th>Periodo actual</th><th>Situación</th><th>Vista 3D</th></tr></thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={`${r.kind}-${r.name}`} className={viewing === r.name ? "row-selected" : undefined}>
                    <td>{r.name}</td>
                    <td>{r.previous ?? <span className="muted">No existe</span>}</td>
                    <td>{r.current ?? <span className="muted">No existe</span>}</td>
                    <td><span className={`pill pill-${r.kind}`}>{LABEL[r.kind]}</span></td>
                    <td><button type="button" aria-label={`Ver en 3D: ${r.name}`} aria-pressed={viewing === r.name} onClick={() => setViewing(r.name)}>Ver en 3D</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {visible.length === 0 && <p className="empty">Ningún sólido coincide con lo buscado.</p>}
          </div>
          {viewing && previousId && currentId && (
            <Viewer3D previousId={previousId} currentId={currentId} solidKey={viewing} onClose={() => setViewing(null)} />
          )}
          <p className="note">{plural(visible.length, "sólido mostrado", "sólidos mostrados")} de {rows.length}.</p>
        </>
      )}
    </section>
  );
}
