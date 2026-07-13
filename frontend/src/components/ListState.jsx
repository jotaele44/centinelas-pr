import { Skeleton } from "@/components/ui/skeleton";

/**
 * Shared async-list state wrapper for the lifecycle pages.
 *
 * Renders one of three states — loading (skeletons), error, or empty — and
 * otherwise renders `children`. This replaces the ~14 hand-rolled inline
 * "Cargando… / No hay…" blocks and, critically, adds a distinct **error** state
 * so a failed data layer no longer looks identical to "no data".
 *
 * Accessibility: the loading state is announced via `role="status"` /
 * `aria-live`, and the error state via `role="alert"`.
 */
export default function ListState({
  loading,
  error,
  empty,
  loadingLabel = "Cargando…",
  emptyMessage = "No hay resultados con esos criterios.",
  errorMessage = "No se pudo cargar la información. Revisa la conexión con el almacén de datos e inténtalo de nuevo.",
  skeletonCount = 3,
  children,
}) {
  if (loading) {
    return (
      <div className="space-y-3" role="status" aria-live="polite" aria-busy="true">
        <span className="sr-only">{loadingLabel}</span>
        {Array.from({ length: skeletonCount }).map((_, index) => (
          <Skeleton key={index} className="h-24 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-sm text-foreground">
        {errorMessage}
      </p>
    );
  }

  if (empty) {
    return <p className="rounded-xl border p-6 text-muted-foreground">{emptyMessage}</p>;
  }

  return children;
}
