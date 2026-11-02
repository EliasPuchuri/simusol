import { useState } from "react";

import { api } from "../api";

type Props = {
  title: string;
  rowKey: string;
  /** Text of the state the system gave, e.g. "Variable". Absent for a general observation. */
  systemLabel?: string;
  reviewer: string;
  onReviewerChange: (name: string) => void;
  previousId: string;
  currentId: string;
  onSaved: () => void | Promise<void>;
};

const STATES: [string, string][] = [["SIN CAMBIOS", "Sin cambios"], ["VARIABLE", "Variable"], ["NUEVO", "Nuevo"], ["ELIMINADO", "Eliminado"]];
const TYPES: [string, string][] = [["TABULAR", "Tabular"], ["TABULAR CURVO", "Tabular curvo"], ["GLOBULAR", "Globular"]];

type Parsed = number | null | "invalid";

const parse = (text: string): Parsed => {
  if (!text.trim()) return null;
  const n = Number(text.trim().replace(",", "."));
  return Number.isFinite(n) ? n : "invalid";
};

export function ReviewForm({ title, rowKey, systemLabel, reviewer, onReviewerChange, previousId, currentId, onSaved }: Props) {
  const general = rowKey === "*";
  const [name, setName] = useState(reviewer);
  const [agrees, setAgrees] = useState(true);
  const [state, setState] = useState("");
  const [type, setType] = useState("");
  const [azimuth, setAzimuth] = useState("");
  const [dip, setDip] = useState("");
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const az: Parsed = parse(azimuth);
  const dp: Parsed = parse(dip);
  const hasInfo = Boolean(state || type || (az !== null && az !== "invalid") || (dp !== null && dp !== "invalid") || comment.trim());
  const valid = name.trim() !== "" && az !== "invalid" && dp !== "invalid" && (general ? comment.trim() !== "" : agrees || hasInfo);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setSaving(true);
    setMessage(null);
    onReviewerChange(name.trim());
    try {
      await api.putReview({
        previous: previousId, current: currentId, key: rowKey, reviewer: name.trim(), agrees: general ? true : agrees,
        expected_state: !general && !agrees && state ? state : null, expected_body_type: !general && !agrees && type ? type : null,
        expected_azimuth: !general && !agrees ? az : null, expected_dip: !general && !agrees ? dp : null, comment: comment.trim(),
      });
      setMessage({ ok: true, text: "Opinión guardada" });
      await onSaved();
    } catch {
      setMessage({ ok: false, text: "No se pudo guardar la opinión. Inténtalo de nuevo: lo que escribiste sigue aquí." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form aria-label={title} className="review" onSubmit={submit}>
      <strong>{title}</strong>
      {!reviewer && (
        <label className="field"><span>Tu nombre</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Para firmar tu opinión" /></label>
      )}
      {!general && (
        <fieldset className="choice">
          <legend>¿Estás de acuerdo con el resultado{systemLabel ? <> «{systemLabel}»</> : ""}?</legend>
          <label><input type="radio" name={`agree-${rowKey}`} checked={agrees} onChange={() => setAgrees(true)} /> De acuerdo</label>
          <label><input type="radio" name={`agree-${rowKey}`} checked={!agrees} onChange={() => setAgrees(false)} /> No estoy de acuerdo</label>
        </fieldset>
      )}
      {!general && !agrees && (
        <div className="review-fields">
          <label className="field"><span>Estado que esperabas</span>
            <select value={state} onChange={(e) => setState(e.target.value)}><option value="">—</option>{STATES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
          <label className="field"><span>Tipo de cuerpo que esperabas</span>
            <select value={type} onChange={(e) => setType(e.target.value)}><option value="">—</option>{TYPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></label>
          <label className="field"><span>Azimuth esperado</span><input inputMode="decimal" value={azimuth} onChange={(e) => setAzimuth(e.target.value)} placeholder="0 a 360" /></label>
          <label className="field"><span>Dip esperado</span><input inputMode="decimal" value={dip} onChange={(e) => setDip(e.target.value)} placeholder="0 a 90" /></label>
        </div>
      )}
      <label className="field"><span>Comentario</span>
        <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} placeholder={general ? "Escribe tu observación" : "Qué viste o qué esperabas (opcional si estás de acuerdo)"} /></label>
      <div className="review-actions">
        <button type="submit" className="primary" disabled={!valid || saving}>Guardar opinión</button>
        {message && <span role={message.ok ? "status" : "alert"} className={message.ok ? "ok-line" : "error"}>{message.text}</span>}
      </div>
    </form>
  );
}
