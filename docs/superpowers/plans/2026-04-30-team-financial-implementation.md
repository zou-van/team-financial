# 团队财务数据展示系统 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 Excel 解析团队财务数据，生成本地 Markdown，通过 Vite + React 网页展示月度明细和趋势图。

**Architecture:** Python 脚本扫描 `excel/`，读 Sheet「差距分析(团队)」，按 `team-mapping.yaml` 层级生成 `data/YYYY-MM.md` 和 `data/index.json`。Vite + React 前端通过 `import.meta.glob` 加载 Markdown，Recharts 渲染图表。

**Tech Stack:** Python 3 + openpyxl + PyYAML / Vite + React 18 + Recharts

---

## 文件结构

```
team-financial/
├── .gitignore
├── package.json
├── vite.config.js
├── index.html
├── team-mapping.yaml
├── excel/.gitkeep
├── data/.gitkeep
├── scripts/
│   └── parse.py
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── App.css
    ├── lib/
    │   ├── parseMarkdown.js
    │   └── loadData.js
    └── components/
        ├── MonthSelector.jsx
        ├── ViewTabs.jsx
        ├── MonthlyTable.jsx
        ├── TrendChart.jsx
        ├── MetricPicker.jsx
        └── TeamPicker.jsx
```

---

### Task 1: 项目脚手架 ✅

**涉及文件：** `.gitignore`, `package.json`, `vite.config.js`, `index.html`, `excel/.gitkeep`, `data/.gitkeep`

**做什么：**
- `git init` 初始化仓库
- 创建 `.gitignore`，忽略 `node_modules/`、`dist/`、`__pycache__/`、`.DS_Store`
- 创建 `package.json`：项目名 `team-financial`，依赖 react 18、react-dom 18、recharts 2.x，devDependencies vite 5.x 和 @vitejs/plugin-react 4.x，scripts 含 dev/build/preview
- `vite.config.js`：使用 react 插件，`assetsInclude` 包含 `**/*.md`
- `index.html`：lang=zh-CN，title「团队财务数据」，`<div id="root">` + 指向 `/src/main.jsx`
- 创建 `excel/.gitkeep` 和 `data/.gitkeep`
- `npm install` 安装依赖
- 验证：`npx vite build` 不报错（可能需要先创建空的 `data/index.json` 和占位的 `src/main.jsx` 来让构建跑通）

---

### Task 2: team-mapping.yaml 模板 ✅

**涉及文件：** `team-mapping.yaml`

**做什么：**
- 创建 `team-mapping.yaml`，包含 boss（老板/大团队列名）、leaders（Leader → 子团队 → 小团队列表）
- 填入示例数据作为模板，用户后续根据实际组织架构修改
- 格式参考 spec 中定义的 YAML 结构

---

### Task 3: Python 解析脚本 ✅

**涉及文件：** `scripts/parse.py`

**做什么：**
- 安装依赖：`openpyxl`、`pyyaml`
- 脚本功能：
  1. 读取 `team-mapping.yaml`（缺失时降级为按 Excel 原始列顺序）
  2. 扫描 `excel/*.xlsx`，逐个打开并读取 Sheet「差距分析(团队)」
  3. 从第 1 行解析列标题（团队名，从第 2 列开始），第 1 列是行标题（指标名）
  4. 校验列名与 mapping 中定义的团队名是否匹配，不匹配时打 warning
  5. 按 mapping 定义的层级顺序重排列，然后每行指标生成一个 Markdown 表格
  6. 输出 `data/YYYY-MM.md`，格式：`# 月份 财务数据` → `## 指标名` → 表格
  7. 汇总所有月份和指标名，生成 `data/index.json`（含 months、metrics、teams 三个字段）
- 数值格式化：整数显示整数，浮点保留两位，空值显示 "-"
- 错误处理：sheet 不存在报错、某文件解析失败跳过继续、无 Excel 文件时提示退出

---

### Task 4: 前端数据层 ✅

**涉及文件：** `src/lib/parseMarkdown.js`, `src/lib/loadData.js`

