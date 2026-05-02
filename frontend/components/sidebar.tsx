import Link from "next/link";
import { LayoutDashboard, Siren, Wrench, BarChart3, Bell, FlaskConical, BrainCircuit } from "lucide-react";

const menuItems = [
  { name: "Dashboard",     href: "/",             icon: LayoutDashboard },
  { name: "Submit Failure",href: "/submit",        icon: FlaskConical },
  { name: "Failures",      href: "/failures",      icon: Siren },
  { name: "Healing",       href: "/healing",       icon: Wrench },
  { name: "Analytics",     href: "/analytics",     icon: BarChart3 },
  { name: "Notifications", href: "/notifications", icon: Bell },
  { name: "Model Training",href: "/model",         icon: BrainCircuit },
];

export default function Sidebar() {
  return (
    <aside className="w-64 min-h-screen border-r border-[var(--border)] bg-[var(--card)] p-5">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">NEXTGEN QA</h1>
        <p className="text-sm text-[var(--muted)] mt-1">
          Failure Analysis System
        </p>
      </div>

      <nav className="space-y-2">
        {menuItems.map((item) => {
          const Icon = item.icon;

          return (
            <Link
              key={item.name}
              href={item.href}
              className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm transition hover:bg-[var(--card-2)]"
            >
              <Icon size={18} />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}