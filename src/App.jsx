import { useState } from "react";
import { loadAllData } from "./lib/loadData";
import MonthSelector from "./components/MonthSelector";
import ViewTabs from "./components/ViewTabs";
import MonthlyTable from "./components/MonthlyTable";
import TrendChart from "./components/TrendChart";
import "./App.css";

// Load at module level — static data bundled at build time
const DATA = loadAllData();

export default function App() {
  const { months, index } = DATA;
  const monthKeys = Object.keys(months).sort();

  const [selectedMonth, setSelectedMonth] = useState(
    monthKeys[monthKeys.length - 1] || ""
  );
  const [view, setView] = useState("monthly");

  const currentMonthData = months[selectedMonth] || null;

  return (
    <div className="app">
      <header className="app-header">
        <p className="app-eyebrow">TEAM FINANCE</p>
        <h1>团队财务看板</h1>
        <p className="app-subtitle">按月查看团队经营指标与趋势</p>
      </header>

      <div className="app-toolbar">
        <MonthSelector
          months={monthKeys}
          selected={selectedMonth}
          onChange={setSelectedMonth}
        />
        <ViewTabs active={view} onChange={setView} />
      </div>

      <main className="app-main">
        {view === "monthly" ? (
          <MonthlyTable
            key={selectedMonth}
            data={currentMonthData}
            mapping={index}
            months={months}
            selectedMonth={selectedMonth}
          />
        ) : (
          <TrendChart trendData={DATA.trendData} />
        )}
      </main>
    </div>
  );
}
