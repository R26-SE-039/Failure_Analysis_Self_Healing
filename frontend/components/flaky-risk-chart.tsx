"use client";
import { useState, useEffect } from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

type RiskEntry = { name: string; value: number; color: string };

interface Props {
  data?: RiskEntry[];
}

const PLACEHOLDER: RiskEntry[] = [
  { name: "High",   value: 0, color: "#ef4444" },
  { name: "Medium", value: 0, color: "#f59e0b" },
  { name: "Low",    value: 0, color: "#22c55e" },
];

export default function FlakyRiskChart({ data }: Props) {
  const [mounted, setMounted] = useState(false);
  const chartData = data && data.length > 0 ? data : PLACEHOLDER;
  const isEmpty   = chartData.every((d) => d.value === 0);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="h-[280px] w-full">
      {!mounted ? (
        <div className="flex h-full items-center justify-center animate-pulse bg-slate-50/50 rounded-2xl border border-slate-100/50" />
      ) : isEmpty ? (
        <div className="flex h-full items-center justify-center text-sm text-[var(--muted)]">
          No flaky tests detected yet.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              outerRadius={90}
              innerRadius={40}
              paddingAngle={3}
              label={({ name, percent }: any) =>
                `${name || ""} ${((percent || 0) * 100).toFixed(0)}%`
              }
            >
              {chartData.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: any, name: any) => [`${value} tests`, name]}
            />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}