import { useEffect, useState } from "react";
import api from "../api/client";

export default function StatusBar() {
  const [status, setStatus] = useState(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const load = () => api.get("/status")
      .then(r => { setStatus(r.data); setOffline(false); })
      .catch(() => setOffline(true));
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  if (offline) return (
    <div className="status-bar status-offline">
      <div className="status-left">
        <span className="dot dot-offline" />
        <span>
          <strong className="offline-label">Backend offline.</strong> Start it with <code>python backend/main.py</code> in
          the TradBot folder. Checking again every 15s.
        </span>
      </div>
    </div>
  );
  if (!status) return <div className="status-bar status-loading">Connecting…</div>;

  const modeLabel = status.paper_mode ? "Paper" : `Live · cap ${status.max_capital_usdt?.toLocaleString()} USDT`;
  const modeClass = status.paper_mode ? "badge-paper" : "badge-live";
  const signalClass = status.last_signal === "LONG" ? "signal-long" : "signal-flat";
  const gate = status.gate;

  return (
    <div className="status-bar">
      <div className="status-left">
        <span className={`dot ${status.running ? "dot-active" : "dot-idle"}`} />
        <span className="status-label">{status.running ? "Running pipeline…" : "Waiting for next hour"}</span>
        <span className={`badge ${modeClass}`}>{modeLabel}</span>
        {gate && (
          <span className={`badge ${gate.passed ? "badge-gate-open" : "badge-gate-locked"}`}
                title={`Live buys need a ${gate.rule}`}>
            {gate.passed ? "Live trading unlocked" : "Live trading locked"} · Sharpe {gate.sharpe ?? "—"}
          </span>
        )}
        <span className="status-symbol">{status.symbol}</span>
      </div>
      <div className="status-right">
        <span className={`signal-chip ${signalClass}`}>{status.last_signal}</span>
        <span className="signal-reason">{status.last_signal_reason}</span>
      </div>
    </div>
  );
}
