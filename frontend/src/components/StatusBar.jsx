import { useEffect, useState } from "react";
import api from "../api/client";

export default function StatusBar() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    const load = () => api.get("/status").then(r => setStatus(r.data)).catch(() => {});
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  if (!status) return <div className="status-bar status-loading">Connecting…</div>;

  const modeLabel = status.paper_mode ? "Paper" : "Live";
  const modeClass = status.paper_mode ? "badge-paper" : "badge-live";
  const signalClass =
    status.last_signal === "LONG" ? "signal-long" :
    status.last_signal === "SHORT" ? "signal-short" :
    "signal-flat";

  return (
    <div className="status-bar">
      <div className="status-left">
        <span className={`dot ${status.running ? "dot-active" : "dot-idle"}`} />
        <span className="status-label">{status.running ? "Running pipeline…" : "Waiting for next hour"}</span>
        <span className={`badge ${modeClass}`}>{modeLabel}</span>
        <span className="status-symbol">{status.symbol}</span>
      </div>
      <div className="status-right">
        <span className={`signal-chip ${signalClass}`}>{status.last_signal}</span>
        <span className="signal-reason">{status.last_signal_reason}</span>
      </div>
    </div>
  );
}
