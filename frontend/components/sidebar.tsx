"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Siren, Wrench, BarChart3, Send, FlaskConical, BrainCircuit } from "lucide-react";

const menuItems = [
  { name: "Dashboard",     href: "/",             icon: LayoutDashboard },
  { name: "Submit Failure",href: "/submit",        icon: FlaskConical },
  { name: "Failures",      href: "/failures",      icon: Siren },
  { name: "Healing",       href: "/healing",       icon: Wrench },
  { name: "Analytics",     href: "/analytics",     icon: BarChart3 },
  { name: "Alert Outbox",  href: "/notifications", icon: Send },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 min-h-screen border-r border-[var(--border)] bg-[var(--card)] p-6 flex flex-col justify-between shadow-sm">
      <div>
        <div className="mb-10 px-2 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
            <BrainCircuit size={22} />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
              NEXTGEN QA
            </h1>
            <p className="text-xs font-medium text-[var(--muted)]">
              Intelligent Pipeline
            </p>
          </div>
        </div>

        <nav className="space-y-1.5">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href));

            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition-all duration-200 transform ${
                  isActive
                    ? "bg-indigo-50 text-indigo-700 shadow-sm border border-indigo-100/50"
                    : "text-[var(--muted)] hover:bg-[var(--card-2)] hover:text-[var(--foreground)] hover:translate-x-1"
                }`}
              >
                <Icon size={18} className={`${isActive ? "text-indigo-600" : "text-[var(--muted)]"}`} />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="rounded-2xl bg-[var(--card-2)] p-4 border border-[var(--border)] shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 font-bold text-sm">
            QA
          </div>
          <div>
            <h4 className="text-sm font-bold text-[var(--foreground)]">Enterprise Client</h4>
            <p className="text-xs text-[var(--muted)] font-medium">Active Session</p>
          </div>
        </div>
      </div>
    </aside>
  );
}