# Project State

Last updated: 2026-07-27

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

## Task status

### ✅ 已完成

- **整体卡** (2026-07-22)：`scripts/notify.py` → `build_overall_card()` 已实现，收件人孙磊。
  结构：2×2 全局 KPI → 7月现金流预估 → 警告块 → Leader 摘要（紧凑行）→ 风险榜单（现金流最差前3 + 差距最大前3）→ 数据来源脚注。
- **张浩个人卡**：已实现，收件人张浩（交易中台）。
- **个人卡 v2.0**：已实现，支持 `notification-config.yaml` 中 `card_type: overall` 区分整体卡/个人卡，
  个人卡结构含 scope sections、2×2 指标卡、7月现金流预估、负差距警告、团队明细（虚拟汇总展开）。
- **风险榜单**：已在整体卡中实现，KPI 卡片风格，现金流最差 & 差距最大各前3。
- **Trend chart redesign**：curated metrics + 维度选择器（大团队/子团队/小团队）。
- **Virtual aggregates**：`孙伟（汇总）`、`钱知麟（汇总）`、`前端创新汇总` 已在 parser 中生成。
- **2026-04/05/06 数据**：已入库。

### 🟠 当前进行中：轻量知识图谱洞察系统

- **目标**：为整体卡增加可追溯的管理层数据解读，优先回答“哪些团队需关注、谁负责、什么指标触发、建议做什么”。
- **已确认方案**：采用“结构化规则知识 + 当月事实图”的轻量实现，不引入图数据库；LLM 负责基于规则和事实生成表达，规则分析作为兜底。
  - 新增 `knowledge-graph.yaml`：维护团队负责人、风险规则、解释模板与建议行动等长期知识。
  - 新增 `scripts/insights.py`：读取最新月度数据与组织映射，匹配风险规则，并将排名前三团队事实与知识规则交给 DeepSeek 生成管理层洞察。
  - 生成 `data/knowledge-graph-latest.json`：保存当月命中的团队、负责人、指标值、风险与行动建议。
  - `scripts/notify.py` 消费该结果，为整体卡生成管理洞察；模型调用失败时回退到规则洞察。
- **首批固定查询**：
  1. 本月哪些团队触发高风险？
  2. 每项风险由谁负责、相关数值是多少？
  3. 每项风险建议下一步做什么？
- **实施顺序**：先共同确定首批 5 条风险规则，再实现 YAML 结构、洞察生成脚本和整体卡接入；后续再按需要增加订单、项目、会议纪要和时间趋势节点。

### 当前实现与待优化

- 首批 3 类业务规则已确定并实现：累计现金流为负、PMS 在途覆盖现金流缺口关系、10 月底前考虑 2 倍奖金的出单进度。
- `knowledge-graph.yaml`、`scripts/insights.py`、`data/knowledge-graph-latest.json` 已建立，整体卡已接入管理层洞察。
- 所有消息卡 KPI 顺序统一为：累计现金流 → PMS预计回款（在途）→ 回款目标（2倍奖金）→ 在途单回款差距（2倍奖金）。
- 整体卡当前顺序为：Leader 摘要 → 风险榜单 → 财务数据洞察；Leader 摘要顺序为现金流 → 下月预计现金流 → PMS在途 → 2倍奖金差距。当前版本已发送给用户和孙磊验证。
- 财务数据洞察已拆成“现金流分析”和“全年订单分析”两个 topic，只分析风险榜单前 3 个不同团队；每个指标后紧跟对应动作。
- 洞察表达改为按指标连续分析，不再分“风险 / 措施”两栏：现金流指标后紧跟现金流判断，PMS 在途指标后紧跟“严格追踪在途单回款情况”，2 倍奖金差距后紧跟出单计划判断和业务 Owner 动作。
- 2 倍奖金缺口的卡片文案不展示计算出的进度差额，只说明当前差距代表未按出单计划推进、今年财务目标存在无法完成风险，并提示与业务 Owner 确认后续出单计划。
- 若 2 倍奖金在途回款差距达到当前阶段应有出单进度，则对排名前三团队明确说明“符合当前出单计划，风险不大”，并提示团队按计划持续推进新订单。
- 现金流洞察规则已调整为：当月累计现金流为负时，先看下月现金流预估；下月预估转正则只持续跟进，下月预估仍为负才继续检查 PMS 在途金额。
- 2 倍奖金缺口规则仍按距离 10 月底的剩余月份判断是否匹配出单计划，但只分析风险榜单前 3 个不同团队；对外洞察只展示当前差距、计划判断和后续动作，不展示剩余月份或计算出的进度下限。
- 2026-06 结果目前生成 32 个团队实体、41 条规则命中；完整规则事实保存在 `data/knowledge-graph-latest.json`，整体卡只展示风险榜单前三团队的合并洞察。当前版本已发送给孙磊。
- 用户提出将长期财务知识与当月事实一起交给 LLM 生成管理层洞察。当前已接入 DeepSeek：`scripts/insights.py` 将知识规则、排名前三团队事实和规则命中一起提交模型，输出现金流分析与全年订单分析；调用失败时自动回退到规则洞察。
- 财务数据原始单位为千元；LLM 洞察提示词已明确禁止换算为万元，生成结果需保留“千元”单位。
- LLM 洞察金额已增加统一格式化：千分位逗号、两位小数、金额与“千元”之间留空格，例如 `-1,547.45 千元`。
- PMS 在途覆盖判断以“下月预估现金流缺口”为比较基准；若在途金额仅高出缺口不超过 10%，洞察表述为两者基本持平、现金流转正挑战较大。
- `.env.local` 已配置 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_MODEL`，文件已加入 `.gitignore`；密钥不会写入结果或消息。

## Working tree status

As of 2026-07-28, the knowledge-graph implementation, DeepSeek integration,
notification updates, and generated insight data are ready to commit. Local
dependency/build directories, card previews, and skill metadata remain
untracked and are ignored or intentionally excluded from the commit.
