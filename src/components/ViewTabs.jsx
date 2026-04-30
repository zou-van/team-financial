const TABS = [
  { key: "monthly", label: "月度详情" },
  { key: "trend", label: "趋势图" },
];

export default function ViewTabs({ active, onChange }) {
  return (
    <div className="view-tabs">
      {TABS.map((t) => (
        <button
          key={t.key}
          className={`tab ${active === t.key ? "active" : ""}`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
