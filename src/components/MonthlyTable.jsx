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
const CUMULATIVE_CASH_FLOW_PREFIX = "累计现金流_";
const PMS_FORECAST_NAME = "PMS预计回款（在途）";

function formatValue(value) {
  if (typeof value !== "number") return value ?? "-";
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
  }).format(value);
}

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

function isMonthOverMonthMetric(name) {
  return name.startsWith(CUMULATIVE_CASH_FLOW_PREFIX) || name === PMS_FORECAST_NAME;
}

function getPreviousMetric(metrics, metricName) {
  if (!metrics) return null;
  if (metricName.startsWith(CUMULATIVE_CASH_FLOW_PREFIX)) {
    return Object.entries(metrics).find(([name]) =>
      name.startsWith(CUMULATIVE_CASH_FLOW_PREFIX),
    )?.[1];
  }
  return metrics[metricName] || null;
}

function getMonthOverMonth(item, header, months, selectedMonth) {
  const previousMonth = Object.keys(months)
    .filter((month) => month < selectedMonth)
    .sort()
    .at(-1);
  const previousMetric = getPreviousMetric(
    previousMonth ? months[previousMonth]?.metrics : null,
    item.name,
  );
  const previousIndex = previousMetric?.headers.indexOf(header);
  const previousValue = previousIndex >= 0
    ? previousMetric.values[previousIndex]
    : null;

  if (typeof previousValue !== "number") return "暂无上月可比数据";
  if (previousValue === 0) return "上月为 0，无法计算环比";

  const currentIndex = item.data.headers.indexOf(header);
  const currentValue = item.data.values[currentIndex];
  const difference = currentValue - previousValue;
  const percentage = Math.abs(difference / Math.abs(previousValue) * 100).toFixed(2);

  if (difference > 0) return `上升 ${percentage}%`;
  if (difference < 0) return `下降 ${percentage}%`;
  return "持平 0.00%";
}

/** Build lookup: column name → { leader, subTeam, isAggregate } */
function buildColumnInfo(colGroups) {
  if (!colGroups) return {};
  const info = {};
  for (const g of colGroups.groups) {
    for (const sg of g.subGroups) {
      const cols = sg.columns;
      for (let i = 0; i < cols.length; i++) {
        info[cols[i]] = {
          leader: g.leader,
          subTeam: sg.subTeam,
          isAggregate: i === cols.length - 1,
        };
      }
    }
  }
  return info;
}

function renderValueCells(
  item,
  orderedHeaders,
  aggregateCols,
  hiddenCols,
  columnInfo,
  collapsedLeaders,
  months,
  selectedMonth,
  activeMomCell,
  toggleMomCell,
) {
  const renderedCollapsedLeaders = new Set();

  return orderedHeaders.map((h) => {
    const leader = columnInfo[h]?.leader;
    if (leader && collapsedLeaders.has(leader)) {
      if (renderedCollapsedLeaders.has(leader)) return null;
      renderedCollapsedLeaders.add(leader);
      return <td key={`collapsed-${leader}`} className="collapsed-leader-cell" />;
    }

    if (hiddenCols.has(h)) return null;
    const idx = item.data.headers.indexOf(h);
    const value = idx >= 0 ? item.data.values[idx] : null;
    const cls = cellClass(h, value, aggregateCols);
    const isComparable = isMonthOverMonthMetric(item.name) && typeof value === "number";
    const cellKey = `${item.name}:${h}`;
    return (
      <td key={h} className={`${cls} ${isComparable ? "mom-cell" : ""}`.trim() || undefined}>
        {isComparable ? (
          <>
            <button
              className="mom-value"
              onClick={() => toggleMomCell(cellKey)}
              title="点击查看环比"
              aria-expanded={activeMomCell === cellKey}
            >
              {formatValue(value)}
            </button>
            {activeMomCell === cellKey && (
              <span className="mom-popover" role="status">
                环比：{getMonthOverMonth(item, h, months, selectedMonth)}
              </span>
            )}
          </>
        ) : formatValue(value)}
      </td>
    );
  });
}

