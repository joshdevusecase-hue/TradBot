import StatusBar from "./components/StatusBar";
import OpenPosition from "./components/OpenPosition";
import EquityCurve from "./components/EquityCurve";
import TradeLog from "./components/TradeLog";
import PerformanceCard from "./components/PerformanceCard";
import "./App.css";

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <div className="header-brand">
          <span className="header-logo">⚡</span>
          <span className="header-name">TradBot</span>
          <span className="header-sub">Binance spot · BTC/USDT</span>
        </div>
      </header>
      <StatusBar />
      <main className="app-main">
        <div className="col-left">
          <OpenPosition />
          <EquityCurve />
        </div>
        <div className="col-right">
          <PerformanceCard />
          <TradeLog />
        </div>
      </main>
    </div>
  );
}
