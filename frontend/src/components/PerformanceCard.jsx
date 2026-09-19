import { useState } from "react";
import api from "../api/client";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid
} from "recharts";

const fmt$ = v => `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;

export default function PerformanceCard() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(90);

  const run = () => {
    setLoading(true);
    api.get(`/backtest?days=${days}`, { timeout: 120_000 })
      .then(r => setResult(r.data))
      .catch(err => {
        const detail = err.response?.data?.detail;
        let error = "No response from the backend. Make sure python main.py is running in the backend folder.";
        if (detail) error = `Backtest failed: ${detail}`;
        else if (err.code === "ECONNABORTED") error = "Backtest timed out after 2 minutes. Try a shorter period.";
        setResult({ error });
      })
      .finally(() => setLoading(false));
  };

  return (
    <div className="card backtest-card">
      <div className="card-header">
        <h2 className="card-title">Backtest</h2>
        <div className="bt-controls">
          <select value={days} onChange={e => setDays(Number(e.target.value))} className="bt-select">
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
            <option value={365}>365 days</option>
          </select>
          <button onClick={run} disabled={loading} className="bt-btn">
            {loading ? "Running…" : "Run backtest"}
          </button>
        </div>
      </div>

      {!result && !loading && (
        <p className="empty-msg">Click "Run backtest" to replay the strategy on historical Binance data.</p>
      )}

      {loading && <p className="empty-msg">Fetching candles and replaying the strategy…</p>}

      {result?.error && <p className="error-msg">{result.error}</p>}

      {result && !result.error && (
        <>
          <div className="perf-strip">
            <Stat label="Trades" value={result.total_trades} />
            <Stat label="Return" value={`${result.total_return_pct >= 0 ? "+" : ""}${result.total_return_pct?.toFixed(2)}%`} pos={result.total_return_pct >= 0} />
            <Stat label="Win rate" value={`${result.win_rate?.toFixed(1)}%`} />
            <Stat label="Sharpe" value={result.sharpe?.toFixed(2)} />
            <Stat label="Max DD" value={`${result.max_drawdown_pct?.toFixed(1)}%`} red />
            <Stat label="RR ratio" value={result.rr_ratio?.toFixed(2)} />
            <Stat label="Fees paid" value={fmt$(result.fees_paid)} red />
            <Stat label="Buy & hold" value={`${result.buy_hold_pct >= 0 ? "+" : ""}${result.buy_hold_pct?.toFixed(2)}%`} />
          </div>
          <p className="bt-note">
            Buy-only on spot, {result.fee_pct}% fee on each buy and sell, stops and targets filled inside the hour.
            Buy &amp; hold is what simply holding BTC over the same days returned.
          </p>

          {result.equity_curve?.length > 2 && (
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={result.equity_curve} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--text-muted)" }} tickLine={false} />
                <YAxis domain={["auto", "auto"]} tickFormatter={v => `$${(v / 1000).toFixed(1)}k`} tick={{ fontSize: 10, fill: "var(--text-muted)" }} tickLine={false} width={56} />
                <Tooltip formatter={v => [fmt$(v), "Portfolio"]} contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6 }} />
                <Line type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value, red, pos }) {
  const cls = red ? "pnl-neg" : pos === true ? "pnl-pos" : "";
  return (
    <div className="perf-stat">
      <span className="perf-label">{label}</span>
      <span className={`perf-value ${cls}`}>{value ?? "—"}</span>
    </div>
  );
}
