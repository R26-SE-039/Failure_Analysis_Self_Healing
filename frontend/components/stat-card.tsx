type StatCardProps = {
  title: string;
  value: string;
  change: string;
};

export default function StatCard({ title, value, change }: StatCardProps) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-sm">
      <p className="text-sm text-[var(--muted)]">{title}</p>
      <h3 className="mt-2 text-3xl font-bold">{value}</h3>
      <p className="mt-2 text-sm text-[var(--accent)]">{change} from last run</p>
    </div>
  );
}