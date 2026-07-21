# Trend Chart Redesign

Date: 2026-05-01

## Problem

Current trend chart shows all 50+ metrics and lets users pick any team combination. This is unwieldy — most metrics don't need trend visualization, and the team picker is confusing.

## Solution

Restrict trend chart to a curated set of metrics, and replace the team checkbox picker with a dimension-based selector (pick a group, see all members as lines).

## 1. Configuration — `team-mapping.yaml`

Add `trend_metrics` section at the end:

```yaml
trend_metrics:
  - 回款目标（实发奖金口径）
  - 回款目标（考虑2倍奖金）
  - 累计现金流
  - PMS预计回款（在途）
  - 考虑在途回款差距（+超额/-落后）
  - 考虑2倍奖金在途回款差距（+超额/-落后）
```

Matching logic in parse.py: exact match against index.json metrics list first; if no exact match, use as prefix to match metrics like `累计现金流_2026.3.31`.

## 2. Data Generation — parse.py → `data/trend.json`

parse.py reads `trend_metrics` from team-mapping.yaml, matches against each month's parsed data, and generates `data/trend.json`:

```json
{
  "metrics": {
    "累计现金流": {
      "2026-02": { "合计": 1000, "交易中台": 500, "订单&选店": 300 },
      "2026-03": { "合计": 800, "交易中台": 400, "订单&选店": 250 }
    }
  },
  "teams": { /* same structure as index.json teams */ }
}
```

- `metrics`: keyed by whitelist name (not raw Excel name), value is month → team → number
- `teams`: copied from the generated index.json teams structure

Frontend imports via `import trendData from "/data/trend.json"` (Vite JSON import, no special config needed).

Each month is paired with its own parsed ordered headers before this JSON is
generated. Do not reuse a single month's column positions for all months:
organization changes and virtual aggregate columns can change later months'
column order.

## 3. UI — TrendChart Component

### Metric Picker

Dropdown, populated from `Object.keys(trendData.metrics)`. Default: first item.

### Team Dimension Picker

Two-level dropdown:

| Level 1 | Level 2 options | Lines shown |
|---------|----------------|-------------|
| 大团队 | 合计 | 1 line |
| 子团队 | 交易中台, 营销中台, 大前端, 前端创新, 线上运营 | small teams + sub-team aggregate |
| 小团队 | 订单&选店, Promotion, 礼品卡, ... | 1 line |

When a sub-team is selected, the chart shows:
- One line per small team (solid)
- One line for the sub-team aggregate (dashed)

If a sub-team aggregate shares a name with one of its small teams, use the
configured display key from `aggregate_column_names` (for example,
`前端创新汇总`) for the aggregate line.

Virtual aggregates are carried into `trend.json` from their configured start
month, but they are not added as selectable small-team lines unless the product
requirements change.

### Removed

- `MetricPicker.jsx` — no longer needed
- `TeamPicker.jsx` — replaced by the dimension picker
- `getTeamList()` in loadData.js — no longer needed by TrendChart (MonthlyTable doesn't use it)

### Data Flow

```
trend.json → TrendChart
                ↓
  metric picker → metrics[metric] → all months' data for that metric
  team picker   → filter to selected group's teams → chart lines
```

## Files Changed

| File | Change |
|------|--------|
| `team-mapping.yaml` | Add `trend_metrics` section |
| `scripts/parse.py` | Read trend_metrics, generate `data/trend.json` |
| `data/trend.json` | New generated file |
| `src/components/TrendChart.jsx` | New metric picker + dimension picker, read trend.json |
| `src/components/MetricPicker.jsx` | Delete |
| `src/components/TeamPicker.jsx` | Delete |
| `src/lib/loadData.js` | Remove `getTeamList()` |
| `src/App.jsx` | Update TrendChart props (pass trendData instead of months+index) |
