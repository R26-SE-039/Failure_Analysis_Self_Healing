"use client";

import { useState, useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

type Metrics = {
  model_name: string;
  accuracy: number;
  macro_f1: number;
  weighted_f1: number;
  macro_precision: number;
  macro_recall: number;
  train_samples: number;
  test_samples: number;
  classes: string[];
  per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  all_models: Record<string, number>;
};

type ServiceHealth = Record<string, { status: string; model?: string; error?: string }>;

export default function ModelPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [health, setHealth] = useState<ServiceHealth | null>(null);
  const [retraining, setRetraining] = useState(false);
  const [retrainMsg, setRetrainMsg] = useState<string | null>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(true);

  const fetchMetrics = async () => {
    setLoadingMetrics(true);
    try {
      const res = await fetch(`${API_BASE}/analyze/metrics`);
      if (res.ok) setMetrics(await res.json());
    } catch {
      /* metrics not ready */
    } finally {
      setLoadingMetrics(false);
    }
  };

  const fetchHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/analyze/health`);
      if (res.ok) setHealth(await res.json());
    } catch { /* ignore */ }
  };

  useEffect(() => {
    fetchMetrics();
    fetchHealth();
  }, []);

  // Poll retrain status
  useEffect(() => {
    if (!retraining) return;
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/analyze/retrain/status`);
        const data = await res.json();
        if (!data.running) {
          setRetraining(false);
          if (data.last_result === "success") {
            setRetrainMsg("✅ Retraining complete! Model updated successfully.");
            fetchMetrics();
          } else {
            setRetrainMsg(`⚠️ Retraining ended: ${data.last_result}`);
          }
          clearInterval(poll);
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(poll);
  }, [retraining]);

  const handleRetrain = async () => {
    setRetrainMsg(null);
    setRetraining(true);
    try {
      const res = await fetch(`${API_BASE}/analyze/retrain`, { method: "POST" });
      const data = await res.json();
      if (data.status === "running") {
        setRetrainMsg("⏳ Already retraining…");
        setRetraining(false);
      } else {
        setRetrainMsg("🔄 Retraining started in background…");
      }
    } catch (e) {
      setRetrainMsg("❌ Failed to trigger retraining. Is the ML service running?");
      setRetraining(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Model Training & Metrics</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Monitor ML classifier performance and trigger model retraining
        </p>
      </div>

      {/* ── Service Health ─────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Microservice Health</h3>
          <button
            onClick={fetchHealth}
            className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs transition hover:bg-[var(--card-2)]"
          >
            Refresh
          </button>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {health
            ? Object.entries(health).map(([name, info]) => (
                <div key={name} className="rounded-xl bg-[var(--card-2)] p-4">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${info.status === "ready" ? "bg-green-500" : "bg-red-500"}`} />
                    <p className="text-xs font-medium capitalize">{name}</p>
                  </div>
                  <p className={`mt-1 text-xs ${info.status === "ready" ? "text-green-400" : "text-red-400"}`}>
                    {info.status}
                  </p>
                  {info.model && <p className="text-xs text-[var(--muted)] mt-0.5">{info.model}</p>}
                  {info.error && <p className="text-xs text-red-400 mt-0.5 truncate">{info.error}</p>}
                </div>
              ))
            : Array(4).fill(0).map((_, i) => (
                <div key={i} className="rounded-xl bg-[var(--card-2)] p-4 animate-pulse h-16" />
              ))}
        </div>
      </div>

      {/* ── Retrain ───────────────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="font-semibold">Trigger Model Retraining</h3>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Retrain on <code className="bg-[var(--card-2)] px-1 py-0.5 rounded text-xs">final_training_dataset.csv</code> (45,850 records). Takes ~3–5 minutes.
          </p>
          {retrainMsg && (
            <p className="mt-2 text-sm text-[var(--accent)]">{retrainMsg}</p>
          )}
        </div>
        <button
          onClick={handleRetrain}
          disabled={retraining}
          className="flex shrink-0 items-center gap-2 rounded-xl bg-[var(--accent)] px-6 py-3 font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
        >
          {retraining ? (
            <>
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Training…
            </>
          ) : (
            "🔄 Retrain Model"
          )}
        </button>
      </div>

      {/* ── Metrics ───────────────────────────────────────────────────────────── */}
      {loadingMetrics ? (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 animate-pulse h-40" />
      ) : metrics ? (
        <div className="space-y-4">
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Accuracy",       value: `${(metrics.accuracy * 100).toFixed(2)}%`,    color: "text-green-400" },
              { label: "Macro F1",       value: `${(metrics.macro_f1 * 100).toFixed(2)}%`,    color: "text-blue-400"  },
              { label: "Macro Precision",value: `${(metrics.macro_precision * 100).toFixed(2)}%`, color: "text-yellow-400" },
              { label: "Macro Recall",   value: `${(metrics.macro_recall * 100).toFixed(2)}%`,   color: "text-purple-400" },
            ].map((m) => (
              <div key={m.label} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
                <p className="text-xs text-[var(--muted)]">{m.label}</p>
                <p className={`mt-1 text-3xl font-bold ${m.color}`}>{m.value}</p>
                <p className="mt-1 text-xs text-[var(--muted)]">{metrics.model_name}</p>
              </div>
            ))}
          </div>

          {/* Model comparison */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
            <h3 className="font-semibold">Model Comparison</h3>
            <div className="mt-4 space-y-3">
              {Object.entries(metrics.all_models).map(([name, acc]) => (
                <div key={name} className="flex items-center gap-4">
                  <span className="w-40 shrink-0 text-sm">{name}</span>
                  <div className="flex-1 rounded-full bg-[var(--card-2)] h-3 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-[var(--accent)] transition-all"
                      style={{ width: `${acc * 100}%` }}
                    />
                  </div>
                  <span className="w-16 text-right text-sm font-semibold">{(acc * 100).toFixed(2)}%</span>
                </div>
              ))}
            </div>
          </div>

          {/* Per-class metrics */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
            <h3 className="font-semibold">Per-Class Performance</h3>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--muted)]">
                    <th className="py-3 pr-4">Root Cause Class</th>
                    <th className="py-3 pr-4">Precision</th>
                    <th className="py-3 pr-4">Recall</th>
                    <th className="py-3 pr-4">F1-Score</th>
                    <th className="py-3">Support</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(metrics.per_class).map(([cls, m]) => (
                    <tr key={cls} className="border-b border-[var(--border)] last:border-0">
                      <td className="py-3 pr-4 font-mono text-xs">{cls}</td>
                      <td className="py-3 pr-4">
                        <Meter value={m.precision} />
                      </td>
                      <td className="py-3 pr-4">
                        <Meter value={m.recall} />
                      </td>
                      <td className="py-3 pr-4">
                        <Meter value={m.f1} />
                      </td>
                      <td className="py-3 text-[var(--muted)]">{m.support.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Dataset info */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
            <h3 className="font-semibold">Dataset Information</h3>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Stat label="Training Samples" value={metrics.train_samples.toLocaleString()} />
              <Stat label="Test Samples"     value={metrics.test_samples.toLocaleString()} />
              <Stat label="Total Classes"    value={String(metrics.classes.length)} />
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-10 text-center text-sm text-[var(--muted)]">
          No metrics available. Train the model first using the button above.
        </div>
      )}
    </div>
  );
}

function Meter({ value }: { value: number }) {
  const pct = value * 100;
  const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 rounded-full bg-[var(--card-2)] h-1.5 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs">{pct.toFixed(1)}%</span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-[var(--card-2)] p-4">
      <p className="text-xs text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}
