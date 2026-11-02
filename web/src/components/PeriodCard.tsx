import { useCallback, useEffect, useState } from "react";

import { api, type Dataset, type DatasetDetail } from "../api";
import { formatBytes, friendlyError, plural } from "../format";
import { DropZone } from "./DropZone";
import { OrientationReference } from "./OrientationReference";
import { CharacterizationPanel } from "./CharacterizationPanel";
import { QualityPanel } from "./QualityPanel";

type Props = {
  title: string;
  folderAria: string;
  modelName: string;
  saved: Dataset[];
  onReady: (id: string | null) => void;
  onChanged: () => void | Promise<void>;
};

type Failure = { filename: string; message: string };

export function PeriodCard({ title, folderAria, modelName, saved, onReady, onChanged }: Props) {
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DatasetDetail | null>(null);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<"annual" | "monthly">("annual");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [skipped, setSkipped] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (id: string) => {
    setDetail(await api.getDataset(id));
  }, []);

  useEffect(() => {
    if (datasetId) load(datasetId).catch((e) => setError((e as Error).message));
    else setDetail(null);
  }, [datasetId, load]);

  async function handleFiles(all: File[], folder: string) {
    setError(null);
    const objs = all.filter((f) => f.name.toLowerCase().endsWith(".obj"));
    setSkipped(all.length - objs.length);
    if (objs.length === 0) {
      setError("No se encontraron archivos .obj en lo que elegiste.");
      return;
    }
    try {
      let id = datasetId;
      if (!id) {
        const created = await api.createDataset({
          name: modelName || "Modelo", period_label: label.trim() || folder || title,
          period_kind: kind, is_demo: false, spatial_reference: null, units: null,
        });
        id = created.id;
        setDatasetId(id);
      }
      const failed: Failure[] = [];
      for (const [index, file] of objs.entries()) {
        setProgress({ done: index, total: objs.length });
        try {
          await api.uploadFile(id, file);
        } catch (e) {
          failed.push({ filename: file.name, message: friendlyError((e as Error).message) });
        }
      }
      setFailures(failed);
      await load(id);
      await onChanged();
    } catch (e) {
      setError(friendlyError((e as Error).message));
    } finally {
      setProgress(null);
    }
  }

  async function confirm() {
    if (!datasetId) return;
    try {
      await api.finalize(datasetId);
      await load(datasetId);
      await onChanged();
      onReady(datasetId);
    } catch (e) {
      setError(friendlyError((e as Error).message));
    }
  }

  async function useSaved(id: string) {
    if (!id) return;
    setError(null);
    setFailures([]);
    setSkipped(0);
    setDatasetId(id);
    try {
      const d = await api.getDataset(id);
      setDetail(d);
      if (d.state === "closed") onReady(id);
    } catch (e) {
      setError(friendlyError((e as Error).message));
    }
  }

  function reset() {
    setDatasetId(null);
    setDetail(null);
    setLabel("");
    setFailures([]);
    setSkipped(0);
    setError(null);
    onReady(null);
  }

  const total = detail?.files.length ?? 0;
  const done = detail?.state === "closed";
  const uploading = progress !== null;

  return (
    <section className={`card${done ? " card-done" : ""}`} aria-labelledby={`${folderAria}-t`}>
      <h2 id={`${folderAria}-t`}>{title}</h2>

      {!datasetId && !uploading && (
        <>
          <label className="field">
            <span>Nombre del periodo <em>(opcional)</em></span>
            <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Ej.: 2025 o Enero 2026" />
          </label>
          <fieldset className="segmented">
            <legend className="sr-only">Tipo de periodo</legend>
            {(["annual", "monthly"] as const).map((k) => (
              <label key={k} className={kind === k ? "on" : ""}>
                <input type="radio" name={`${folderAria}-kind`} checked={kind === k} onChange={() => setKind(k)} />
                {k === "annual" ? "Anual" : "Mensual"}
              </label>
            ))}
          </fieldset>
        </>
      )}

      {(!datasetId || (detail?.state === "open")) && (
        <DropZone folderLabelText={folderAria} disabled={uploading} compact={Boolean(datasetId)} onFiles={handleFiles} />
      )}

      {!datasetId && !uploading && saved.length > 0 && (
        <label className="field saved">
          <span>Usar un periodo ya guardado</span>
          <select value="" onChange={(e) => useSaved(e.target.value)}>
            <option value="">Seleccione…</option>
            {saved.map((d) => (
              <option key={d.id} value={d.id}>
                {d.period_label} · {plural(d.file_count ?? 0, "sólido", "sólidos")}
                {d.state === "open" ? " (sin terminar)" : ""}
              </option>
            ))}
          </select>
        </label>
      )}

      {uploading && (
        <div role="status" aria-live="polite" className="progress">
          <progress max={progress.total} value={progress.done} />
          <span>Subiendo {Math.min(progress.done + 1, progress.total)} de {progress.total}…</span>
        </div>
      )}

      {detail && !uploading && (
        <div className="summary">
          {done ? (
            <p className="ok"><strong>Listo</strong> <span>{detail.period_label} · {plural(total, "sólido", "sólidos")}</span></p>
          ) : (
            <p className="count"><strong>{plural(total, "sólido cargado", "sólidos cargados")}</strong> en «{detail.period_label}»</p>
          )}
        </div>
      )}

      {skipped > 0 && (
        <p className="note">Se ignoró {plural(skipped, "archivo que no es .obj", "archivos que no son .obj")}.</p>
      )}

      {failures.length > 0 && (
        <div role="alert" className="alert alert-error">
          <strong>{plural(failures.length, "archivo no se pudo usar", "archivos no se pudieron usar")}:</strong>
          <ul>{failures.map((f) => <li key={f.filename}><b>{f.filename}</b>: {f.message}</li>)}</ul>
        </div>
      )}

      {detail?.incidents.map((i, n) => {
        const names = (i.detail.filenames as string[] | undefined) ?? [];
        return (
          <p key={n} role="alert" className="alert alert-warn">
            {names.join(" y ")} corresponderían al mismo sólido. Ninguno se comparará hasta que quede uno solo.
          </p>
        );
      })}

      {error && <p role="alert" className="alert alert-error">{error}</p>}

      {detail && total > 0 && (
        <details className="files">
          <summary>Ver archivos ({total})</summary>
          <ul>
            {detail.files.map((f) => (
              <li key={f.filename}>{f.filename} <small>{formatBytes(f.size_bytes)}</small></li>
            ))}
          </ul>
        </details>
      )}

      {detail?.state === "open" && total > 0 && !uploading && (
        <div className="confirm">
          <button type="button" className="primary big" onClick={confirm}>Está completo, continuar</button>
          <p className="note">Revisa que no falte ningún archivo. Después no se podrá modificar este periodo; si hay que corregirlo, se crea una nueva versión.</p>
        </div>
      )}

      {datasetId && detail && total > 0 && !uploading && <QualityPanel datasetId={datasetId} refreshKey={total} />}

      {datasetId && detail && total > 0 && !uploading && (
        <CharacterizationPanel datasetId={datasetId} refreshKey={total + (detail.orientation_reference_count ?? 0)} />
      )}

      {datasetId && detail && !uploading && (
        <OrientationReference datasetId={datasetId} periodTitle={title} storedCount={detail.orientation_reference_count ?? 0}
          onSaved={() => load(datasetId)} />
      )}

      {datasetId && !uploading && (
        <button type="button" className="link change" onClick={reset}>{done ? "Cambiar periodo" : "Empezar de nuevo"}</button>
      )}
    </section>
  );
}
