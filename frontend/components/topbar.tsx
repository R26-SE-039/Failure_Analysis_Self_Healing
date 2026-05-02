export default function Topbar() {
  return (
    <div className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--card)] px-6 py-4">
      <div>
        <h2 className="text-xl font-semibold">Failure Analysis Dashboard</h2>
        <p className="text-sm text-[var(--muted)]">
          Monitor failures, healing actions, and flaky tests
        </p>
      </div>

      <div className="rounded-full bg-[var(--card-2)] px-4 py-2 text-sm">
        QA Engineer
      </div>
    </div>
  );
}