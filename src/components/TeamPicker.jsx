export default function TeamPicker({ teams, selected, onChange }) {
  if (!teams || teams.length === 0) {
    return <div className="picker">无可用团队</div>;
  }

  const bossTeams = teams.filter((t) => t.level === "boss");
  const subTeams = teams.filter((t) => t.level === "sub");
  const smallTeams = teams.filter((t) => t.level === "small");

  const handleToggle = (key) => {
    const next = new Set(selected);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    onChange([...next]);
  };

  return (
    <div className="picker team-picker">
      <span className="picker-label">团队：</span>

      {bossTeams.length > 0 && (
        <div className="team-group">
          {bossTeams.map((t) => (
            <label key={t.key} className="team-checkbox">
              <input
                type="checkbox"
                checked={selected.includes(t.key)}
                onChange={() => handleToggle(t.key)}
              />
              {t.label}
            </label>
          ))}
        </div>
      )}

      {subTeams.length > 0 && (
        <div className="team-group">
          <span className="group-label">子团队</span>
          {subTeams.map((t) => (
            <label key={t.key} className="team-checkbox">
              <input
                type="checkbox"
                checked={selected.includes(t.key)}
                onChange={() => handleToggle(t.key)}
              />
              {t.label}
            </label>
          ))}
        </div>
      )}

      {smallTeams.length > 0 && (
        <div className="team-group">
          <span className="group-label">小团队</span>
          {smallTeams.map((t) => (
            <label key={t.key} className="team-checkbox">
              <input
                type="checkbox"
                checked={selected.includes(t.key)}
                onChange={() => handleToggle(t.key)}
              />
              {t.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
