"use client";

import { useState, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

type PipelineResult = {
  test_id: string;
  status: string;
  pipeline: {
    classification: {
      root_cause: string;
      confidence: number;
      all_probabilities: Record<string, number>;
      model_used: string;
    };
    healing: {
      healing_id: string;
      repair_type: string;
      old_value: string;
      new_value: string;
      recommendation: string;
      status: string;
      developer_alert: boolean;
    };
    flaky_analysis: {
      is_flaky: boolean;
      flaky_probability: number;
      risk_level: string;
      instability_score: string;
      recent_pattern: string;
    };
    notification: { status: string } | null;
  };
};

const ROOT_CAUSE_COLORS: Record<string, string> = {
  locator_issue:       "text-blue-400 bg-blue-500/10 border-blue-500/30",
  synchronization_issue: "text-yellow-400 bg-yellow-500/10 border-yellow-500/30",
  test_data_issue:     "text-orange-400 bg-orange-500/10 border-orange-500/30",
  environment_failure: "text-purple-400 bg-purple-500/10 border-purple-500/30",
  network_api_error:   "text-red-400 bg-red-500/10 border-red-500/30",
  application_defect:  "text-pink-400 bg-pink-500/10 border-pink-500/30",
};

export default function SubmitPage() {
  const [tab, setTab] = useState<"manual" | "upload">("manual");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Form state
  const [form, setForm] = useState({
    test_name: "",
    pipeline: "GitHub Actions",
    error_message: "",
    stack_trace: "",
    logs: "",
    failure_stage: "test",
    failure_type: "Test Failure",
    severity: "MEDIUM",
    retry_count: 0,
    test_duration_sec: 30,
    cpu_usage_pct: 50,
    memory_usage_mb: 1024,
    old_locator: "",
  });

  const update = (k: string, v: string | number) =>
    setForm((p) => ({ ...p, [k]: v }));

  const submitForm = async () => {
    if (!form.test_name || !form.error_message) {
      setError("Test Name and Error Message are required.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/analyze/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const e = await res.json();
        throw new Error(e.detail || "Analysis failed");
      }
      setResult(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const processFile = useCallback(async (file: File) => {
    const text = await file.text();
    let parsed: Partial<typeof form> = {};
    try {
      // Try JSON first
      const json = JSON.parse(text);
      parsed = {
        test_name:       json.test_name || json.testName || file.name,
        error_message:   json.error_message || json.errorMessage || json.message || "",
        stack_trace:     json.stack_trace || json.stackTrace || "",
        logs:            json.logs || "",
        failure_stage:   json.failure_stage || "test",
        failure_type:    json.failure_type || "Test Failure",
        severity:        json.severity || "MEDIUM",
        retry_count:     Number(json.retry_count ?? 0),
        pipeline:        json.pipeline || "GitHub Actions",
        old_locator:     json.old_locator || json.old_value || "",
      };
    } catch {
      // Plain text — treat as error message + logs
      parsed = {
        test_name:     file.name.replace(/\.(log|json|txt)$/, ""),
        error_message: text.split("\n")[0]?.substring(0, 500) || text.substring(0, 500),
        logs:          text,
        stack_trace:   text.includes("Exception") || text.includes("Error")
          ? text.split("\n").filter((l) => l.trim().match(/at\s|Exception|Error/)).join("\n")
          : "",
      };
    }
    setForm((p) => ({ ...p, ...parsed }));
    setTab("manual");
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) processFile(file);
    },
    [processFile]
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Submit Test Failure</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Trigger the full AI analysis pipeline: Classification → Self-Healing → Flaky Detection
        </p>
      </div>

      {/* ── Tab bar ──────────────────────────────────────────────────────────── */}
      <div className="flex gap-2 rounded-xl bg-[var(--card-2)] p-1 w-fit">
        {(["manual", "upload"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-5 py-2 text-sm font-medium transition ${
              tab === t
                ? "bg-[var(--accent)] text-white"
                : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            {t === "manual" ? "✏️ Manual Input" : "📁 File Upload"}
          </button>
        ))}
      </div>

      {/* ── File Upload Tab ───────────────────────────────────────────────────── */}
      {tab === "upload" && (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onClick={() => fileRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed p-16 transition ${
            dragOver
              ? "border-[var(--accent)] bg-blue-500/5"
              : "border-[var(--border)] hover:border-[var(--accent)]/50"
          }`}
        >
          <div className="text-5xl">📂</div>
          <div className="text-center">
            <p className="font-semibold">Drop your artifact file here</p>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Supports <strong>.json</strong>, <strong>.log</strong>, <strong>.txt</strong>
            </p>
            <p className="mt-2 text-xs text-[var(--muted)]">
              JSON fields: test_name, error_message, stack_trace, logs, severity, retry_count
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".json,.log,.txt"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && processFile(e.target.files[0])}
          />
        </div>
      )}

      {/* ── Manual Input Form ─────────────────────────────────────────────────── */}
      {tab === "manual" && (
        <div className="grid gap-6 xl:grid-cols-2">
          {/* Left column */}
          <div className="space-y-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
            <h3 className="font-semibold">Test Information</h3>

            <Field label="Test Name *">
              <input
                value={form.test_name}
                onChange={(e) => update("test_name", e.target.value)}
                placeholder="e.g. Login Test"
                className={inputCls}
              />
            </Field>

            <Field label="Pipeline">
              <select
                value={form.pipeline}
                onChange={(e) => update("pipeline", e.target.value)}
                className={inputCls}
              >
                {["GitHub Actions", "Jenkins", "GitLab CI", "CircleCI", "Azure DevOps"].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Failure Stage">
                <select value={form.failure_stage} onChange={(e) => update("failure_stage", e.target.value)} className={inputCls}>
                  <option>test</option><option>build</option><option>deploy</option>
                </select>
              </Field>
              <Field label="Severity">
                <select value={form.severity} onChange={(e) => update("severity", e.target.value)} className={inputCls}>
                  <option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option>
                </select>
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Retry Count">
                <input type="number" min={0} max={10} value={form.retry_count}
                  onChange={(e) => update("retry_count", Number(e.target.value))} className={inputCls} />
              </Field>
              <Field label="Duration (sec)">
                <input type="number" min={0} value={form.test_duration_sec}
                  onChange={(e) => update("test_duration_sec", Number(e.target.value))} className={inputCls} />
              </Field>
            </div>

            <Field label="Old Locator (optional)">
              <input value={form.old_locator} onChange={(e) => update("old_locator", e.target.value)}
                placeholder="#submit-btn or //button[@id='pay']" className={inputCls} />
            </Field>
          </div>

          {/* Right column */}
          <div className="space-y-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
            <h3 className="font-semibold">Failure Artifacts</h3>

            <Field label="Error Message *">
              <textarea rows={3} value={form.error_message}
                onChange={(e) => update("error_message", e.target.value)}
                placeholder="NoSuchElementException: no such element: Unable to locate element..."
                className={inputCls + " resize-none"} />
            </Field>

            <Field label="Stack Trace">
              <textarea rows={4} value={form.stack_trace}
                onChange={(e) => update("stack_trace", e.target.value)}
                placeholder="at LoginPage.findElement()&#10;at TestBase.click()..."
                className={inputCls + " resize-none font-mono text-xs"} />
            </Field>

            <Field label="Logs">
              <textarea rows={3} value={form.logs}
                onChange={(e) => update("logs", e.target.value)}
                placeholder="Test execution logs..."
                className={inputCls + " resize-none font-mono text-xs"} />
            </Field>
          </div>
        </div>
      )}

      {/* ── Error ────────────────────────────────────────────────────────────── */}
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          ⚠️ {error}
        </div>
      )}

      {/* ── Submit button ─────────────────────────────────────────────────────── */}
      <button
        onClick={submitForm}
        disabled={loading}
        className="flex items-center gap-2 rounded-xl bg-[var(--accent)] px-8 py-3 font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
      >
        {loading ? (
          <>
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            Analyzing…
          </>
        ) : (
          "🚀 Run Analysis Pipeline"
        )}
      </button>

      {/* ── Result ───────────────────────────────────────────────────────────── */}
      {result && <AnalysisResult result={result} />}
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────────────── */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-[var(--muted)]">{label}</label>
      {children}
    </div>
  );
}

const inputCls =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--card-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)] transition";

function AnalysisResult({ result }: { result: PipelineResult }) {
  const { classification: cls, healing, flaky_analysis: flaky, notification } = result.pipeline;
  const rcColor = ROOT_CAUSE_COLORS[cls.root_cause] ?? "text-gray-400 bg-gray-500/10 border-gray-500/30";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h3 className="text-lg font-semibold">Analysis Complete</h3>
        <span className="rounded-full bg-green-500/10 px-3 py-1 text-xs font-medium text-green-400 border border-green-500/30">
          ✓ {result.test_id}
        </span>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {/* Classification */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-[var(--muted)]">🤖 ML Classification</p>
          <span className={`inline-flex rounded-full border px-3 py-1 text-sm font-semibold ${rcColor}`}>
            {cls.root_cause.replace(/_/g, " ")}
          </span>
          <p className="text-2xl font-bold">{(cls.confidence * 100).toFixed(1)}%</p>
          <p className="text-xs text-[var(--muted)]">Confidence · {cls.model_used}</p>
          <div className="space-y-1 pt-2">
            {Object.entries(cls.all_probabilities)
              .sort(([, a], [, b]) => b - a)
              .map(([label, prob]) => (
                <div key={label} className="flex items-center gap-2">
                  <div className="w-24 shrink-0 text-xs text-[var(--muted)] truncate">{label.replace(/_/g, " ")}</div>
                  <div className="flex-1 rounded-full bg-[var(--card-2)] h-1.5 overflow-hidden">
                    <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${prob * 100}%` }} />
                  </div>
                  <span className="text-xs w-10 text-right">{(prob * 100).toFixed(0)}%</span>
                </div>
              ))}
          </div>
        </div>

        {/* Healing */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-[var(--muted)]">🔧 Self-Healing</p>
          <p className="font-semibold">{healing.repair_type}</p>
          <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${
            healing.status === "Suggested" ? "bg-blue-500/10 text-blue-400 border-blue-500/30" :
            healing.status === "Applied"   ? "bg-green-500/10 text-green-400 border-green-500/30" :
            healing.status === "Rejected"  ? "bg-red-500/10 text-red-400 border-red-500/30" :
            "bg-yellow-500/10 text-yellow-400 border-yellow-500/30"
          }`}>
            {healing.status}
          </span>
          {healing.old_value && (
            <div className="space-y-1 text-xs font-mono">
              <p className="text-red-400 line-through opacity-70">{healing.old_value}</p>
              <p className="text-green-400">{healing.new_value}</p>
            </div>
          )}
          <p className="text-xs text-[var(--muted)] leading-relaxed">{healing.recommendation}</p>
          {healing.developer_alert && (
            <span className="inline-flex rounded-full bg-orange-500/10 border border-orange-500/30 px-2 py-0.5 text-xs text-orange-400">
              🔔 Developer Alert Sent
            </span>
          )}
        </div>

        {/* Flaky */}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 space-y-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-[var(--muted)]">📈 Flaky Detection</p>
          <div className="flex items-baseline gap-2">
            <p className="text-3xl font-bold">{flaky.instability_score}</p>
            <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
              flaky.risk_level === "High"   ? "bg-red-500/10 text-red-400 border-red-500/30" :
              flaky.risk_level === "Medium" ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/30" :
              "bg-green-500/10 text-green-400 border-green-500/30"
            }`}>
              {flaky.risk_level} Risk
            </span>
          </div>
          <p className="text-xs text-[var(--muted)]">Instability Score</p>
          <div className="w-full rounded-full bg-[var(--card-2)] h-2 overflow-hidden">
            <div
              className={`h-full rounded-full ${
                flaky.risk_level === "High" ? "bg-red-500" :
                flaky.risk_level === "Medium" ? "bg-yellow-500" : "bg-green-500"
              }`}
              style={{ width: flaky.instability_score }}
            />
          </div>
          <p className="text-xs text-[var(--muted)]">Recent Pattern</p>
          <div className="flex gap-1 flex-wrap">
            {flaky.recent_pattern.split(", ").map((r, i) => (
              <span key={i} className={`rounded px-2 py-0.5 text-xs font-mono ${
                r === "FAIL" ? "bg-red-500/20 text-red-400" : "bg-green-500/20 text-green-400"
              }`}>{r}</span>
            ))}
          </div>
          {notification && (
            <span className="inline-flex rounded-full bg-blue-500/10 border border-blue-500/30 px-2 py-0.5 text-xs text-blue-400">
              📧 Notification: {notification.status}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
