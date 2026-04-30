# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

| Command | Purpose |
|---|---|
| `npm run dev` | Start Vite dev server on port 5173 |
| `npm run build` | Production build to `dist/` |
| `python scripts/parse.py` | Parse all `.xlsx` in `excel/` → `data/*.md` + `data/index.json` |

After running `parse.py`, restart the dev server or rebuild to pick up new `.md` files.

Python dependencies: `openpyxl`, `pyyaml`.

## Architecture

Static SPA dashboard for monthly team financial data. Zero backend — all data is bundled at build time via `import.meta.glob`.

```
excel/*.xlsx  →  scripts/parse.py  →  data/YYYY-MM.md + data/index.json
                                              ↓
                                    Vite import.meta.glob (eager, ?raw)
                                              ↓
                              src/lib/loadData.js → parseMarkdown.js
                                              ↓
                                    React components (App.jsx)
```

**Two views:** monthly table (single big table, metrics as rows, teams as columns) and trend chart (Recharts line chart).

**Team hierarchy:** `team-mapping.yaml` defines `boss` → `leaders` → `sub-team` → `[small teams]`. The mapping controls column ordering and the three-level table headers. The Python parser copies the mapping into `index.json` so the frontend doesn't need to parse YAML.

## Critical details

**Excel parsing assumptions** (in `scripts/parse.py`):
- Target sheet: `差距分析(团队)` (hardcoded)
- Headers: row 2, columns 3+
- Data: starts row 4, col 1 = section name (ignored), col 2 = metric name, cols 3+ = values
- Row 3 is skipped (metadata)
- Filename date: last 6-digit number extracted via regex `(\d{6})`

**`assetsInclude: ['**/*.md']` in `vite.config.js`** is required for the `.md` glob import. Do not remove it.

**Name dedup exists in TWO places** and must stay in sync:
- `scripts/parse.py` → `parse_excel()`: when Excel has duplicate header names
- `src/lib/loadData.js` → `buildColumnGroups()`: when building column groups for table headers

Both rename duplicates by appending `(2)`, `(3)`, etc. If you change this logic in one place, you must mirror it in the other.

**Aggregate column styling:** columns identified in `buildColumnGroups().aggregateColumns` get `class="aggregate"` (bold + blue background). Negative values get `class="negative"` (red text).

**Error values** from Excel (e.g., `#REF!`, `#DIV/0!`) pass through as strings and display literally in the UI.