**做什么：**
- `parseMarkdown.js`：导出 `parseMarkdown(mdContent)` 函数，将 Markdown 字符串解析为 `{ title, metrics }` 对象。metrics 的 key 是指标名，value 是 `{ headers: string[], values: (number|null)[] }`。按 `## ` 切分段落，在每个段落中定位 markdown 表格（表头行、分隔行、数据行），数据行的 "-" 转为 null
- `loadData.js`：导出三个函数：
  - `loadAllData()`：用 `import.meta.glob('/data/*.md', { query: '?raw', import: 'default', eager: true })` 加载所有 md 文件，调用 parseMarkdown 解析，结合 `import indexData from '/data/index.json'`，返回 `{ months: { "2026-01": {title, metrics}, ... }, index }`
  - `getTeamList(index)`：从 index.teams 提取所有可选团队的扁平列表（含 key、label、level）
  - `buildColumnGroups(index)`：从 index.teams 构建 MonthlyTable 所需的列分组结构

---

### Task 5: MonthSelector 和 ViewTabs 组件

**涉及文件：** `src/components/MonthSelector.jsx`, `src/components/ViewTabs.jsx`

**做什么：**
- `MonthSelector`：接收 `months`（string[]）、`selected`、`onChange`，渲染一个 `<select>` 下拉框。无数据时显示「暂无数据」
- `ViewTabs`：接收 `active`、`onChange`，渲染两个按钮「月度详情」和「趋势图」，active 态高亮

---

### Task 6: MonthlyTable 组件 ✅

**涉及文件：** `src/components/MonthlyTable.jsx`

**做什么：**
- 接收 `data`（单月解析结果）和 `mapping`（index 对象）
- 若无 data，显示「请选择月份查看数据」
- 遍历 data.metrics，每个指标渲染一个 `<table>`
- 当 mapping 中存在 team 层级信息时，表头分三行：
  - 第 1 行：Leader 名，colspan 覆盖其下所有子团队列
  - 第 2 行：子团队名，colspan 覆盖其下小团队列 + 子团队自身列
  - 第 3 行：具体列名（小团队名、子团队名）
  - 大团队（boss）列 rowspan=3 放在最右
- 当 mapping 无层级信息时，退化为单行平铺表头
- 表格需支持横向滚动（`overflow-x: auto`）

---

### Task 7: TrendChart 组件及相关 Picker ✅

**涉及文件：** `src/components/MetricPicker.jsx`, `src/components/TeamPicker.jsx`, `src/components/TrendChart.jsx`

**做什么：**
- `MetricPicker`：接收 `metrics`（string[]）、`selected`、`onChange`，渲染指标下拉框
- `TeamPicker`：接收 `teams`（getTeamList 的返回值）、`selected`（string[]）、`onChange`，渲染分层级的 checkbox 列表（大团队 / 子团队 / 小团队分组），支持多选
- `TrendChart`：
  - 接收 `months`（loadAllData 的 months 对象）和 `index`
  - 内部维护当前选中的指标（state）和团队列表（state）
  - 根据选中项从 months 中提取数据，构建 Recharts 的 data 数组（每个元素含 `month` 字段和各个选中团队的值字段）
  - 用 `ResponsiveContainer` + `LineChart` 渲染折线图，每个选中团队一条折线，预定义 10 种颜色循环使用，`connectNulls` 处理缺失月份
  - 未选团队时显示「请至少选择一个团队」

---

### Task 8: App 壳、样式、入口 ✅

**涉及文件：** `src/App.jsx`, `src/App.css`, `src/main.jsx`

**做什么：**
- `App.jsx`：模块顶层调用 `loadAllData()`，内部维护 `selectedMonth`（默认最新月份）和 `view`（"monthly" | "trend"）两个 state。渲染 header（标题）、toolbar（MonthSelector + ViewTabs）、main（按 view 切换 MonthlyTable 或 TrendChart）
- `main.jsx`：标准 React 18 createRoot 入口，包裹 StrictMode
- `App.css`：全局样式，包括 reset、布局（app/toolbar/main）、MonthSelector、ViewTabs、MonthlyTable（表格边框、表头背景色、hover 效果）、TrendChart 控制区、TeamPicker checkbox 布局、空状态样式。配色简洁专业，字体优先使用系统中文字体（PingFang SC、Microsoft YaHei）

---

### Task 9: 验证 ✅

**做什么：**
- 确保 `data/index.json` 存在（内容可为空初始值 `{"months":[],"metrics":[],"teams":{}}`）
- 运行 `npx vite build`，确认构建成功无报错
- 运行 `npm run dev`，确认 dev server 启动正常
- 检查页面渲染：无数据时不报错，有空状态提示
