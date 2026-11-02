export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Name of the folder the user picked, when the browser exposes it. */
export function folderLabel(files: File[]): string {
  const rel = (files[0] as (File & { webkitRelativePath?: string }) | undefined)?.webkitRelativePath;
  return rel && rel.includes("/") ? rel.split("/")[0] : "";
}

export function friendlyError(message: string): string {
  if (message.includes("not a valid OBJ")) return "El archivo está vacío o no tiene geometría válida.";
  if (message.includes("only .obj")) return "No es un archivo .obj.";
  if (message.includes("already exists")) return "Ya se había cargado un archivo con ese nombre.";
  if (message.includes("exceeds")) return "Supera el tamaño máximo permitido.";
  if (message.includes("closed")) return "Este periodo ya está cerrado y no admite más archivos.";
  return message;
}

type EntryLike = {
  isFile: boolean;
  isDirectory: boolean;
  file?: (ok: (f: File) => void, fail: (e: unknown) => void) => void;
  createReader?: () => { readEntries: (ok: (e: EntryLike[]) => void, fail: (e: unknown) => void) => void };
};

async function readFolder(entry: EntryLike): Promise<File[]> {
  const reader = entry.createReader!();
  const files: File[] = [];
  for (;;) {
    const batch = await new Promise<EntryLike[]>((ok, fail) => reader.readEntries(ok, fail));
    if (batch.length === 0) return files;
    for (const child of batch) {
      if (child.isFile) files.push(await new Promise<File>((ok, fail) => child.file!(ok, fail)));
    }
  }
}

/** Files (and the folder name) from a drag-and-drop, supporting dropped folders. */
export async function filesFromDrop(data: DataTransfer): Promise<{ files: File[]; folder: string }> {
  // Entries must be captured synchronously, before any await.
  const entries = Array.from(data.items ?? [])
    .map((item) => item.webkitGetAsEntry?.() as unknown as EntryLike | null | undefined)
    .filter((e): e is EntryLike => Boolean(e));
  if (entries.length === 0) return { files: Array.from(data.files), folder: "" };

  const files: File[] = [];
  let folder = "";
  for (const entry of entries) {
    if (entry.isDirectory) {
      folder ||= (entry as EntryLike & { name?: string }).name ?? "";
      files.push(...(await readFolder(entry)));
    } else if (entry.isFile) {
      files.push(await new Promise<File>((ok, fail) => entry.file!(ok, fail)));
    }
  }
  return { files, folder };
}

type IssueLike = { code: string; line?: number | null; column?: string | null; value?: string | null };

/** Plain-Spanish description of a validation issue of the orientation table. */
export function describeIssue(issue: IssueLike): string {
  const where = issue.line ? `Línea ${issue.line}: ` : "";
  const { column, value } = issue;
  switch (issue.code) {
    case "empty_file": return "El archivo está vacío.";
    case "no_rows": return "No hay filas para guardar. Rellena la plantilla y borra las filas de ejemplo.";
    case "too_many_rows": return "Hay demasiadas filas (el máximo es 5000).";
    case "missing_column": return `Falta la columna «${column}».`;
    case "unknown_column": return `Se ignoró la columna «${column}», que no forma parte de la plantilla.`;
    case "not_obj": return `${where}«${value ?? ""}» no es un nombre de archivo .obj.`;
    case "bad_type": return `${where}el tipo «${value}» no es válido. Usa planar, axial o no_interpretable.`;
    case "required": return `${where}falta un valor en ${column}.`;
    case "not_a_number": return `${where}«${value}» no es un número (${column}).`;
    case "azimuth_range": return `${where}el azimuth ${value} debe estar entre 0 y 360.`;
    case "dip_range": return `${where}el dip ${value} debe estar entre 0 y 90.`;
    case "must_be_empty": return `${where}con tipo no_interpretable, ${column} debe quedar vacío.`;
    case "duplicate_file": return `${where}el sólido «${value}» aparece más de una vez.`;
    case "not_in_dataset": return `${where}«${value}» no está en los archivos de este periodo.`;
    default: return `${where}${issue.code}`;
  }
}

type QcFields = Partial<{
  open_edges: number | null;
  non_manifold_edges: number | null;
  duplicate_vertices: number | null;
  duplicate_faces: number | null;
  degenerate_faces: number | null;
  components: { value: number | null };
  self_intersections: { value: number | null };
}>;

/** Plain-Spanish description of one quality finding of a mesh. */
export function describeProblem(code: string, r: QcFields): string {
  const n = (v: number | null | undefined) => v ?? 0;
  switch (code) {
    case "not_watertight": return "La superficie no está cerrada.";
    case "inconsistent_winding": return "El sentido de las caras no es consistente.";
    case "inverted_orientation": return "La orientación global está invertida: el volumen firmado sale negativo.";
    case "open_edges": return n(r.open_edges) === 1 ? "Tiene 1 borde abierto (hueco en la superficie)." : `Tiene ${n(r.open_edges)} bordes abiertos (huecos en la superficie).`;
    case "non_manifold_edges": return `Tiene ${plural(n(r.non_manifold_edges), "arista compartida", "aristas compartidas")} por más de dos caras.`;
    case "duplicate_vertices": return `Tiene ${plural(n(r.duplicate_vertices), "vértice repetido", "vértices repetidos")}.`;
    case "duplicate_faces": return `Tiene ${plural(n(r.duplicate_faces), "cara repetida", "caras repetidas")}.`;
    case "degenerate_faces": return `Tiene ${plural(n(r.degenerate_faces), "cara sin área", "caras sin área")}.`;
    case "multiple_components": return `Está formado por ${n(r.components?.value)} partes separadas.`;
    case "self_intersections": {
      const k = n(r.self_intersections?.value);
      return k === 1 ? "1 cara se cruza con otra (autointersección)." : `${k} caras se cruzan entre sí (autointersecciones).`;
    }
    default: return code;
  }
}

