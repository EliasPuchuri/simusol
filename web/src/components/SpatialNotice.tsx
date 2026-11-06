import type { SpatialCheck } from "../api";

const shown = (v: string | null | undefined) => v || "sin declarar";

/** Whether the two periods can be compared coordinate by coordinate (RF-60). Says nothing when everything agrees. */
export function SpatialNotice({ spatial }: { spatial: SpatialCheck | undefined }) {
  if (!spatial || spatial.status === "compatible") return null;
  const { previous, current } = spatial.declared;
  if (spatial.status === "mismatch")
    return (
      <p role="alert" className="alert alert-error">
        Los dos periodos declaran sistemas distintos (referencia: «{shown(previous.spatial_reference)}» y «{shown(current.spatial_reference)}»;
        unidades: «{shown(previous.units)}» y «{shown(current.units)}»). Sus coordenadas no se pueden comparar tal cual: no confíes en los resultados hasta aclararlo.
      </p>
    );
  if (spatial.status === "extent_disjoint")
    return (
      <p role="alert" className="alert alert-error">
        Las zonas que cubren los dos periodos no se superponen en Este ni Norte. Revisa que ambos estén en el mismo sistema de coordenadas (UTM, en metros) y que sean del mismo yacimiento.
      </p>
    );
  return (
    <p className="note spatial-note">
      No se declaró la referencia espacial ni las unidades de los periodos: se asume el mismo sistema UTM en metros.
      {spatial.extent_checked ? " Las zonas de ambos periodos sí coinciden." : ""} Puedes declararlas en «Ajustes» antes de cargar un periodo.
    </p>
  );
}
