import { useState } from "react";
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
import MetricPicker from "./MetricPicker";
import TeamPicker from "./TeamPicker";
import { getTeamList } from "../lib/loadData";

const COLORS = [
  "#2563eb", "#dc2626", "#16a34a", "#ca8a04", "#9333ea",
  "#0891b2", "#d97706", "#4f46e5", "#be123c", "#15803d",
];

export default function TrendChart({ months, index }) {
  const metrics = index?.metrics || [];
  const teams = getTeamList(index);

  const [metric, setMetric] = useState(metrics[0] || "");
  const [selectedTeams, setSelectedTeams] = useState(
    index?.teams?.boss ? [index.teams.boss] : []
  );

  const monthKeys = Object.keys(months).sort();

  // Build chart data: [{ month, "团队A": value, "团队B": value, ... }, ...]
  const chartData = monthKeys.map((month) => {
    const point = { month };
    const monthData = months[month];
    if (!monthData || !monthData.metrics[metric]) return point;

    const { headers, values } = monthData.metrics[metric];
    for (const team of selectedTeams) {
      const idx = headers.indexOf(team);
      point[team] = idx >= 0 ? values[idx] : null;
    }
    return point;
  });

  return (
    <div className="trend-chart">
      <div className="chart-controls">
        <MetricPicker
          metrics={metrics}
          selected={metric}
          onChange={setMetric}
        />
        <TeamPicker
          teams={teams}
          selected={selectedTeams}
          onChange={setSelectedTeams}
        />
      </div>

      {selectedTeams.length === 0 ? (
        <div className="empty-state">请至少选择一个团队</div>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="month" />
            <YAxis />
            <Tooltip />
            <Legend />
            {selectedTeams.map((team, i) => (
              <Line
                key={team}
                type="monotone"
                dataKey={team}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
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
