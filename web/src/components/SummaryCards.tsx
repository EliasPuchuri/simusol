import { percentOf } from "../dashboard";

type Counts = { sin: number; variable: number; nuevo: number; eliminado: number };

const CARDS = [
  { key: "sin", label: "Sin cambios", icon: "✓", tone: "ok" },
  { key: "variable", label: "Variables", icon: "↻", tone: "var" },
  { key: "nuevo", label: "Nuevos", icon: "+", tone: "new" },
  { key: "eliminado", label: "Eliminados", icon: "✕", tone: "del" },
] as const;

export function SummaryCards({ counts }: { counts: Counts }) {
  const base = counts.sin + counts.variable + counts.nuevo + counts.eliminado;
  return (
    <section className="dash-card" aria-label="Resumen de resultados">
      <h4>Resumen de resultados</h4>
      <ul className="cards">
        {CARDS.map((c) => (
          <li key={c.key} className={`summary-card tone-${c.tone}`}>
            <span className="summary-icon" aria-hidden="true">{c.icon}</span>
            <span className="summary-label">{c.label}</span>
            <strong>{counts[c.key]}</strong>
            <span className="summary-pct">{percentOf(counts[c.key], base)}</span>
          </li>
        ))}
      </ul>
      <p className="note">Porcentajes sobre {base} {base === 1 ? "sólido" : "sólidos"} con estado.</p>
    </section>
  );
}
