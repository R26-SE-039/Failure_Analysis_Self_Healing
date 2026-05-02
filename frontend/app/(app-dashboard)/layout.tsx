import Sidebar from "@/components/sidebar";
import Topbar from "@/components/topbar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="flex min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <Sidebar />

      <section className="flex-1">
        <Topbar />
        <div className="p-6">{children}</div>
      </section>
    </main>
  );
}