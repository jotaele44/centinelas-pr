export default function WaterDisruption() {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-6">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-foreground">Water Disruption Shadow Queue</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Shadow-mode evidence, candidates, delivery outbox, and provenance. Live alerts and production promotion remain disabled.
        </p>
      </div>
      <iframe
        src="/water-disruption/console"
        title="Water disruption shadow console"
        className="min-h-[70vh] w-full rounded-lg border bg-background"
      />
    </main>
  );
}
