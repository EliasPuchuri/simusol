import { useRef, useState } from "react";

import { api, ApiError, type Issue, type ReferenceFailure, type ReferenceResult } from "../api";
import { describeIssue, friendlyError, plural } from "../format";

type Props = { datasetId: string; storedCount: number; periodTitle: string; onSaved: () => void | Promise<void> };

export function OrientationReference({ datasetId, storedCount, periodTitle, onSaved }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ReferenceResult | null>(null);
  const [failure, setFailure] = useState<ReferenceFailure | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setResult(null);
    setFailure(null);
    setError(null);
    try {
      setResult(await api.uploadOrientationReference(datasetId, file));
      await onSaved();
    } catch (e) {
      const detail = e instanceof ApiError ? (e.detail as ReferenceFailure | undefined) : undefined;
      if (detail && Array.isArray(detail.errors)) setFailure(detail);
      else setError(friendlyError((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  const list = (issues: Issue[]) => <ul>{issues.map((i, n) => <li key={n}>{describeIssue(i)}</li>)}</ul>;

  return (
    <details className="reference">
      <summary>Valores de referencia de orientación <em>(opcional)</em></summary>
      <p>
        Si ya tienes el Azimuth y el Dip de cada sólido medidos en Studio RM o Leapfrog, súbelos aquí para contrastarlos
        después con el cálculo automático. Descarga la plantilla, rellénala en Excel y vuelve a subirla.
      </p>
      {storedCount > 0 && <p className="ok-line">Ya hay {plural(storedCount, "fila de referencia guardada", "filas de referencia guardadas")}. Si subes otra tabla, reemplaza a la anterior.</p>}
      <p className="actions">
        <a className="button" href={api.orientationTemplateUrl} download>Descargar plantilla (CSV)</a>
        <button type="button" disabled={busy} onClick={() => input.current?.click()}>
          {busy ? "Revisando…" : "Subir tabla completada"}
        </button>
      </p>
      <input ref={input} className="sr-only" type="file" accept=".csv,text/csv" tabIndex={-1}
        aria-label={`Tabla de orientación del ${periodTitle.toLowerCase()}`} onChange={upload} />

      {result && (
        <div role="status" className="alert alert-ok">
          <p>Se guardaron {plural(result.saved, "fila", "filas")} de referencia.</p>
          {result.ignored_examples > 0 && <p>Se ignoraron {plural(result.ignored_examples, "fila de ejemplo", "filas de ejemplo")}.</p>}
          {result.warnings.length > 0 && <><p>Avisos:</p>{list(result.warnings)}</>}
        </div>
      )}
      {failure && (
        <div role="alert" className="alert alert-error">
          <p><strong>No se guardó nada: corrige {plural(failure.errors.length, "problema", "problemas")} y vuelve a subir el archivo.</strong></p>
          {list(failure.errors)}
        </div>
      )}
      {error && <p role="alert" className="alert alert-error">{error}</p>}
    </details>
  );
}
