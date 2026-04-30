export default function MonthSelector({ months, selected, onChange }) {
  if (!months || months.length === 0) {
    return <div className="month-selector">暂无数据</div>;
  }

  return (
    <div className="month-selector">
      <label>
        选择月份：
        <select
          value={selected || ""}
          onChange={(e) => onChange(e.target.value)}
        >
          {months.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