function renderRows(
  resolvedGroups,
  orderedHeaders,
  aggregateCols,
  visibleColCount,
  ytdExpanded,
  toggleYtd,
  hiddenCols,
  columnInfo,
  collapsedLeaders,
  months,
  selectedMonth,
  activeMomCell,
  toggleMomCell,
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
            <th className="metric-label" title={item.name}>{item.name}</th>
            {renderValueCells(item, orderedHeaders, aggregateCols, hiddenCols, columnInfo, collapsedLeaders, months, selectedMonth, activeMomCell, toggleMomCell)}
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
                <th className="metric-label child" title={child.name}>{child.name}</th>
                {renderValueCells(child, orderedHeaders, aggregateCols, hiddenCols, columnInfo, collapsedLeaders, months, selectedMonth, activeMomCell, toggleMomCell)}
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
            <th className="metric-label" title={item.name}>{item.name}</th>
            {renderValueCells(item, orderedHeaders, aggregateCols, hiddenCols, columnInfo, collapsedLeaders, months, selectedMonth, activeMomCell, toggleMomCell)}
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

export default function MonthlyTable({ data, mapping, months, selectedMonth }) {
  if (!data) {
    return <div className="empty-state">请选择月份查看数据</div>;
  }

  const { title, metrics } = data;
  const metricEntries = Object.entries(metrics);
  const firstEntry = metricEntries[0];
  const orderedHeaders = firstEntry ? firstEntry[1].headers : [];
  const colGroups = buildColumnGroups(mapping, orderedHeaders);
  const aggregateCols = new Set(colGroups?.aggregateColumns || []);

  const resolvedGroups = resolveGroups(metrics);
  const [ytdExpanded, setYtdExpanded] = useState(false);
  const [collapsedSubTeams, setCollapsedSubTeams] = useState(new Set());
  const [collapsedLeaders, setCollapsedLeaders] = useState(new Set());
  const [activeMomCell, setActiveMomCell] = useState(null);

  const toggleYtd = () => setYtdExpanded((prev) => !prev);

  const toggleSubTeam = (name) => {
    setCollapsedSubTeams((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const toggleLeader = (name) => {
    setCollapsedLeaders((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const toggleMomCell = (cellKey) => {
    setActiveMomCell((current) => current === cellKey ? null : cellKey);
  };

  const columnInfo = buildColumnInfo(colGroups);

  // Build set of hidden columns (small team columns of collapsed sub-teams)
  const hiddenCols = new Set();
  if (colGroups) {
    for (const g of colGroups.groups) {
      for (const sg of g.subGroups) {
        if (collapsedLeaders.has(g.leader)) {
          sg.columns.forEach((column) => hiddenCols.add(column));
          continue;
        }
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

  const visibleColCount = 2 + orderedHeaders.length - hiddenCols.size + collapsedLeaders.size;

  return (
    <div className="monthly-table">
      <div className="section-heading">
        <h2>{title}</h2>
        <span className="unit-label">单位：千元</span>
      </div>

      <div className="table-wrapper">
        <table>
          {colGroups ? (
            <GroupedHeader
              colGroups={colGroups}
              columnInfo={columnInfo}
              collapsedLeaders={collapsedLeaders}
              toggleLeader={toggleLeader}
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
              columnInfo,
              collapsedLeaders,
              months,
              selectedMonth,
              activeMomCell,
              toggleMomCell,
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
  collapsedLeaders,
  toggleLeader,
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
          const collapsed = collapsedLeaders.has(g.leader);
          const visibleCount = collapsed
            ? 1
            : g.subGroups.reduce((sum, sg) => {
                if (collapsedSubTeams.has(sg.subTeam)) return sum + 1;
                return sum + sg.columns.length;
              }, 0);
          return (
            <th key={g.leader} colSpan={visibleCount}>
              <button
                className="leader-toggle"
                onClick={() => toggleLeader(g.leader)}
                title={collapsed ? "展开" : "收起"}
              >
                {collapsed ? "+" : "−"}
              </button>
              {g.leader}
            </th>
          );
        })}
        <th rowSpan={3}>{boss}</th>
      </tr>

      {/* Row 2: Sub team names + toggle */}
      <tr>
        {groups.map((g) => {
          if (collapsedLeaders.has(g.leader)) {
            return <th key={g.leader} rowSpan={2} className="collapsed-leader-placeholder" />;
          }
          return g.subGroups.map((sg) => {
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
          });
        })}
      </tr>

      {/* Row 3: Individual column names */}
      <tr>
        {groups.map((g) => {
          if (collapsedLeaders.has(g.leader)) return null;
          return g.subGroups.map((sg) =>
            sg.columns.map((col) => {
              if (hiddenCols.has(col)) return null;
              return (
                <th key={col}>
                  {col}
                </th>
              );
            }),
          );
        })}
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
