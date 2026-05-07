import { useState, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

function formatNumber(val) {
  if (val == null) return "-";
  return Math.round(val).toLocaleString("zh-CN");
}

const COLORS = [
  "#2563eb", "#dc2626", "#16a34a", "#ca8a04", "#9333ea",
  "#0891b2", "#d97706", "#4f46e5", "#be123c", "#15803d",
];

function getDimensionOptions(teams) {
  if (!teams?.leaders) return { subTeams: [], smallTeams: [] };

  const subTeams = [];
  const smallTeams = [];

  for (const subTeamsMap of Object.values(teams.leaders)) {
    for (const [subTeam, members] of Object.entries(subTeamsMap)) {
      subTeams.push({ name: subTeam, members });
      smallTeams.push(...members);
    }
  }

  return { subTeams, smallTeams };
}

export default function TrendChart({ trendData }) {
  const metrics = trendData?.metrics || {};
  const teams = trendData?.teams;
  const metricKeys = Object.keys(metrics);

  const { subTeams, smallTeams } = useMemo(
    () => getDimensionOptions(teams),
    [teams]
  );

  const [metric, setMetric] = useState(metricKeys[0] || "");
  const [dimension, setDimension] = useState("boss");
  const [selectedSubTeam, setSelectedSubTeam] = useState(
    subTeams[0]?.name || ""
  );
  const [selectedSmallTeam, setSelectedSmallTeam] = useState(
    smallTeams[0] || ""
  );

  // Determine which teams to chart
  // Each entry: { key: dataKey in trend.json, displayName: legend label }
  const chartLines = useMemo(() => {
    if (!metric || !metrics[metric]) return { lines: [], isSubTeam: false };

    if (dimension === "boss") {
      return { lines: [{ key: teams.boss, displayName: teams.boss }], isSubTeam: false };
    }

    if (dimension === "sub") {
      const sub = subTeams.find((s) => s.name === selectedSubTeam);
      if (!sub) return { lines: [], isSubTeam: false };
      const hasCollision = sub.members.includes(sub.name);
      // Small teams as solid lines
      const lines = sub.members.map((m) => ({ key: m, displayName: m }));
      if (hasCollision) {
        // Sub-team aggregate stored under deduped name e.g. "前端创新(2)"
        const dedupedName = `${sub.name}(2)`;
        lines.push({ key: dedupedName, displayName: `${sub.name}(子团队)` });
      } else {
        lines.push({ key: sub.name, displayName: sub.name });
      }
      return { lines, isSubTeam: true, aggregateKey: hasCollision ? `${sub.name}(2)` : sub.name };
    }

    // dimension === "small"
    return { lines: [{ key: selectedSmallTeam, displayName: selectedSmallTeam }], isSubTeam: false };
  }, [dimension, selectedSubTeam, selectedSmallTeam, metric, metrics, teams, subTeams]);

  // Build chart data
  const monthKeys = useMemo(
    () => Object.keys(metrics[metric] || {}).sort(),
    [metric, metrics]
  );

  const chartData = useMemo(() => {
    if (!metric || !metrics[metric]) return [];
    return monthKeys.map((month) => {
      const point = { month };
      const monthData = metrics[metric][month] || {};
      for (const { key } of chartLines.lines) {
        const v = monthData[key];
        point[key] = v != null ? Math.round(v) : null;
      }
      return point;
    });
  }, [monthKeys, metric, metrics, chartLines]);

  if (metricKeys.length === 0) {
    return <div className="trend-chart empty-state">无可用趋势数据</div>;
  }

  return (
    <div className="trend-chart">
      <div className="chart-controls">
        <div className="picker">
          <label>
            指标：
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            >
              {metricKeys.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="picker">
          <label>
            维度：
            <select
              value={dimension}
              onChange={(e) => setDimension(e.target.value)}
            >
              <option value="boss">大团队</option>
              <option value="sub">子团队</option>
              <option value="small">小团队</option>
            </select>
          </label>

          {dimension === "sub" && (
            <select
              value={selectedSubTeam}
              onChange={(e) => setSelectedSubTeam(e.target.value)}
            >
              {subTeams.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          )}

          {dimension === "small" && (
            <select
              value={selectedSmallTeam}
              onChange={(e) => setSelectedSmallTeam(e.target.value)}
            >
              {smallTeams.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {chartLines.lines.length === 0 ? (
        <div className="empty-state">请选择团队</div>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" />
            <YAxis tickFormatter={formatNumber} label={{ value: "千元", angle: -90, position: "insideLeft" }} />
            <Tooltip formatter={(v) => formatNumber(v) + " 千元"} />
            <Legend />
            {chartLines.lines.map(({ key, displayName }, i) => (
              <Line
                key={key}
                name={displayName}
                type="monotone"
                dataKey={key}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                strokeDasharray={
                  chartLines.isSubTeam && key === chartLines.aggregateKey
                    ? "6 3"
                    : undefined
                }
                connectNulls
                dot={{ r: 4 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
