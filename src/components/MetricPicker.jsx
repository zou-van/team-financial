export default function MetricPicker({ metrics, selected, onChange }) {
  if (!metrics || metrics.length === 0) {
    return <div className="picker">无可用指标</div>;
  }

  return (
    <div className="picker">
      <label>
        指标：
        <select
          value={selected || ""}
          onChange={(e) => onChange(e.target.value)}
        >
          {metrics.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
