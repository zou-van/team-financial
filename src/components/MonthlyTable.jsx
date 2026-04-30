import { buildColumnGroups } from "../lib/loadData";

export default function MonthlyTable({ data, mapping }) {
  if (!data) {
    return <div className="empty-state">请选择月份查看数据</div>;
  }

  const { title, metrics } = data;
  const colGroups = buildColumnGroups(mapping);

  return (
    <div className="monthly-table">
      <h2>{title}</h2>

      {Object.entries(metrics).map(([metricName, { headers, values }]) => (
        <div key={metricName} className="metric-section">
          <h3>{metricName}</h3>
          <div className="table-wrapper">
            <table>
              {colGroups ? (
                <GroupedHeader colGroups={colGroups} />
              ) : (
                <SimpleHeader headers={headers} />
              )}
              <tbody>
                <tr>
                  {values.map((v, i) => (
                    <td key={i}>
                      {v === null || v === undefined ? "-" : v}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

function GroupedHeader({ colGroups }) {
  const { groups, boss } = colGroups;

  return (
    <thead>
      {/* Row 1: Leader names */}
      <tr>
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
        {headers.map((h) => (
          <th key={h}>{h}</th>
        ))}
      </tr>
    </thead>
  );
}
