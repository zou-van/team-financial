import { useState } from "react";
import { buildColumnGroups } from "../lib/loadData";

/* ------------------------------------------------------------------ */
/*  group definitions                                                  */
/* ------------------------------------------------------------------ */

function findMetric(metrics, rule) {
  if (typeof rule === "string") {
    return metrics[rule] ? { name: rule, data: metrics[rule] } : null;
  }
  for (const [name, data] of Object.entries(metrics)) {
    if (rule.prefix && name.startsWith(rule.prefix)) return { name, data };
    if (rule.suffix && name.endsWith(rule.suffix)) return { name, data };
  }
  return null;
}

const GROUPS = [
  {
    rows: [
      "回款目标（实发奖金口径）",
      { prefix: "25年奖金发放" },
      "26年2倍奖金计提",
      "回款目标（考虑2倍奖金）",
      { prefix: "累计现金流_" },
    ],
  },
  {
    rows: [
      {
        expandable: true,
        parent: { prefix: "回款YTD合计" },
        children: ["25年结转", "26年回款"],
      },
      "PMS预计回款（在途）",
      "内部划账（已刷新目标）",
    ],
  },
  {
    rows: [
      "每月需回款",
      "全年回款差距（+超额/-落后）",
      "考虑在途回款差距（+超额/-落后）",
      "全年回款差距（+超额/-落后）-2倍奖金",
      "考虑2倍奖金在途回款差距（+超额/-落后）",
    ],
  },
  {
    rows: [
      { suffix: "月现金支出" },
      { suffix: "月回款预估" },
      { suffix: "月现金流预估" },
    ],
  },
];

const GROUP_COLORS = ["#f0fdf4", "#eff6ff", "#fefce8", "#fef2f2"];

/* ------------------------------------------------------------------ */
/*  helpers                                                            */
/* ------------------------------------------------------------------ */

function resolveGroups(metrics) {
  return GROUPS.map((group) =>
    group.rows
      .map((rule) => {
        if (rule.expandable) {
          const parent = findMetric(metrics, rule.parent);
          if (!parent) return null;
          const childEntries = rule.children
            .map((c) => findMetric(metrics, c))
            .filter(Boolean);
          return { ...parent, expandable: true, children: childEntries };
        }
        return findMetric(metrics, rule);
      })
      .filter(Boolean),
  );
}

/** Build lookup: column name → { subTeam, isAggregate } */
function buildColumnInfo(colGroups) {
  if (!colGroups) return {};
  const info = {};
  for (const g of colGroups.groups) {
    for (const sg of g.subGroups) {
      const cols = sg.columns;
      for (let i = 0; i < cols.length; i++) {
        info[cols[i]] = { subTeam: sg.subTeam, isAggregate: i === cols.length - 1 };
      }
    }
  }
  return info;
}

function renderRows(
  resolvedGroups,
  orderedHeaders,
  aggregateCols,
  visibleColCount,
  ytdExpanded,
  toggleYtd,
  hiddenCols,
) {
  const rows = [];

  resolvedGroups.forEach((groupRows, gi) => {
    if (gi > 0) {
      rows.push(
        <tr key={`spacer-${gi}`} className="section-spacer">
          <td colSpan={visibleColCount} />
        </tr>,
      );
    }

    groupRows.forEach((item) => {
      if (item.expandable) {
        rows.push(
          <tr
            key={item.name}
            style={{ backgroundColor: GROUP_COLORS[gi] }}
          >
            <td className="toggle-cell">
              <button
                className="row-toggle"
                onClick={toggleYtd}
                title={ytdExpanded ? "收起" : "展开"}
              >
                {ytdExpanded ? "−" : "+"}
              </button>
            </td>
            <th className="metric-label">{item.name}</th>
            {orderedHeaders.map((h) => {
              if (hiddenCols.has(h)) return null;
              const idx = item.data.headers.indexOf(h);
              const v = idx >= 0 ? item.data.values[idx] : null;
              const cls = cellClass(h, v, aggregateCols);
              return (
                <td key={h} className={cls || undefined}>
                  {v === null || v === undefined ? "-" : v}
                </td>
              );
            })}
          </tr>,
        );

        if (ytdExpanded) {
          item.children.forEach((child) => {
            rows.push(
              <tr
                key={child.name}
                style={{ backgroundColor: GROUP_COLORS[gi] }}
              >
                <td className="toggle-cell" />
                <th className="metric-label child">{child.name}</th>
                {orderedHeaders.map((h) => {
                  if (hiddenCols.has(h)) return null;
                  const idx = child.data.headers.indexOf(h);
                  const v =
                    idx >= 0 ? child.data.values[idx] : null;
                  const cls = cellClass(h, v, aggregateCols);
                  return (
                    <td key={h} className={cls || undefined}>
                      {v === null || v === undefined ? "-" : v}
                    </td>
                  );
                })}
              </tr>,
            );
          });
        }
      } else {
        rows.push(
          <tr
            key={item.name}
            style={{ backgroundColor: GROUP_COLORS[gi] }}
          >
            <td className="toggle-cell" />
            <th className="metric-label">{item.name}</th>
            {orderedHeaders.map((h) => {
              if (hiddenCols.has(h)) return null;
              const idx = item.data.headers.indexOf(h);
              const v = idx >= 0 ? item.data.values[idx] : null;
              const cls = cellClass(h, v, aggregateCols);
              return (
                <td key={h} className={cls || undefined}>
                  {v === null || v === undefined ? "-" : v}
                </td>
              );
            })}
          </tr>,
        );
      }
    });
  });

  return rows;
}

