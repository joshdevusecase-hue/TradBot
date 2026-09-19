import { useEffect, useState } from "react";
import api from "../api/client";

function fmt(v) { return v != null ? `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"; }
function fmtDate(s) { return s ? s.slice(0, 16).replace("T", " ") : "—"; }

export default function TradeLog() {
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    api.get("/trades").then(r => setTrades(r.data)).catch(() => {});
  }, []);

  return (
    <div className="card trade-card">
      <h2 className="card-title">Trade Log</h2>
      {trades.length === 0 ? (
        <p className="empty-msg">No trades yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="trade-table">
            <thead>
              <tr>
                <th>#</th><th>Dir</th><th>Entry</th><th>Exit</th>
                <th>P&L</th><th>Exit reason</th><th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {trades.map(t => (
                <tr key={t.id} className={t.pnl >= 0 ? "row-win" : "row-loss"}>
                  <td>{t.id}</td>
                  <td><span className={`dir-badge ${t.direction === "LONG" ? "dir-long" : "dir-short"}`}>{t.direction}</span></td>
                  <td>{fmt(t.entry_price)}</td>
                  <td>{t.exit_price ? fmt(t.exit_price) : <span className="open-tag">open</span>}</td>
                  <td className={t.pnl >= 0 ? "pnl-pos" : "pnl-neg"}>{t.pnl != null ? fmt(t.pnl) : "—"}</td>
                  <td className="reason-cell">{t.exit_reason ?? "—"}</td>
                  <td className="date-cell">{fmtDate(t.entry_time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
