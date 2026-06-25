import { useEffect, useRef, useState } from "react";

import { api } from "../api";

// ── Pipeline step definitions ─────────────────────────────────────────────────
const PIPELINE_STEPS = [
  { id: "zip",   icon: "📦", label: "Zip workspace" },
  { id: "send",  icon: "📡", label: "Send to VM"    },
  { id: "build", icon: "🏗️", label: "Docker build"  },
  { id: "run",   icon: "▶️", label: "Start container"},
  { id: "live",  icon: "🌐", label: "Public URL"    },
];

// Keywords in SSE step text → pipeline stage
const STEP_KEYWORDS = {
  zip:   ["zip", "pack", "compress"],
  send:  ["send", "upload", "transfer", "connecting"],
  build: ["build", "docker", "layer", "pull", "step"],
  run:   ["start", "container", "running", "launch"],
  live:  ["live", "url", "http", "done", "success"],
};

function stepFromText(text) {
  const lower = (text || "").toLowerCase();
  for (const [id, kws] of Object.entries(STEP_KEYWORDS)) {
    if (kws.some((kw) => lower.includes(kw))) return id;
  }
  return null;
}

// ── URL anatomy breakdown ─────────────────────────────────────────────────────
function UrlAnatomy({ url }) {
  // e.g. http://nixornode-2.eastus.cloudapp.azure.com:9004
  const m = url.match(/^(https?:\/\/)([^/:]+?)(\.[^/:]+\.cloudapp\.azure\.com)(:\d+)?(.*)$/);
  if (!m) return <code className="deploy-url-raw">{url}</code>;
  const [, scheme, label, suffix, port] = m;
  return (
    <div className="url-anatomy">
      <code className="url-full">{url}</code>
      <div className="url-parts">
        <span className="url-part scheme">
          <span className="url-value">{scheme}</span>
          <span className="url-label">protocol</span>
        </span>
        <span className="url-part host">
          <span className="url-value">{label}</span>
          <span className="url-label">your VM node</span>
        </span>
        <span className="url-part suffix">
          <span className="url-value">{suffix}</span>
          <span className="url-label">Azure DNS</span>
        </span>
        {port && (
          <span className="url-part port">
            <span className="url-value">{port}</span>
            <span className="url-label">your port</span>
          </span>
        )}
      </div>
    </div>
  );
}

// ── Slot info card shown before deploy ───────────────────────────────────────
function SlotCard({ sandbox }) {
  const nodeIdx = sandbox?.cluster_node_index ?? null;
  const port = sandbox?.cluster_port ?? null;
  const hasSlot = nodeIdx !== null && port !== null;

  return (
    <div className="slot-card">
      <div className="slot-title">Your deployment slot</div>
      {hasSlot ? (
        <div className="slot-fields">
          <div className="slot-field">
            <span className="slot-icon">🖥️</span>
            <span>
              <strong>VM node {nodeIdx + 1}</strong>
              <br />
              <span className="slot-sub">nixornode-{nodeIdx + 1}.eastus.cloudapp.azure.com</span>
            </span>
          </div>
          <div className="slot-field">
            <span className="slot-icon">🔌</span>
            <span>
              <strong>Port {port}</strong>
              <br />
              <span className="slot-sub">reserved for you on this VM</span>
            </span>
          </div>
          <div className="slot-field">
            <span className="slot-icon">📦</span>
            <span>
              <strong>Container</strong>
              <br />
              <span className="slot-sub">student-{sandbox?.slug || "…"}</span>
            </span>
          </div>
        </div>
      ) : (
        <p className="slot-pending">
          Waiting for slot assignment… your instructor provisions the cluster before Day 3.
        </p>
      )}
    </div>
  );
}

