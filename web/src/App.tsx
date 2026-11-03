import { useCallback, useEffect, useState } from "react";

import { api, type Dataset } from "./api";
import { PeriodCard } from "./components/PeriodCard";
import { Results } from "./components/Results";

export default function App() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [previousId, setPreviousId] = useState<string | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [modelName, setModelName] = useState("Modelo");
  const [reviewer, setReviewerState] = useState(() => localStorage.getItem("simusol.reviewer") ?? "");
  const setReviewer = (name: string) => {
    setReviewerState(name);
    localStorage.setItem("simusol.reviewer", name);
  };
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDatasets(await api.listDatasets());
      setError(null);
    } catch {
      setError("No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const available = (otherId: string | null) => datasets.filter((d) => d.id !== otherId && (d.file_count ?? 0) > 0);

  const labelOf = (id: string | null, fallback: string) => datasets.find((d) => d.id === id)?.period_label || fallback;

  const steps = [
    { label: "Periodo anterior", done: previousId !== null },
    { label: "Periodo actual", done: currentId !== null },
    { label: "Comparación", done: previousId !== null && currentId !== null },
  ];

  return (
    <main>
      <header>
        <h1>Compara dos periodos de sólidos</h1>
        <p className="lead">
          Carga la carpeta del periodo anterior y la del actual. La página te mostrará qué sólidos están en ambos y cuáles aparecen o desaparecen.
        </p>
        <ol className="steps" aria-label="Progreso">
          {steps.map((s, i) => (
            <li key={s.label} className={s.done ? "done" : ""}>
              <span className="num" aria-hidden="true">{s.done ? "✓" : i + 1}</span>
              {s.label}
              <span className="sr-only">{s.done ? " (listo)" : " (pendiente)"}</span>
            </li>
          ))}
        </ol>
        <details className="settings">
          <summary>Ajustes</summary>
          <label className="field">
            <span>Nombre del modelo</span>
            <input value={modelName} onChange={(e) => setModelName(e.target.value)} />
          </label>
          <label className="field">
            <span>Tu nombre (para firmar tus opiniones)</span>
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} />
          </label>
        </details>
      </header>

      {error && <p role="alert" className="alert alert-error">{error}</p>}

      <Results
        periods={(
          <>
            <h2>1. Carga de carpetas</h2>
            <div className="periods">
              <PeriodCard title="Periodo anterior" folderAria="Carpeta del periodo anterior" modelName={modelName}
                saved={available(currentId)} onReady={setPreviousId} onChanged={refresh} />
              <PeriodCard title="Periodo actual" folderAria="Carpeta del periodo actual" modelName={modelName}
                saved={available(previousId)} onReady={setCurrentId} onChanged={refresh} />
            </div>
          </>
        )}
        previousId={previousId} currentId={currentId} previousLabel={labelOf(previousId, "Anterior")} currentLabel={labelOf(currentId, "Actual")}
        reviewer={reviewer} onReviewerChange={setReviewer} />
    </main>
  );
}
