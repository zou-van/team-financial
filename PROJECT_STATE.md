# Project State

Last updated: 2026-07-22

## Current scope

This repository is a static Vite + React dashboard for monthly team financial
data. There is no backend: Excel source workbooks are parsed into generated
data files and bundled into the frontend at build time.

Current generated data covers **2026-02 through 2026-06**. The working tree
contains uncommitted implementation and data updates; treat them as the
current working state, not as merged or deployed changes.

## User-facing behavior

### Monthly detail

- Metrics are rows; team columns are grouped as Leader → sub-team → small team.
- The unit is **千元**. Numeric values use Chinese thousands separators and
  retain up to two decimal places.
- The compact metric column and its toggle column remain fixed while the table
  scrolls horizontally.
- Each sub-team can be collapsed to its aggregate column. 张浩、沈晓华、赵华 can
  each be collapsed to one placeholder column with the header `−` / `+` toggle.
- Aggregate columns use the aggregate styling; negative values use red text.
- In `累计现金流_*` and `PMS预计回款（在途）` rows, numeric cells can be clicked
  to show the month-over-month direction and percentage. The comparison is
  current value minus previous month, divided by the previous absolute value;
  it is unavailable for a missing or zero previous value.

### Trend chart

- Trend metrics are curated through `team-mapping.yaml` → `trend_metrics`.
- The selector supports 大团队、子团队、小团队. A sub-team view renders member
  lines plus its aggregate line (dashed).
- `data/trend.json` is generated from each month's own ordered headers. This is
  required because column positions can change across months.

## Current organization mapping

`team-mapping.yaml` is the source of truth for display order and grouping.

- 张浩 → 交易中台
- 沈晓华 → 营销中台、大前端、前端创新
  - 营销中台：Coupon、多拉、CRM Portal、企微社群
  - CRM Portal belongs under 沈晓华 → 营销中台.
- 赵华 → 线上运营

From **2026-06**, the parser generates calculated display columns (they do not
need to exist in Excel):

- `孙伟（汇总）` in 营销中台, after CRM Portal: Coupon + 多拉 + CRM Portal.
- `钱知麟（汇总）` in 线上运营, after 扁鹊&大禹&商城&预约: PMS&天气中台 + PH点餐 +
  K点餐 + 点餐平台 + Prime + 扁鹊&大禹&商城&预约.

The duplicate sub-team aggregate named `前端创新` is displayed as
`前端创新汇总`.

`notification-config.yaml` keeps notification scopes separate from the data
model. 个人卡收件人：朱孝峰（赵华团队）、彭明阳（营销中台及自动化营销）、郭一鸣
（大前端-APP及前端创新）、张浩（交易中台）。整体卡收件人：孙磊（全局视角 + Leader 摘要 + 风险榜单）。

通知为飞书 Interactive Card 2.0 格式，`scripts/notify.py` 生成 `.cards/人名.json`，
通过 `lark-cli im +messages-send --msg-type interactive` 发送。支持 `card_type: overall`
配置项区分个人卡和整体卡。

每张个人卡片结构：header（标题不含人名，可转发）→ 每 scope 一个 section（分隔线隔开）
→ 2×2 指标卡（PMS在途 / 累计现金流 / 回款目标 / 在途差距）→ 7月现金流预估
→ 负差距红色警告块 → 团队明细（虚拟汇总展开成员缩进列表，独立团队空行分隔）
→ 数据来源脚注。

整体卡片结构：2×2 全局 KPI（合计列）→ 7月预估 → 警告 → Leader 摘要（紧凑行）
→ 风险榜单（现金流最差前3 + 差距最大前3，KPI 卡片风格，小号红色数字）。

消息只提醒需关注的不足，不输出正向结论。团队明细字段顺序：现金流 → 距2倍奖金订单差 →
PMS在途；落后标签用红色加粗。无远程可访问的看板地址，消息末尾用数据来源脚注代替链接。

Notification insights: 使用 latest `累计现金流_*` metric, 正/负现金流状态,
负的 `考虑2倍奖金在途回款差距（+超额/-落后）` → 新订单缺口 + `YYYY-10-15` 出单建议。
`7月现金流预估` 标签：预计转正（绿）/ 仍承压（橙）/ 持续为正（绿）。

发送流程: `python scripts/notify.py` → `lark-cli im +messages-send --user-id ou_xxx
--msg-type interactive --content "$(cat .cards/人名.json)" --as user --dry-run`（去掉
`--dry-run` 正式发送）。收件人 open_id 需通过 `lark-cli contact +search-user` 查询。

## Data pipeline

```text
excel/*.xlsx
  -> scripts/parse.py
  -> data/YYYY-MM.md + data/index.json + data/trend.json
  -> src/lib/loadData.js
  -> React monthly table and trend chart
```

- The parser reads sheet `差距分析(团队)`: headers are on row 2 from column 3;
  row 3 is metadata; data starts on row 4 (column 2 is the metric name).
- It extracts the final six-digit `YYYYMM` from each workbook filename.
- Workbooks are loaded in read-only mode to avoid unnecessary pivot-cache load
  time.
- `data/index.json` and `data/trend.json` are generated files; do not edit them
  directly.

## Key files

| File | Role |
| --- | --- |
| `team-mapping.yaml` | Organization, display order, virtual aggregates, trend whitelist |
| `notification-config.yaml` | Notification recipients and data scopes; not part of parsing |
| `scripts/parse.py` | Excel parsing and generated monthly/index/trend data |
| `src/lib/loadData.js` | Build-time Markdown/JSON loading and column grouping |
| `src/components/MonthlyTable.jsx` | Monthly table, frozen columns, expand/collapse behavior |
| `src/components/TrendChart.jsx` | Curated-metric Recharts trend chart |
| `src/App.css` | Current Refero/Dub-inspired visual system |

## Commands

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite development server on port 5173 |
| `npm run build` | Verify a production build |
| `python scripts/parse.py` | Regenerate data after Excel or mapping changes |

After running the parser, restart the development server or rebuild so Vite
picks up changed Markdown files.

## Invariants and checks

- Keep duplicate-name logic in `scripts/parse.py` and
  `src/lib/loadData.js` synchronized. The custom display alias for an
  aggregate is controlled by `aggregate_column_names`.
- Keep `assetsInclude: ['**/*.md']` in `vite.config.js`.
- Preserve Excel error values (such as `#REF!` and `#DIV/0!`) as display text.
- After changing parsing, mapping, or generated data, run the parser and review
  the generated diffs. After frontend changes, run `npm run build`.

## Working tree status

As of this update, the implementation, generated data for 2026-04 through
2026-06, and design updates are uncommitted. No deployment or commit status is
asserted by this document.