/* ------------------------------------------------------------------ */
/*  component                                                          */
/* ------------------------------------------------------------------ */

export default function MonthlyTable({ data, mapping }) {
  if (!data) {
    return <div className="empty-state">请选择月份查看数据</div>;
  }

  const { title, metrics } = data;
  const colGroups = buildColumnGroups(mapping);
  const aggregateCols = new Set(colGroups?.aggregateColumns || []);

  const metricEntries = Object.entries(metrics);
  const firstEntry = metricEntries[0];
  const orderedHeaders = firstEntry ? firstEntry[1].headers : [];

  const resolvedGroups = resolveGroups(metrics);
  const [ytdExpanded, setYtdExpanded] = useState(false);
  const [collapsedSubTeams, setCollapsedSubTeams] = useState(new Set());

  const toggleYtd = () => setYtdExpanded((prev) => !prev);

  const toggleSubTeam = (name) => {
    setCollapsedSubTeams((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const columnInfo = buildColumnInfo(colGroups);

  // Build set of hidden columns (small team columns of collapsed sub-teams)
  const hiddenCols = new Set();
  if (colGroups) {
    for (const g of colGroups.groups) {
      for (const sg of g.subGroups) {
        if (collapsedSubTeams.has(sg.subTeam)) {
          const cols = sg.columns;
          // All columns except the last (aggregate) are hidden
          for (let i = 0; i < cols.length - 1; i++) {
            hiddenCols.add(cols[i]);
          }
        }
      }
    }
  }

  const visibleColCount = 2 + orderedHeaders.length - hiddenCols.size;

  return (
    <div className="monthly-table">
      <h2>{title}</h2>

      <div className="table-wrapper">
        <table>
          {colGroups ? (
            <GroupedHeader
              colGroups={colGroups}
              columnInfo={columnInfo}
              collapsedSubTeams={collapsedSubTeams}
              toggleSubTeam={toggleSubTeam}
              hiddenCols={hiddenCols}
            />
          ) : (
            <SimpleHeader headers={orderedHeaders} />
          )}
          <tbody>
            {renderRows(
              resolvedGroups,
              orderedHeaders,
              aggregateCols,
              visibleColCount,
              ytdExpanded,
              toggleYtd,
              hiddenCols,
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  cell helpers                                                        */
/* ------------------------------------------------------------------ */

function cellClass(header, value, aggregateCols) {
  const cls = [];
  if (aggregateCols.has(header)) cls.push("aggregate");
  if (typeof value === "number" && value < 0) cls.push("negative");
  return cls.join(" ");
}

/* ------------------------------------------------------------------ */
/*  header components                                                   */
/* ------------------------------------------------------------------ */

function GroupedHeader({
  colGroups,
  columnInfo,
  collapsedSubTeams,
  toggleSubTeam,
  hiddenCols,
}) {
  const { groups, boss } = colGroups;

  return (
    <thead>
      {/* Row 1: Leader names */}
      <tr>
        <th rowSpan={3} className="toggle-col"></th>
        <th rowSpan={3} className="metric-header">指标</th>
        {groups.map((g) => {
          const visibleCount = g.subGroups.reduce((sum, sg) => {
            if (collapsedSubTeams.has(sg.subTeam)) return sum + 1;
            return sum + sg.columns.length;
          }, 0);
          return (
            <th key={g.leader} colSpan={visibleCount}>
              {g.leader}
            </th>
          );
        })}
        <th rowSpan={3}>{boss}</th>
      </tr>

      {/* Row 2: Sub team names + toggle */}
      <tr>
        {groups.map((g) =>
          g.subGroups.map((sg) => {
            const collapsed = collapsedSubTeams.has(sg.subTeam);
            const visibleCount = collapsed ? 1 : sg.columns.length;
            return (
              <th key={sg.subTeam} colSpan={visibleCount}>
                <button
                  className="sub-toggle"
                  onClick={() => toggleSubTeam(sg.subTeam)}
                  title={collapsed ? "展开" : "收起"}
                >
                  {collapsed ? "+" : "−"}
                </button>
                {sg.subTeam}
              </th>
            );
          }),
        )}
      </tr>

      {/* Row 3: Individual column names */}
      <tr>
        {groups.map((g) =>
          g.subGroups.map((sg) =>
            sg.columns.map((col) => {
              if (hiddenCols.has(col)) return null;
              return (
                <th key={col}>
                  {col}
                </th>
              );
            }),
          ),
        )}
      </tr>
    </thead>
  );
}

function SimpleHeader({ headers }) {
  return (
    <thead>
      <tr>
        <th className="toggle-col"></th>
        <th>指标</th>
        {headers.map((h) => (
          <th key={h}>{h}</th>
        ))}
      </tr>
    </thead>
  );
}
