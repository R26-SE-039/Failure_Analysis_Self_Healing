"use client";

import { useState, useEffect } from "react";
import { RefreshCw, Activity, ArrowRight, ShieldCheck, Database, Award } from "lucide-react";

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
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-extrabold tracking-tight text-[var(--foreground)]">Model Training & Metrics</h2>
        <p className="text-xs font-medium text-[var(--muted)]">
          Monitor ML classifier performance and trigger model retraining
        </p>
      </div>

      {/* ── Service Health ─────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
        <div className="flex items-center justify-between border-b border-[var(--border)] pb-4 mb-4">
          <div>
            <h3 className="text-base font-bold tracking-tight text-[var(--foreground)]">Microservice Status</h3>
            <p className="text-xs font-medium text-[var(--muted)]">Health checks across analytics backend</p>
          </div>
          <button
            onClick={fetchHealth}
            className="flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--card-2)] px-3.5 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-100/80"
          >
            <RefreshCw size={13} />
            Refresh
          </button>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {health
            ? Object.entries(health).map(([name, info]) => (
                <div key={name} className="rounded-2xl bg-[var(--card-2)] p-4 border border-[var(--border)]/40 hover:border-indigo-100 transition duration-150 relative overflow-hidden flex flex-col justify-between min-h-[110px]">
                  <div className="absolute top-0 right-0 p-2 opacity-10">
                    <Activity size={32} className={`${info.status === "ready" ? "text-emerald-500" : "text-red-500 animate-pulse"}`} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${info.status === "ready" ? "bg-emerald-500 shadow-sm shadow-emerald-500/30" : "bg-red-500 shadow-sm shadow-red-500/30"}`} />
                      <p className="text-xs font-extrabold capitalize tracking-tight text-slate-800">{name.replace("-service", "")} Service</p>
                    </div>
                    <p className={`mt-2 text-xs font-bold ${info.status === "ready" ? "text-emerald-700" : "text-red-600"}`}>
                      {info.status === "ready" ? "Active & Healthy" : "Offline / Unreachable"}
                    </p>
                    {info.model && <p className="text-[11px] font-mono font-medium text-[var(--muted)] mt-1 truncate max-w-[200px]">{info.model}</p>}
                    {info.error && <p className="text-[11px] font-medium text-red-600 mt-1 truncate max-w-[200px]" title={info.error}>{info.error}</p>}
                  </div>
                </div>
              ))
            : Array(4).fill(0).map((_, i) => (
                <div key={i} className="rounded-2xl bg-[var(--card-2)] p-4 animate-pulse h-28 border border-[var(--border)]/30" />
              ))}
        </div>
      </div>

      {/* ── Retrain ───────────────────────────────────────────────────────────── */}
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-5 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-indigo-500 to-purple-600" />
        <div>
          <h3 className="text-base font-bold tracking-tight text-[var(--foreground)]">Retrain ML Engine</h3>
          <p className="text-xs font-medium text-[var(--muted)] max-w-xl">
            Retrain directly on the <code className="bg-[var(--card-2)] px-1.5 py-0.5 rounded border border-[var(--border)]/30 text-xs font-mono font-bold text-indigo-700">final_training_dataset.csv</code>. Takes ~3–5 minutes.
          </p>
          {retrainMsg && (
            <p className="mt-3 text-xs font-bold bg-indigo-50/50 border border-indigo-100/50 p-2 rounded-xl text-indigo-800 max-w-fit">{retrainMsg}</p>
          )}
        </div>
        <button
          onClick={handleRetrain}
          disabled={retraining}
          className="flex shrink-0 items-center gap-2 rounded-2xl bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-3.5 font-extrabold text-xs text-white hover:opacity-95 disabled:opacity-50 hover:shadow-lg hover:shadow-indigo-500/15 transition-all"
        >
          {retraining ? (
            <>
              <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Training Process Running…
            </>
          ) : (
            <>
              <RefreshCw size={14} />
              Retrain Production Model
            </>
          )}
        </button>
      </div>

      {/* ── Metrics ───────────────────────────────────────────────────────────── */}
      {loadingMetrics ? (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 animate-pulse h-40" />
      ) : metrics ? (
        <div className="space-y-6">
          {/* Summary cards */}
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
            {[
              { label: "Overall Accuracy", value: `${(metrics.accuracy * 100).toFixed(2)}%`, icon: ShieldCheck, color: "text-emerald-600", bg: "bg-emerald-50/60" },
              { label: "Macro F1 Score",    value: `${(metrics.macro_f1 * 100).toFixed(2)}%`,  icon: Award,       color: "text-indigo-600",  bg: "bg-indigo-50/60"  },
              { label: "Macro Precision", value: `${(metrics.macro_precision * 100).toFixed(2)}%`, icon: Activity,  color: "text-amber-600",   bg: "bg-amber-50/60"  },
              { label: "Macro Recall",    value: `${(metrics.macro_recall * 100).toFixed(2)}%`,   icon: Database,  color: "text-purple-600",  bg: "bg-purple-50/60" },
            ].map((m) => {
              const Icon = m.icon;
              return (
                <div key={m.label} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm flex flex-col justify-between h-full relative group">
                  <div className="flex justify-between items-start">
                    <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">{m.label}</p>
                    <div className={`w-8 h-8 rounded-xl ${m.bg} flex items-center justify-center ${m.color}`}>
                      <Icon size={16} />
                    </div>
                  </div>
                  <p className={`mt-2 text-3xl font-extrabold ${m.color}`}>{m.value}</p>
                  <p className="mt-1 text-xs font-medium text-[var(--muted)] uppercase tracking-wide">
                    {metrics.model_name}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Model comparison */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
            <h3 className="text-base font-bold tracking-tight text-[var(--foreground)] border-b border-[var(--border)] pb-4 mb-4">Model Performance Benchmarks</h3>
            <div className="mt-4 space-y-4">
              {Object.entries(metrics.all_models).map(([name, acc]) => (
                <div key={name} className="flex items-center gap-4">
                  <span className="w-44 shrink-0 text-xs font-bold text-slate-800 tracking-tight">{name}</span>
                  <div className="flex-1 rounded-full bg-[var(--card-2)] h-3.5 overflow-hidden border border-[var(--border)]/20 p-0.5">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-indigo-600 transition-all duration-300"
                      style={{ width: `${acc * 100}%` }}
                    />
                  </div>
                  <span className="w-16 text-right text-xs font-bold font-mono text-indigo-700">{(acc * 100).toFixed(2)}%</span>
                </div>
              ))}
            </div>
          </div>

          {/* Per-class metrics */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
            <h3 className="text-base font-bold tracking-tight text-[var(--foreground)] border-b border-[var(--border)] pb-4 mb-4">Per-Class Performance breakdown</h3>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-left text-xs font-bold text-[var(--muted)] uppercase tracking-wider">
                    <th className="py-3 pr-4 px-1">Root Cause Category</th>
                    <th className="py-3 pr-4">Precision</th>
                    <th className="py-3 pr-4">Recall</th>
                    <th className="py-3 pr-4">F1-Score</th>
                    <th className="py-3">Support</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(metrics.per_class).map(([cls, m]) => (
                    <tr key={cls} className="border-b border-[var(--border)] last:border-0 hover:bg-slate-50/50 transition duration-150">
                      <td className="py-4 pr-4 font-bold text-slate-800">{cls}</td>
                      <td className="py-4 pr-4">
                        <Meter value={m.precision} />
                      </td>
                      <td className="py-4 pr-4">
                        <Meter value={m.recall} />
                      </td>
                      <td className="py-4 pr-4">
                        <Meter value={m.f1} />
                      </td>
                      <td className="py-4 text-xs font-mono font-bold text-slate-700">{m.support.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Dataset info */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
            <h3 className="text-base font-bold tracking-tight text-[var(--foreground)] border-b border-[var(--border)] pb-4 mb-4">Dataset Diagnostics</h3>
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <Stat label="Training Samples" value={metrics.train_samples.toLocaleString()} color="text-indigo-600" />
              <Stat label="Test Samples"     value={metrics.test_samples.toLocaleString()} color="text-purple-600" />
              <Stat label="Total Target Classes" value={String(metrics.classes.length)} color="text-pink-600" />
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-10 text-center text-sm font-medium text-[var(--muted)] shadow-sm">
          No metrics available yet. Train the model first using the button above.
        </div>
      )}
    </div>
  );
}

function Meter({ value }: { value: number }) {
  const pct = value * 100;
  const color = pct >= 80 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-3">
      <div className="w-24 rounded-full bg-[var(--card-2)] h-2 overflow-hidden border border-[var(--border)]/20 p-0.5">
        <div className={`h-full rounded-full ${color} transition-all duration-300`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-bold font-mono text-slate-700">{pct.toFixed(1)}%</span>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-2xl bg-[var(--card-2)] p-5 border border-[var(--border)]/40 flex flex-col justify-between h-full hover:border-indigo-100 transition duration-150">
      <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">{label}</p>
      <p className={`mt-2 text-3xl font-extrabold ${color}`}>{value}</p>
    </div>
  );
}
