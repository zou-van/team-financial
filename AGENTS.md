# AGENTS.md

> **First action in every session:** Read `PROJECT_STATE.md` for the latest project status, uncommitted changes, and pending work. Then check `git status` and `git diff` to confirm nothing has drifted.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

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