// ── Pipeline visual ───────────────────────────────────────────────────────────
function Pipeline({ activeStep, doneSteps }) {
  return (
    <div className="pipeline">
      {PIPELINE_STEPS.map((s, i) => {
        const done = doneSteps.includes(s.id);
        const active = activeStep === s.id;
        return (
          <div key={s.id} className={`pipe-step ${done ? "done" : ""} ${active ? "active" : ""}`}>
            <div className="pipe-icon">{s.icon}</div>
            <div className="pipe-label">{s.label}</div>
            {i < PIPELINE_STEPS.length - 1 && (
              <div className={`pipe-arrow ${done ? "done" : ""}`}>→</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function DeployPanel() {
  const [sandbox, setSandbox] = useState(null);
  const [deploying, setDeploying] = useState(false);
  const [lines, setLines] = useState([]);
  const [liveUrl, setLiveUrl] = useState("");
  const [error, setError] = useState("");
  const [activeStep, setActiveStep] = useState(null);
  const [doneSteps, setDoneSteps] = useState([]);
  const [copied, setCopied] = useState(false);
  const logRef = useRef(null);

  useEffect(() => {
    api.sandbox().then(setSandbox).catch(() => setSandbox(null));
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  function advancePipeline(stepId) {
    if (!stepId) return;
    const idx = PIPELINE_STEPS.findIndex((s) => s.id === stepId);
    setActiveStep(stepId);
    setDoneSteps(PIPELINE_STEPS.slice(0, idx).map((s) => s.id));
  }

  function appendLine(cls, text) {
    setLines((prev) => [...prev, { cls, text }]);
  }

  async function onDeploy() {
    setDeploying(true);
    setLines([]);
    setError("");
    setLiveUrl("");
    setActiveStep("zip");
    setDoneSteps([]);
    try {
      await api.deploy((evt) => {
        if (evt.step) {
          appendLine("step", `▶ ${evt.step}`);
          const s = stepFromText(evt.step);
          if (s) advancePipeline(s);
        }
        if (evt.log) appendLine("log", `  ${evt.log}`);
        if (evt.url) {
          setLiveUrl(evt.url);
          setDoneSteps(PIPELINE_STEPS.map((s) => s.id));
          setActiveStep(null);
        }
        if (evt.error) {
          setError(evt.error);
          appendLine("err", `⚠ ${evt.error}`);
        }
      });
    } catch (e) {
      setError(e.message || "Deploy failed");
    } finally {
      setDeploying(false);
      api.sandbox().then(setSandbox).catch(() => {});
    }
  }

  function copyUrl() {
    navigator.clipboard.writeText(liveUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const hasSlot =
    sandbox?.cluster_node_index !== null &&
    sandbox?.cluster_node_index !== undefined &&
    sandbox?.cluster_port !== null &&
    sandbox?.cluster_port !== undefined;

  return (
    <section className="panel deploy-panel">
      <header className="panel-header">
        <span>Deploy to VM Cluster</span>
        {sandbox && (
          <span className={`badge badge-${sandbox.status}`}>{sandbox.status}</span>
        )}
      </header>

      <div className="deploy-body">
        <SlotCard sandbox={sandbox} />

        {hasSlot && !deploying && !liveUrl && !error && (
          <button className="deploy-btn" onClick={onDeploy}>
            🚀 Deploy my app
          </button>
        )}

        {(deploying || liveUrl || error) && (
          <Pipeline activeStep={activeStep} doneSteps={doneSteps} />
        )}

        {deploying && (
          <div className="deploy-status-row">
            <span className="spinner" />
            <span className="deploy-status-text">Building and starting your container…</span>
          </div>
        )}

        {liveUrl && (
          <div className="deploy-success">
            <div className="deploy-success-header">Your app is live</div>
            <UrlAnatomy url={liveUrl} />
            <div className="deploy-actions">
              <a className="deploy-open" href={liveUrl} target="_blank" rel="noreferrer">
                Open app ↗
              </a>
              <button className="deploy-copy" onClick={copyUrl}>
                {copied ? "Copied!" : "Copy URL"}
              </button>
              <button className="deploy-again" onClick={onDeploy} disabled={deploying}>
                Redeploy
              </button>
            </div>
            <p className="deploy-hint">
              This URL works for anyone on the internet — share it with your neighbour.
            </p>
          </div>
        )}

        {error && !deploying && (
          <div className="deploy-error-box">
            <span>⚠ {error}</span>
            <button className="deploy-retry" onClick={onDeploy}>
              Retry
            </button>
          </div>
        )}

        {lines.length > 0 && (
          <details className="deploy-log-details" open={deploying || !!error}>
            <summary>Build log ({lines.length} lines)</summary>
            <pre className="deploy-log" ref={logRef}>
              {lines.map((l, i) => (
                <span key={i} className={`log-${l.cls}`}>
                  {l.text}
                  {"\n"}
                </span>
              ))}
            </pre>
          </details>
        )}
      </div>
    </section>
  );
}
