import { useEffect, useRef, useState } from "react";

import { api } from "../api";

// Session 3 one-click deploy. The platform runs `az webapp up` server-side into the
// student's own resource group and streams logs here — students never touch Azure auth.
export function DeployPanel() {
  const [sandbox, setSandbox] = useState(null);
  const [deploying, setDeploying] = useState(false);
  const [lines, setLines] = useState([]);
  const [liveUrl, setLiveUrl] = useState("");
  const [error, setError] = useState("");
  const logRef = useRef(null);

  useEffect(() => {
    api.sandbox().then(setSandbox).catch(() => setSandbox(null));
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines]);

  const append = (text) => setLines((prev) => [...prev, text]);

  async function onDeploy() {
    setDeploying(true);
    setLines([]);
    setError("");
    setLiveUrl("");
    try {
      await api.deploy((evt) => {
        if (evt.step) append(`▶ ${evt.step}`);
        if (evt.log) append(`  ${evt.log}`);
        if (evt.url) setLiveUrl(evt.url);
        if (evt.error) setError(evt.error);
      });
    } catch (e) {
      setError(e.message || "Deploy failed");
    } finally {
      setDeploying(false);
      api.sandbox().then(setSandbox).catch(() => {});
    }
  }

  const ready = sandbox && sandbox.resource_group && sandbox.webapp_name;

  return (
    <section className="panel deploy-panel">
      <header className="panel-header">
        <span>Deploy to Azure</span>
        {sandbox && <span className="badge">{sandbox.status}</span>}
      </header>

      <div className="deploy-body">
        {!ready && (
          <p className="muted">
            Your Azure sandbox isn’t set up yet. Once your instructor provisions it,
            a one-click deploy button appears here.
          </p>
        )}

        {ready && (
          <>
            <p className="muted">
              Deploys your current app to <code>{sandbox.webapp_name}</code> in{" "}
              <code>{sandbox.resource_group}</code>. No Azure login needed.
            </p>
            <button className="primary" onClick={onDeploy} disabled={deploying}>
              {deploying ? "Deploying…" : "🚀 Deploy my app to Azure"}
            </button>
          </>
        )}

        {liveUrl && (
          <p className="deploy-url">
            ✅ Live at{" "}
            <a href={liveUrl} target="_blank" rel="noreferrer">
              {liveUrl}
            </a>
          </p>
        )}
        {error && <p className="deploy-error">⚠ {error}</p>}

        {lines.length > 0 && (
          <pre className="deploy-log" ref={logRef}>
            {lines.join("\n")}
          </pre>
        )}
      </div>
    </section>
  );
}
