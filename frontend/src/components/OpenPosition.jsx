import { useEffect, useState } from "react";
import api from "../api/client";

function Field({ label, value, className }) {
  return (
    <div className="pos-field">
      <span className="pos-label">{label}</span>
      <span className={`pos-value ${className ?? ""}`}>{value}</span>
    </div>
  );
}

export default function OpenPosition() {
  const [pos, setPos] = useState(null);

  useEffect(() => {
    const load = () => api.get("/position").then(r => setPos(r.data)).catch(() => {});
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  if (!pos) return <div className="card pos-card"><p className="empty-msg">Loading position…</p></div>;
  if (!pos.open) return (
    <div className="card pos-card">
      <h2 className="card-title">Open Position</h2>
      <p className="empty-msg">No open position — bot is waiting for a signal.</p>
    </div>
  );

  const pnlClass = pos.unrealised_pnl >= 0 ? "pnl-pos" : "pnl-neg";
  const dirClass = pos.direction === "LONG" ? "dir-long" : "dir-short";

  return (
    <div className="card pos-card">
      <div className="card-header">
        <h2 className="card-title">Open Position</h2>
        <span className={`dir-badge ${dirClass}`}>{pos.direction}</span>
      </div>
      <div className="pos-grid">
        <Field label="Entry" value={`$${pos.entry_price?.toLocaleString()}`} />
        <Field label="Current" value={`$${pos.current_price?.toLocaleString()}`} />
        <Field label="Qty" value={pos.quantity} />
        <Field label="SL" value={`$${pos.sl_price?.toLocaleString()}`} />
        <Field label="TP" value={`$${pos.tp_price?.toLocaleString()}`} />
        <Field label="Time left" value={`${pos.time_remaining_h}h`} />
        <Field
          label="Unrealised P&L"
          value={`$${pos.unrealised_pnl?.toFixed(2)} (${pos.unrealised_pct?.toFixed(2)}%)`}
          className={pnlClass}
        />
      </div>
      <p className="pos-reason">{pos.signal_reason}</p>
    </div>
  );
}
