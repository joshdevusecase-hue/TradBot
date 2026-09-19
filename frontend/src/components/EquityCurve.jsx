import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";
import api from "../api/client";

const fmt = v => `$${v.toLocaleString()}`;

export default function EquityCurve() {
  const [data, setData] = useState([]);
  const [perf, setPerf] = useState(null);

  useEffect(() => {
    api.get("/equity").then(r => setData(r.data)).catch(() => {});
    api.get("/performance").then(r => setPerf(r.data)).catch(() => {});
  }, []);

  const returnPct = perf?.total_return_pct ?? 0;
  const returnClass = returnPct >= 0 ? "pnl-pos" : "pnl-neg";

  return (
    <div className="card equity-card">
      <div className="card-header">
        <h2 className="card-title">Equity Curve</h2>
        {perf && (
          <span className={`return-badge ${returnClass}`}>
            {returnPct >= 0 ? "+" : ""}{returnPct.toFixed(2)}%
          </span>
        )}
      </div>

      {data.length < 2 ? (
        <p className="empty-msg">No completed trades yet — equity curve will appear after the first closed trade.</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--text-muted)" }} tickLine={false} />
            <YAxis domain={["auto", "auto"]} tickFormatter={fmt} tick={{ fontSize: 11, fill: "var(--text-muted)" }} tickLine={false} width={80} />
            <Tooltip formatter={v => [fmt(v), "Portfolio"]} contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }} />
            <Line type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}

      {perf && (
        <div className="perf-strip">
          <Stat label="Trades" value={perf.total_trades} />
          <Stat label="Win rate" value={`${perf.win_rate?.toFixed(1)}%`} />
          <Stat label="Sharpe" value={perf.sharpe?.toFixed(2)} />
          <Stat label="Max DD" value={`${perf.max_drawdown_pct?.toFixed(1)}%`} red />
          <Stat label="Avg win" value={`$${perf.avg_win?.toFixed(2)}`} />
          <Stat label="Avg loss" value={`$${perf.avg_loss?.toFixed(2)}`} red />
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, red }) {
  return (
    <div className="perf-stat">
      <span className="perf-label">{label}</span>
      <span className={`perf-value ${red ? "pnl-neg" : ""}`}>{value ?? "—"}</span>
    </div>
  );
}
