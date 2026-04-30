import { buildColumnGroups } from "../lib/loadData";

export default function MonthlyTable({ data, mapping }) {
  if (!data) {
    return <div className="empty-state">请选择月份查看数据</div>;
  }

  const { title, metrics } = data;
  const colGroups = buildColumnGroups(mapping);

  // Build set of aggregate column names from colGroups output
  const aggregateCols = new Set(colGroups?.aggregateColumns || []);

  const metricEntries = Object.entries(metrics);
  const firstEntry = metricEntries[0];
  const orderedHeaders = firstEntry ? firstEntry[1].headers : [];

  return (
    <div className="monthly-table">
      <h2>{title}</h2>
      <div className="table-wrapper">
        <table>
          {colGroups ? (
            <GroupedHeader colGroups={colGroups} />
          ) : (
            <SimpleHeader headers={orderedHeaders} />
          )}
          <tbody>
            {metricEntries.map(([metricName, { headers, values }]) => (
              <tr key={metricName}>
                <th className="metric-label">{metricName}</th>
                {headers.map((h) => {
                  const idx = orderedHeaders.indexOf(h);
                  const v = idx >= 0 ? values[idx] : null;
                  const isAggregate = aggregateCols.has(h);
                  const isNegative = typeof v === "number" && v < 0;
                  const cls = [
                    isAggregate ? "aggregate" : "",
                    isNegative ? "negative" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <td key={h} className={cls || undefined}>
                      {v === null || v === undefined ? "-" : v}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GroupedHeader({ colGroups }) {
  const { groups, boss } = colGroups;

  return (
    <thead>
      {/* Row 1: Leader names */}
      <tr>
        <th rowSpan={3}>指标</th>
        {groups.map((g) => {
          const span = g.subGroups.reduce(
            (s, sg) => s + sg.columns.length,
            0
          );
          return (
            <th key={g.leader} colSpan={span}>
              {g.leader}
            </th>
          );
        })}
        <th rowSpan={3}>{boss}</th>
      </tr>

      {/* Row 2: Sub team names */}
      <tr>
        {groups.map((g) =>
          g.subGroups.map((sg) => (
            <th key={sg.subTeam} colSpan={sg.columns.length}>
              {sg.subTeam}
            </th>
          ))
        )}
      </tr>

      {/* Row 3: Individual column names */}
      <tr>
        {groups.map((g) =>
          g.subGroups.map((sg) =>
            sg.columns.map((col) => <th key={col}>{col}</th>)
          )
        )}
      </tr>
    </thead>
  );
}

function SimpleHeader({ headers }) {
  return (
    <thead>
      <tr>
        <th>指标</th>
        {headers.map((h) => (
          <th key={h}>{h}</th>
        ))}
      </tr>
    </thead>
  );
}
