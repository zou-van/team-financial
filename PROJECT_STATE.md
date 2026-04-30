# Project State

Last updated: 2026-04-30

## What's Built

Team financial data dashboard — static SPA with Vite + React. Parses monthly Excel files into Markdown, bundles at build time via `import.meta.glob`.

### Two views
- **月度详情** — single big table, metrics as rows, teams as columns, 3-level headers (Leader → Sub Team → Individual Team)
- **趋势图** — line chart (Recharts), selectable metrics and teams

### Features implemented
- Excel → Markdown parsing (`scripts/parse.py`)
- Monthly table with grouped headers (`src/components/MonthlyTable.jsx`)
- Trend chart with metric/team pickers (`src/components/TrendChart.jsx`)
- Per-metric-row collapse/expand toggle (click "−"/"+" button)
- Aggregate columns (subteam/boss) styled bold with blue background
- Negative numbers displayed in red
- Name deduplication for duplicate Excel headers (in both parse.py and loadData.js)

## Uncommitted Changes

| File | Change |
|------|--------|
| `CLAUDE.md` | Added behavioral guidelines (sections 1-4) |
| `data/index.json` | Generated from parse.py run |
| `src/App.css` | Added `.row-toggle`, `.row-collapsed` styles |
| `src/components/MonthlyTable.jsx` | Added collapse/expand toggle feature |

### Untracked
- `excel/EC团队经营数据汇总202603.xlsx` — one month of source data
- `docs/` — superpowers specs/plans from earlier design phase

## Data Pipeline

```
excel/*.xlsx → scripts/parse.py → data/YYYY-MM.md + data/index.json
                                         ↓
                               Vite import.meta.glob (eager, ?raw)
                                         ↓
                           src/lib/loadData.js → parseMarkdown.js
                                         ↓
                                 React components
```

## Key Files

| File | Role |
|------|------|
| `scripts/parse.py` | Excel → Markdown + index.json |
| `team-mapping.yaml` | Org hierarchy, user-maintained |
| `src/lib/loadData.js` | Build-time data loading, column grouping |
| `src/lib/parseMarkdown.js` | Markdown → JS objects |
| `src/App.jsx` | Root component, month/view state |
| `src/components/MonthlyTable.jsx` | Monthly detail table |
| `src/components/TrendChart.jsx` | Trend line chart |
| `src/App.css` | All styles |

## Commands

| Command | Purpose |
|---------|---------|
| `npm run dev` | Dev server on port 5173 |
| `npm run build` | Production build to `dist/` |
| `python scripts/parse.py` | Parse Excel files → data/ |

## Known Constraints

- Target Excel sheet hardcoded as `差距分析(团队)`
- Name dedup logic exists in TWO places (`parse.py` + `loadData.js`), must stay in sync
- `assetsInclude: ['**/*.md']` in `vite.config.js` is required for .md imports
- Only one month of data (2026-03) currently available — trend chart has limited utility