export function describeQcError(error: string | null): string {
  if (!error) return "No se pudo revisar este archivo.";
  if (error.includes("timeout")) return "La revisión tardó demasiado y se canceló.";
  if (error.includes("process ended")) return "Este archivo hizo fallar el programa de revisión.";
  return `No se pudo leer el archivo: ${error}`;
}

const deg = (v: number) => `${v.toLocaleString("es-PE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}°`;

export function bodyTypeLabel(type: string | null | undefined): string {
  if (type === "TABULAR") return "Tabular";
  if (type === "TABULAR CURVO") return "Tabular curvo";
  if (type === "GLOBULAR") return "Globular";
  return "—";
}

type OrientationLike = { type: string; azimuth: number | null; dip: number | null; note: string | null; reason: string | null };

export function describeOrientation(o: OrientationLike | null | undefined): string {
  if (!o) return "—";
  if (o.reason === "horizontal_plane" || o.note === "horizontal_plane") return "Plano horizontal: no tiene azimuth.";
  if (o.type === "no_interpretable") {
    if (o.reason === "similar_eigenvalues") return "No interpretable: los ejes del cuerpo son muy parecidos y no hay una dirección dominante.";
    if (o.reason === "horizontal_plane") return "Plano horizontal: no tiene azimuth.";
    if (o.reason === "analysis_failed") return "No se pudo calcular.";
    return "No interpretable.";
  }
  if (o.azimuth == null || o.dip == null) return "No interpretable.";
  if (o.type === "axial") return `Eje: Trend ${deg(o.azimuth)} · Plunge ${deg(o.dip)} (equivalente cada 180°)`;
  const base = `Azimuth ${deg(o.azimuth)} · Dip ${deg(o.dip)}`;
  return o.note === "vertical_plane_direction_ambiguous" ? `${base} (plano vertical: el sentido del buzamiento es ambiguo)` : base;
}

type ReferenceLike = {
  method: string;
  azimuth: number | null;
  dip: number | null;
  comparison:
    | { comparable: true; delta_azimuth_deg: number | null; delta_dip_deg: number | null }
    | { comparable: false; reason: string };
};

export function describeReference(ref: ReferenceLike | null | undefined): string {
  if (!ref) return "—";
  if (!ref.comparison.comparable) {
    const why: Record<string, string> = {
      different_orientation_type: "tipos de orientación distintos",
      not_interpretable: "la orientación calculada no es interpretable",
      not_characterized: "todavía no se calculó la orientación",
    };
    return `No comparable: ${why[ref.comparison.reason] ?? ref.comparison.reason}.`;
  }
  const { delta_azimuth_deg: da, delta_dip_deg: dd } = ref.comparison;
  const refText = `${ref.method}: ${ref.azimuth == null ? "—" : deg(ref.azimuth)} / ${ref.dip == null ? "—" : deg(ref.dip)}`;
  return `${refText} → diferencia ${da == null ? "—" : deg(da)} / ${dd == null ? "—" : deg(dd)}`;
}

type RuleLike = { rule: string; observed: number | string | null; op: string; threshold: number | string | null; applicable: boolean; group?: string; passed?: boolean };
const RULES: Record<string, [string, "pct" | "m" | "deg"]> = {
  iou: ["Coincidencia (IoU)", "pct"], delta_volumen: ["Variación de volumen", "pct"], agregado: ["Volumen agregado", "pct"],
  removido: ["Volumen removido", "pct"], p95: ["Distancia entre superficies (P95)", "m"], centroide: ["Desplazamiento del centro", "m"],
  orientacion: ["Cambio de orientación", "deg"], delta_azimuth: ["Cambio de azimuth", "deg"], delta_dip: ["Cambio de dip", "deg"],
  cambio_local: ["Cambio local de curvatura", "deg"],
};
const OPS: Record<string, string> = { ">=": "mínimo", "<=": "máximo", "<": "menor que", "==": "debe ser" };

export function describeRule(c: RuleLike): string {
  const [label, unit] = RULES[c.rule] ?? [c.rule, "pct"];
  if (!c.applicable) return `${label}: no aplica a este par`;
  const fmt = (v: number | string | null) => {
    if (v == null) return "—";
    if (typeof v === "string") return v;
    return unit === "pct" ? `${v.toFixed(1)} %` : unit === "m" ? `${v.toFixed(2)} m` : `${v.toFixed(1)}°`;
  };
  return `${label}: ${fmt(c.observed)} (${OPS[c.op] ?? c.op} ${fmt(c.threshold)})`;
}

export function describeWarning(code: string): string {
  const [kind, role] = code.split(":");
  const who = role === "previous" ? "El periodo anterior" : role === "current" ? "El periodo actual" : null;
  if (kind === "inverted_orientation_normalized" && who) return `${who} tiene la orientación invertida: su volumen se calculó con una copia corregida (provisional).`;
  if (kind === "self_intersections" && who) return `${who} tiene caras que se cruzan: el volumen y la intersección pueden tener error.`;
  return code;
}

export function describeRowFailure(description: string): string {
  if (description.includes("timeout")) return "No se pudo clasificar: el cálculo de este par tardó demasiado y se canceló.";
  if (description.includes("process ended")) return "No se pudo clasificar: uno de los archivos hizo fallar el programa de cálculo.";
  return description;
}
