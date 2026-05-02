"use client";

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";

type TrendPoint = { name: string; failures: number };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export default function FailureTrendChart() {
  const [data, setData]       = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/dashboard/trend`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => {/* silently fall back to empty */})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="h-[280px] w-full animate-pulse rounded-xl bg-[var(--card-2)]" />
    );
  }

  const hasData = data.some((d) => d.failures > 0);

  if (!hasData) {
    return (
      <div className="flex h-[280px] w-full items-center justify-center text-sm text-[var(--muted)]">
        No failure trend data yet. Submit a failure to begin.
      </div>
    );
  }

  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="name" stroke="#9ca3af" tick={{ fontSize: 11 }} />
          <YAxis stroke="#9ca3af" tick={{ fontSize: 11 }} allowDecimals={false} />
          <Tooltip
            contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 }}
            labelStyle={{ color: "var(--foreground)" }}
          />
          <Line
            type="monotone"
            dataKey="failures"
            stroke="#60a5fa"
            strokeWidth={3}
            dot={{ r: 4, fill: "#60a5fa" }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}