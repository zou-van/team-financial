# 团队财务数据展示系统 — 设计文档

## 概述

从财务每月提供的 Excel 报表中解析团队财务数据，生成本地 Markdown 文件，通过网页展示月度明细和历史趋势。

## 数据流

```
excel/*.xlsx  →  scripts/parse.py  →  data/*.md  →  Vite + React 前端
                   ↑                        ↑
            team-mapping.yaml        data/index.json
```

1. 财务提供 Excel → 放入 `excel/` 目录，按 `YYYY-MM.xlsx` 命名
2. 手动维护 `team-mapping.yaml`，描述团队层级关系（一次性）
3. 运行 `python scripts/parse.py` → 扫描 Excel，生成 `data/YYYY-MM.md` 和 `data/index.json`
4. 重新放入某月 Excel 后重新运行脚本，覆盖更新对应的 Markdown
5. Vite + React 前端读 Markdown 和 index.json，渲染页面

## 团队层级

```
老板（大团队）
├── Leader A
│   ├── 子团队1（小团队A + 小团队B 的汇总列）
│   └── 子团队2（小团队C + 小团队D 的汇总列）
└── Leader B
    └── 子团队3（小团队E 的汇总列）
```

- Excel 中的列：小团队列、子团队列、大团队列（以老板名字出现）
- Leader 不在 Excel 中体现，通过 `team-mapping.yaml` 维护关联关系
- 大团队列 = 所有子团队之和（Excel 中已有）

## Excel 格式约定

- 每月一个 `.xlsx` 文件，命名为 `EC团队经营数据汇总YYYYMM.xlsx`（如 `EC团队经营数据汇总202603.xlsx`）
- 目标 Sheet：**「差距分析(团队)」**
- 列：每个小团队一列 + 子团队汇总列 + 大团队汇总列
- 行：各项财务指标（回款目标、现金支出等）
- 第一行为列标题（团队名），第一列为行标题（指标名）

## team-mapping.yaml

```yaml
# 老板（大团队列在 Excel 中的列名）
boss: 王总

# Leader → 子团队 → 小团队
leaders:
  张三:
    子团队1: [小团队A, 小团队B]
    子团队2: [小团队C, 小团队D]
  李四:
    子团队3: [小团队E]
```

- 用户手动维护，组织架构变动时更新
- 脚本用此文件验证 Excel 列名完整性，不匹配时报错
- 前端用此文件实现按 Leader 分组展示

## scripts/parse.py

### 输入
- `excel/*.xlsx` — 月度财务数据，读取 Sheet「差距分析(团队)」
- `team-mapping.yaml` — 团队层级映射

### 输出
- `data/YYYY-MM.md` — 每月一份，每个指标一个表格
- `data/index.json` — 列出所有可用月份、指标名、团队结构

### Markdown 格式

```md
# 2026年1月 财务数据

## 回款目标（万元）
| 小团队A | 小团队B | 子团队1 | 小团队C | 小团队D | 子团队2 | 大团队 |
|---------|---------|---------|---------|---------|---------|--------|
|     100 |     200 |     300 |     150 |     250 |     400 |    700 |

## 现金支出（万元）
| 小团队A | 小团队B | 子团队1 | ... |
|---------|---------|---------|-----|
|      80 |     150 |     230 | ... |
```

### 错误处理
- Excel 列名与 mapping 不匹配 → 报错并列出不匹配的列名
- 数值单元格非数字 → 跳过并输出警告
- mapping 文件缺失 → 按 Excel 原始列顺序生成，不加分组
- 缺少某月 Excel → 不影响其他月份，前端展示时跳过

### 运行方式
```bash
python scripts/parse.py
```

## 前端

### 技术栈
- Vite + React + Recharts
- `import.meta.glob` 导入 `data/*.md` 和 `team-mapping.yaml`
- 纯静态构建，无需服务端

### 组件树

```
App
├── MonthSelector          # 切换月份
├── ViewTabs               # 「月度详情」/「趋势图」
├── MonthlyTable           # 视图一：按 Leader 分组的表格
│   └── TeamColumnGroup    # 表头分组（Leader → 子团队 → 小团队）
└── TrendChart             # 视图二：趋势折线图
    ├── MetricPicker       # 选数据项
    ├── TeamPicker         # 选要对比的团队
    └── LineChart          # Recharts 折线图
```

### 视图一：月度详情

- 展示单月所有指标，表格形式
- 列按 Leader 分组，使用 colspan 合并表头
- Leader 行 → 子团队行 → 小团队行（三级表头）
- 大团队列独立显示在最后
- 上方月份选择器切换月份

### 视图二：趋势图

- X 轴 = 月份，Y 轴 = 数值
- 选择器：指标、团队层级（大团队/Leader/子团队/小团队）
- 支持多选团队对比
- Recharts 折线图 + 数据点标记

### 数据加载

- 构建时 `import.meta.glob` 读取所有 `data/*.md`
- `data/index.json` 提供月份列表和指标列表，避免遍历文件
- 前端解析 Markdown 表格，构建内存数据结构

### 错误处理
- 某月数据缺失 → 趋势图跳过该月，不报错
- Markdown 解析失败 → 控制台警告，该月不展示
- mapping 缺失 → 列不分 Leader 组，直接平铺

## 不纳入范围

- 数据库 / 后端服务
- 用户登录 / 权限控制
- Excel 上传功能（手动放入目录）
- 数据编辑功能
- 移动端适配
