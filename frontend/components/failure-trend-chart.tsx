"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";

const data = [
  { name: "Mon", failures: 18 },
  { name: "Tue", failures: 25 },
  { name: "Wed", failures: 14 },
  { name: "Thu", failures: 30 },
  { name: "Fri", failures: 22 },
  { name: "Sat", failures: 12 },
  { name: "Sun", failures: 16 },
];

export default function FailureTrendChart() {
  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="name" stroke="#9ca3af" />
          <YAxis stroke="#9ca3af" />
          <Tooltip />
          <Line type="monotone" dataKey="failures" stroke="#60a5fa" strokeWidth={3} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}