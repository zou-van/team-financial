"""Generate Feishu notification messages for latest monthly financial data.

Reads notification-config.yaml and team-mapping.yaml, extracts key metrics
from the latest data file, resolves recipient scopes to column names,
summarizes values, and prints the message text.

Does NOT send messages — output is text only. Use --dry-run (default) to
preview; lark-cli integration is a separate step.
"""

import json
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
NOTIFICATION_CONFIG = BASE_DIR / "notification-config.yaml"
MAPPING_FILE = BASE_DIR / "team-mapping.yaml"
INSIGHTS_FILE = DATA_DIR / "knowledge-graph-latest.json"

# ── Key metric identifiers ──────────────────────────────────────────────
METRIC_PMS_RECEIVABLE = "PMS预计回款（在途）"
METRIC_CASH_FLOW_PREFIX = "累计现金流"
METRIC_REVENUE_TARGET_2X = "回款目标（考虑2倍奖金）"
METRIC_GAP_2X = "考虑2倍奖金在途回款差距（+超额/-落后）"

# Forward-looking estimates
METRIC_JULY_CF_EST = "7月现金流预估"

# Dashboard link template (update when deployed)
DASHBOARD_URL = "https://your-dashboard.example.com"

# Leader → aggregate column mapping for overall card (matching Excel columns)
LEADER_COLUMN_MAP = {
    "张浩": "交易中台",
    "沈晓华": "沈晓华合计",
    "赵华": "线上运营",
}


# ── Helpers ─────────────────────────────────────────────────────────────

def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_insights():
    """Load generated management insights, if available."""
    if not INSIGHTS_FILE.exists():
        return []
    with open(INSIGHTS_FILE, encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("llm_insights") or payload.get("insights", [])


def find_latest_month():
    """Return the path to the latest YYYY-MM.md file in data/."""
    md_files = sorted(DATA_DIR.glob("????-??.md"))
    if not md_files:
        raise FileNotFoundError("No monthly data files found in data/")
    return md_files[-1]


def month_key_from_path(path):
    return path.stem  # "2026-06"


def month_label(month_key):
    y, m = month_key.split("-")
    return f"{y}年{m}月"


def prev_month_key(month_key):
    y, m = int(month_key[:4]), int(month_key[5:7])
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def parse_value(raw):
    """Convert a table cell to int, float, or None (for '-' / '')."""
    if raw in ("-", ""):
        return None
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw  # keep strings like "#REF!" as-is


def parse_md(filepath):
    """Parse a data/YYYY-MM.md file.

    Returns OrderedDict: {metric_name: {column_name: value}}
    where value is int/float, None, or a string for error values.
    """
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    metrics = OrderedDict()
    current_metric = None
    headers = []
    past_separator = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_metric = None
            headers = []
            past_separator = False
            continue

        if stripped.startswith("## "):
            current_metric = stripped[3:]
            headers = []
            past_separator = False
            continue

        if not current_metric:
            continue

        if stripped.startswith("|"):
            parts = [p.strip() for p in stripped.split("|")[1:-1]]

            # Detect separator row: every cell is only dashes and spaces
            if all(set(p) <= {"-", " "} and p for p in parts):
                # The row right before the separator is the header
                # (headers were already stored from the previous row)
                past_separator = True
                continue

            if not headers and not past_separator:
                # First | row after ## is the header
                headers = parts
                continue

            if past_separator and headers:
                # Data row
                row = {}
                for i, val in enumerate(parts):
                    if i < len(headers):
                        row[headers[i]] = parse_value(val)
                metrics[current_metric] = row
                # Only take the first data row per metric
                past_separator = False

    return metrics


def resolve_scope_columns(scope, mapping):
    """Return the set of leaf (small-team) column names for a scope.

    - {leader: X}                → all small teams across all sub-teams
    - {leader: X, sub_team: Y}   → all small teams in that sub-team
    - {…, teams: [A, B]}         → only the listed teams
    """
    columns = set()
    leaders = mapping.get("leaders", {})
    sub_teams = leaders.get(scope["leader"], {})

    sub_team = scope.get("sub_team")
    restrict_teams = scope.get("teams")

    if sub_team:
        small_teams = sub_teams.get(sub_team, [])
        if restrict_teams:
            columns.update(t for t in restrict_teams if t in small_teams)
        else:
            columns.update(small_teams)
    else:
        for teams in sub_teams.values():
            columns.update(teams)

    return columns


def find_latest_cashflow(metrics):
    """Among keys like '累计现金流_2026.6.30', return (key, data) for the
    latest date. Falls back to exact match '累计现金流'."""
    candidates = []
    for name in metrics:
        if name == METRIC_CASH_FLOW_PREFIX:
            # Exact match — no date suffix
            candidates.append((datetime(2099, 12, 31), name))
        elif name.startswith(METRIC_CASH_FLOW_PREFIX + "_"):
            suffix = name[len(METRIC_CASH_FLOW_PREFIX) + 1:]
            try:
                # Normalise: "2026.6.30" or "2026.06.30"
                parts = [int(x) for x in re.split(r"[._]", suffix) if x]
                if len(parts) == 3:
                    candidates.append((datetime(*parts), name))
            except (ValueError, TypeError):
                continue

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[0], reverse=True)
    latest_name = candidates[0][1]
    return latest_name, metrics[latest_name]


def sum_across(data_row, columns):
    """Sum numeric values across *columns*.  Returns None if any column is
    missing or non-numeric."""
    total = 0
    for col in columns:
        val = data_row.get(col)
        if val is None or not isinstance(val, (int, float)):
            return None
        total += val
    return total


def format_amount(val):
    """Format a numeric amount (千元)."""
    if val is None:
        return "—"
    if isinstance(val, float) and val == int(val):
        val = int(val)
    if isinstance(val, int):
        return f"{val:,}"
    return f"{val:,.2f}"


def calc_mom(current, previous):
    """Month-over-month: returns (arrow, percentage, is_calculable)."""
    if previous is None or current is None:
        return "", 0, False
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return "", 0, False
    if previous == 0:
        return "", 0, False

    diff = current - previous
    pct = abs(diff / previous) * 100
    arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
    return arrow, pct, True


# ── Scope breakdown ──────────────────────────────────────────────────────

def scope_label(scope):
    """Short human-readable label for a single scope."""
    leader = scope["leader"]
    sub = scope.get("sub_team")
    teams = scope.get("teams")
    if teams:
        return f"{'、'.join(teams)}（{leader}→{sub}）"
    if sub:
        return f"{sub}（{leader}）"
    # Leader-only: find their sub-teams
    return f"{leader}团队"


def get_scope_breakdown(scope, mapping):
    """Return (teams, sub_breakdowns) for a scope.

    teams: list of leaf team column names covered by this scope.
    sub_breakdowns: list of (label, [column_names]) for sub-groups,
    derived from virtual_aggregates that overlap with this scope.
    Teams not covered by any virtual aggregate become their own entries.
    """
    teams = sorted(resolve_scope_columns(scope, mapping))
    if len(teams) <= 1:
        return teams, []

    sub_team = scope.get("sub_team")
    virtual_aggs = mapping.get("virtual_aggregates", [])

    # Find virtual aggregates whose members are all within this scope
    sub_breakdowns = []
    covered = set()

    for va in virtual_aggs:
        # Only apply when scope targets the same sub_team, or when scope is
        # leader-level and the aggregate's sub_team belongs to that leader
        if sub_team:
            if va["sub_team"] != sub_team:
                continue
        else:
            # Leader-level scope: check that this aggregate's sub_team
            # belongs to the leader
            leader_sub_teams = mapping.get("leaders", {}).get(
                scope["leader"], {}
            )
            if va["sub_team"] not in leader_sub_teams:
                continue

        va_members = [m for m in va["members"] if m in teams]
        if len(va_members) > 1:
            sub_breakdowns.append((va["name"], va_members))
            covered.update(va_members)

    # Remaining teams not covered by any virtual aggregate
    remaining = [t for t in teams if t not in covered]
    for t in remaining:
        sub_breakdowns.append((t, [t]))

    return teams, sub_breakdowns


# ── Card 2.0 component builders ──────────────────────────────────────────

def _card_config():
    """Return the config block shared by all cards."""
    return {
        "update_multi": True,
        "width_mode": "default",
        "style": {
            "text_size": {
                "title":   {"default": "heading-2", "pc": "heading-2", "mobile": "heading-3"},
                "body":    {"default": "normal",    "pc": "normal",    "mobile": "normal"},
                "caption": {"default": "notation",  "pc": "notation",  "mobile": "notation"},
            }
        },
    }


def _header(month_label_str, subtitle):
    """Return the card header block."""
    return {
        "title":    {"tag": "plain_text", "content": f"【{month_label_str}】团队经营数据"},
        "subtitle": {"tag": "plain_text", "content": subtitle},
        "template": "blue",
        "icon":     {"tag": "standard_icon", "token": "chart_colorful"},
    }


def _kpi_card(label, value, sub_text=None, value_color="blue", sub_color="grey",
              value_prefix="## "):
    """Build a single KPI card column.

    label:        metric name shown in grey notation above the value
    value:        big number (already formatted by format_amount)
    sub_text:     optional footnote (MoM, status, etc.), grey notation
    value_color:  colour for the big number (blue / red / green)
    sub_color:    colour for sub_text (grey / red / green)
    value_prefix: markdown heading prefix for value size (default "## ")
    """
    elements = [
        {"tag": "markdown", "content": f"<font color='grey'>{label}</font>",
         "text_align": "center", "text_size": "notation"},
        {"tag": "markdown", "content": f"{value_prefix}<font color='{value_color}'>{value}</font>",
         "text_align": "center"},
    ]
    if sub_text:
        elements.append(
            {"tag": "markdown", "content": f"<font color='{sub_color}'>{sub_text}</font>",
             "text_align": "center", "text_size": "notation"},
        )
    return {
        "tag": "column",
        "width": "weighted", "weight": 1,
        "background_style": "grey-50",
        "padding": "12px", "vertical_spacing": "2px",
        "elements": elements,
    }


def _kpi_row(left_card, right_card, margin="0px 0px 12px 0px"):
    """Wrap two KPI cards in a column_set row."""
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "horizontal_spacing": "12px",
        "margin": margin,
        "columns": [left_card, right_card],
    }


def _section_title(text):
    """Scope/section heading inside the card body."""
    return {
        "tag": "markdown",
        "content": f"**{text}**",
        "text_size": "title",
        "margin": "0px 0px 12px 0px",
    }


def _hr():
    return {"tag": "hr", "margin": "0px 0px 12px 0px"}


def _warning_block(gap_val, scope_label_text, month_key):
    """Red-50 warning block for negative gap."""
    shortfall = abs(gap_val)
    deadline = f"{month_key[:4]}-10-15"
    return {
        "tag": "interactive_container",
        "width": "fill",
        "background_style": "red-50",
        "padding": "12px",
        "margin": "0px 0px 8px 0px",
        "elements": [{
            "tag": "markdown",
            "content": (
                f"<font color='red'>**⚠️ 仍需新订单 {format_amount(shortfall)} 千元**</font>\n"
                f"建议在 {deadline} 前完成新订单出单。"
            ),
            "text_size": "normal",
        }],
    }


def _team_detail_line(sub_label, pms_val, cf_val, gap_val, indent=False):
    """Format one team detail line as a markdown bullet."""
    prefix = "  - " if indent else "• "
    parts = []
    if cf_val is not None:
        parts.append(f"现金流 {format_amount(cf_val)}")
    if gap_val is not None:
        tag = "<font color='red'>**落后**</font>" if gap_val < 0 else "超额"
        parts.append(f"距2倍奖金订单差 {format_amount(gap_val)}（{tag}）")
    parts.append(f"PMS在途 {format_amount(pms_val)}")
    return f"{prefix}{sub_label} — {' | '.join(parts)}"


def _team_details(sub_breakdowns, data, cf_data):
    """Build a team-detail markdown block from sub-breakdowns.

    Virtual aggregates (len(cols) > 1) expand to show each member team
    as an indented sub-bullet.
    """
    lines = ["**团队明细**"]
    for i, (sub_label, sub_cols) in enumerate(sub_breakdowns):
        sub_pms = sum_across(data.get(METRIC_PMS_RECEIVABLE, {}), sub_cols)
        sub_cf = sum_across(cf_data, sub_cols) if cf_data else None
        sub_gap = sum_across(data.get(METRIC_GAP_2X, {}), sub_cols)

        # Blank line between virtual-aggregate block and following teams
        if i > 0 and len(sub_breakdowns[i - 1][1]) > 1:
            lines.append("")

        lines.append(_team_detail_line(sub_label, sub_pms, sub_cf, sub_gap))

        # Expand virtual aggregate members
        if len(sub_cols) > 1:
            for member_col in sub_cols:
                m_pms = sum_across(
                    data.get(METRIC_PMS_RECEIVABLE, {}), [member_col]
                )
                m_cf = (
                    sum_across(cf_data, [member_col]) if cf_data else None
                )
                m_gap = sum_across(
                    data.get(METRIC_GAP_2X, {}), [member_col]
                )
                lines.append(
                    _team_detail_line(
                        member_col, m_pms, m_cf, m_gap, indent=True
                    )
                )
    return {
        "tag": "markdown",
        "content": "\n".join(lines),
        "text_size": "normal",
        "margin": "0px 0px 12px 0px",
    }


def _footer(month_label_str):
    """Data-source footnote."""
    return {
        "tag": "markdown",
        "content": f"<font color='grey'>数据来源：团队经营报表 {month_label_str}</font>",
        "text_size": "notation",
    }


# ── MoM helpers (return display strings for card sub_text) ──────────────

def _pms_mom_text(pms_total, prev_data, columns):
    """Return the MoM sub-text for the PMS card, or None."""
    if not prev_data:
        return "环比：无法计算"
    prev_pms = sum_across(prev_data.get(METRIC_PMS_RECEIVABLE, {}), columns)
    arrow, pct, ok = calc_mom(pms_total, prev_pms)
    if ok:
        return f"环比 {arrow}{pct:.2f}%"
    return "环比：无法计算"


def _cf_mom_text(cf_val, prev_data, columns):
    """Return the MoM sub-text for the cash-flow card, or None."""
    if not prev_data:
        return None
    _, prev_cf_data = find_latest_cashflow(prev_data)
    if not prev_cf_data:
        return None
    prev_cf_val = sum_across(prev_cf_data, columns)
    arrow, pct, ok = calc_mom(cf_val, prev_cf_val)
    if ok:
        return f"环比 {arrow}{pct:.2f}%"
    return None


def _cf_status_text(cf_val):
    """'现金流为正' / '现金流为负'."""
    if cf_val is None:
        return None
    return "现金流为正" if cf_val >= 0 else "现金流为负"


def _july_tag(july_cf, cf_val):
    """Return (tag_text, tag_color) for 7月现金流预估."""
    if july_cf is None:
        return None, None
    if cf_val is not None and cf_val < 0 and july_cf >= 0:
        return "预计转正", "green"
    if july_cf is not None and july_cf < 0:
        return "仍承压", "orange"
    return "持续为正", "green"


# ── Card builder ────────────────────────────────────────────────────────

def build_card(recipient, data, prev_data, month_label_str, month_key, mapping):
    """Build a Card 2.0 JSON object for one recipient.

    Each scope gets: section title → 2×2 KPI cards → 7月预估 →
    warning (if negative gap) → team details (if sub-breakdowns).
    Scopes are separated by <hr>.
    """
    cf_name, cf_data = find_latest_cashflow(data)

    # Subtitle: scope summary
    scope_labels = []
    for scope in recipient["scopes"]:
        scope_labels.append(scope_label(scope))
    subtitle = " · ".join(scope_labels) + " · 千元"

    body_elements = []

    for i, scope in enumerate(recipient["scopes"]):
        label = scope_label(scope)
        teams, sub_breakdowns = get_scope_breakdown(scope, mapping)

        if i > 0:
            body_elements.append(_hr())

        # Section title
        body_elements.append(_section_title(label))

        # ── Compute scope values ────────────────────────────────────
        pms_val  = sum_across(data.get(METRIC_PMS_RECEIVABLE, {}), teams)
        cf_val   = sum_across(cf_data, teams) if cf_data else None
        target_val = sum_across(data.get(METRIC_REVENUE_TARGET_2X, {}), teams)
        gap_val  = sum_across(data.get(METRIC_GAP_2X, {}), teams)

        # ── Row 1: 累计现金流 + PMS在途 ─────────────────────────────
        pms_sub = _pms_mom_text(pms_val, prev_data, teams)

        cf_sub_parts = []
        cf_status = _cf_status_text(cf_val)
        if cf_status:
            cf_sub_parts.append(cf_status)
        cf_mom = _cf_mom_text(cf_val, prev_data, teams)
        if cf_mom:
            cf_sub_parts.append(cf_mom)
        cf_sub = "，".join(cf_sub_parts) if cf_sub_parts else None

        cf_color = "red" if (cf_val is not None and cf_val < 0) else "blue"
        # Short date label: "累计现金流_2026.6.30" → "6.30"
        if cf_name and "_" in cf_name:
            cf_date_label = cf_name.rsplit("_", 1)[-1]
        else:
            cf_date_label = cf_name or "累计现金流"

        body_elements.append(_kpi_row(
            _kpi_card(f"累计现金流（{cf_date_label}）", format_amount(cf_val), cf_sub,
                      value_color=cf_color),
            _kpi_card("PMS预计回款（在途）", format_amount(pms_val), pms_sub),
        ))

        # ── Row 2: 回款目标 + 在途差距 ─────────────────────────────
        gap_color = "red" if (gap_val is not None and gap_val < 0) else \
                    ("green" if (gap_val is not None and gap_val >= 0) else "blue")
        gap_sub = None
        gap_sub_color = "grey"
        if gap_val is not None:
            if gap_val >= 0:
                gap_sub = "超额"
            else:
                gap_sub = "落后"
                gap_sub_color = "red"

        body_elements.append(_kpi_row(
            _kpi_card("回款目标（2倍奖金）", format_amount(target_val)),
            _kpi_card("在途单回款差距（2倍奖金）", format_amount(gap_val), gap_sub,
                      value_color=gap_color, sub_color=gap_sub_color),
        ))

        # ── 7月现金流预估 ───────────────────────────────────────────
        july_cf = sum_across(data.get(METRIC_JULY_CF_EST, {}), teams)
        if july_cf is not None:
            tag_text, tag_color = _july_tag(july_cf, cf_val)
            body_elements.append({
                "tag": "markdown",
                "content": (
                    f"7月现金流预估：**{format_amount(july_cf)} 千元**"
                    f"（<font color='{tag_color}'>{tag_text}</font>）"
                ),
                "text_size": "normal",
                "margin": "0px 0px 8px 0px",
            })

        # ── Warning (only when gap is negative) ─────────────────────
        if gap_val is not None and gap_val < 0:
            body_elements.append(_warning_block(gap_val, label, month_key))

        # ── Team details (only when there are sub-breakdowns) ───────
        if len(sub_breakdowns) > 1:
            body_elements.append(_team_details(sub_breakdowns, data, cf_data))

    # Footer
    body_elements.append(_footer(month_label_str))

    return {
        "schema": "2.0",
        "config": _card_config(),
        "header": _header(month_label_str, subtitle),
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 20px 12px",
            "elements": body_elements,
        },
    }


# ── Overall card ────────────────────────────────────────────────────────

def _build_leader_summary(data, cf_data):
    """Build a compact per-leader summary markdown block.

    Each line: • **Leader** — 现金流 X | 下月预计现金流 Y | PMS在途 Z | 2倍奖金差距 W（tag）
    """
    lines = []
    for leader, col in LEADER_COLUMN_MAP.items():
        cf = cf_data.get(col) if cf_data else None
        gap = data.get(METRIC_GAP_2X, {}).get(col)
        pms = data.get(METRIC_PMS_RECEIVABLE, {}).get(col)
        july = data.get(METRIC_JULY_CF_EST, {}).get(col)

        parts = [f"现金流 {format_amount(cf)}"]

        if july is not None:
            tag_text, tag_color = _july_tag(july, cf)
            parts.append(
                f"下月预计现金流 {format_amount(july)}"
                f"（<font color='{tag_color}'>{tag_text}</font>）"
            )

        parts.append(f"PMS在途 {format_amount(pms)}")

        if gap is not None:
            tag = "<font color='red'>**落后**</font>" if gap < 0 else "超额"
            parts.append(f"2倍奖金差距 {format_amount(gap)}（{tag}）")

        lines.append(f"• **{leader}** — {' | '.join(parts)}")

    return {
        "tag": "markdown",
        "content": "\n".join(lines),
        "text_size": "normal",
        "margin": "0px 0px 12px 0px",
    }


def _add_worst_rankings(body_elements, data, cf_data, mapping):
    """Append risk rankings as KPI-card rows.

    Two rows of 3 cards each:
    - Row 1: worst-3 cash-flow teams (big red value)
    - Row 2: worst-3 gap teams (big red value)
    Each card shows team name (with leader) as label and the value as the hero.
    """
    leaders = mapping.get("leaders", {})

    # ── Build team→leader reverse map ────────────────────────────────
    team_leader = {}
    for leader_name, sub_teams in leaders.items():
        for teams in sub_teams.values():
            for t in teams:
                team_leader[t] = leader_name

    # ── Collect and rank ──────────────────────────────────────────────
    cf_ranked = []
    gap_ranked = []
    for t, leader_name in team_leader.items():
        t_cf = sum_across(cf_data, [t]) if cf_data else None
        if isinstance(t_cf, (int, float)):
            cf_ranked.append((t, t_cf, leader_name))
        t_gap = data.get(METRIC_GAP_2X, {}).get(t)
        if isinstance(t_gap, (int, float)):
            gap_ranked.append((t, t_gap, leader_name))

    cf_ranked.sort(key=lambda x: x[1])
    gap_ranked.sort(key=lambda x: x[1])

    # ── Section title ─────────────────────────────────────────────────
    body_elements.append({
        "tag": "markdown",
        "content": "**⚠️ 风险榜单**",
        "text_size": "title",
        "margin": "0px 0px 8px 0px",
    })

    # ── Row 1: 现金流最差前3 ──────────────────────────────────────────
    body_elements.append({
        "tag": "markdown",
        "content": "现金流最差前3",
        "text_size": "normal",
        "margin": "0px 0px 4px 0px",
    })
    body_elements.append(_kpi_card_row(
        [_risk_card(t, v, l, "现金流") for t, v, l in cf_ranked[:3]]
    ))

    # ── Row 2: 差距最大前3 ────────────────────────────────────────────
    body_elements.append({
        "tag": "markdown",
        "content": "距2倍奖金差最大前3",
        "text_size": "normal",
        "margin": "12px 0px 4px 0px",
    })
    body_elements.append(_kpi_card_row(
        [_risk_card(t, v, l, "gap") for t, v, l in gap_ranked[:3]]
    ))

    ranked_teams = []
    for team_name, _, _ in cf_ranked[:3] + gap_ranked[:3]:
        if team_name not in ranked_teams:
            ranked_teams.append(team_name)
        if len(ranked_teams) == 3:
            break
    return ranked_teams


def _add_management_insights(body_elements, insights, ranked_teams):
    """Append financial insights in cash-flow and annual-order topics."""
    if not insights or not ranked_teams:
        return

    if "cashflow_analysis" in insights[0] or "order_analysis" in insights[0]:
        _add_llm_management_insights(body_elements, insights, ranked_teams)
        return

    body_elements.append(_section_title("财务数据洞察"))
    grouped = {team: [] for team in ranked_teams}
    for item in insights:
        if item["team"] in grouped:
            grouped[item["team"]].append(item)

    topic_lines = [
        _compact_team_insight(team, grouped[team])
        for team in ranked_teams
        if grouped[team]
    ]
    cashflow_lines = [item[0] for item in topic_lines if item[0]]
    order_lines = [item[1] for item in topic_lines if item[1]]
    if not cashflow_lines and not order_lines:
        return
    for title, lines in (("现金流分析", cashflow_lines), ("全年订单分析", order_lines)):
        if not lines:
            continue
        body_elements.append({
            "tag": "markdown",
            "content": f"**{title}**",
            "text_size": "normal",
            "margin": "0px 0px 4px 0px",
        })
        body_elements.append({
            "tag": "markdown",
            "content": "\n\n".join(lines),
            "text_size": "normal",
            "margin": "0px 0px 8px 0px",
        })


def _add_llm_management_insights(body_elements, insights, ranked_teams):
    """Render concise model-written insights while preserving card structure."""
    grouped = {team: [] for team in ranked_teams}
    for item in insights:
        if item.get("team") in grouped:
            grouped[item["team"]].append(item)

    cashflow_lines = []
    order_lines = []
    for team in ranked_teams:
        item = grouped[team][0] if grouped[team] else None
        if not item:
            continue
        risk_color = "red" if item.get("risk_level") == "high" else "orange"
        prefix = f"• <font color='{risk_color}'>关注</font> **{team}**"
        if item.get("leader"):
            prefix += f"（{item['leader']}）"
        if item.get("cashflow_analysis"):
            cashflow_lines.append(f"{prefix}：{item['cashflow_analysis']}")
        if item.get("order_analysis"):
            order_lines.append(f"{prefix}：{item['order_analysis']}")

    if not cashflow_lines and not order_lines:
        return
    body_elements.append(_section_title("财务数据洞察"))
    for title, lines in (("现金流分析", cashflow_lines), ("全年订单分析", order_lines)):
        if not lines:
            continue
        body_elements.append({
            "tag": "markdown",
            "content": f"**{title}**",
            "text_size": "normal",
            "margin": "0px 0px 4px 0px",
        })
        body_elements.append({
            "tag": "markdown",
            "content": "\n\n".join(lines),
            "text_size": "normal",
            "margin": "0px 0px 8px 0px",
        })


def _compact_team_insight(team_name, items):
    """Return one cash-flow line and one annual-order line for a team."""
    first = items[0]
    values = {}
    for item in items:
        values.update(item.get("values", {}))

    cf = next((v for k, v in values.items() if k.startswith(METRIC_CASH_FLOW_PREFIX)), None)
    pms = values.get(METRIC_PMS_RECEIVABLE)
    gap = values.get(METRIC_GAP_2X)
    forecast_name, forecast = next(
        ((k, v) for k, v in values.items() if k.endswith("月现金流预估")),
        (None, None),
    )
    current_name = next(
        (k for k in values if k.startswith(METRIC_CASH_FLOW_PREFIX)),
        None,
    )
    current_month = _metric_month(current_name)
    forecast_month = _metric_month(forecast_name)
    cashflow_paragraphs = []
    order_paragraphs = []

    if cf is not None and cf < 0:
        if forecast is None:
            cashflow_paragraphs.append(
                f"{current_month}现金流为负 {format_amount(cf)}，需补充下月预估并继续跟进回款。"
            )
        elif forecast < 0:
            if forecast < cf:
                cashflow_paragraphs.append(
                    f"现金流缺口从{current_month} {format_amount(cf)}"
                    f"扩大至{forecast_month}预估 {format_amount(forecast)}，现金流风险在加大。"
                )
            else:
                cashflow_paragraphs.append(
                    f"{current_month}现金流为负 {format_amount(cf)}，"
                    f"{forecast_month}预估仍为负 {format_amount(forecast)}，现金流仍有压力。"
                )
        else:
            cashflow_paragraphs.append(
                f"{current_month}现金流为负 {format_amount(cf)}，"
                f"{forecast_month}预估转正 {format_amount(forecast)}，持续跟进回款确认预估兑现。"
            )

    if pms is not None and forecast is not None and forecast < 0:
        forecast_gap = abs(forecast)
        if pms >= forecast_gap:
            cashflow_paragraphs.append(
                f"PMS在途 {format_amount(pms)} 可覆盖{forecast_month}预估缺口 "
                f"{format_amount(forecast_gap)}，团队与业务Owner严格追踪在途单回款情况。"
            )
        else:
            cashflow_paragraphs.append(
                f"PMS在途 {format_amount(pms)} 不足覆盖{forecast_month}预估缺口 "
                f"{format_amount(forecast_gap)}，团队与业务Owner同时追踪在途回款和新出单。"
            )

    progress_item = next(
        (item for item in items if item["rule_id"] in {
            "order_progress_behind_before_october",
            "order_progress_on_plan_before_october",
        }),
        None,
    )
    if progress_item:
        gap = progress_item.get("values", {}).get(METRIC_GAP_2X, gap)
        if progress_item["rule_id"] == "order_progress_on_plan_before_october" and gap is not None:
            order_paragraphs.append(
                f"2倍奖金在途回款差距为 {format_amount(gap)}，符合当前出单计划，"
                "风险不大，团队按计划持续推进新订单。"
            )
        elif gap is not None:
            order_paragraphs.append(
                f"2倍奖金在途回款差距为 {format_amount(gap)}，"
                "未按出单计划推进，存在今年财务目标无法完成的风险；"
                "与业务Owner沟通确认后续出单计划。"
            )
    elif "october_gap_not_ready" in {item["rule_id"] for item in items} and gap is not None:
        order_paragraphs.append(
            f"2倍奖金在途回款差距为 {format_amount(gap)}，"
            "10月底仍未达标，存在今年财务目标无法完成的风险；"
            "与业务Owner沟通确认后续出单计划。"
        )

    def line(text, relevant_items):
        level = "高风险" if any(i["risk_level"] == "high" for i in relevant_items) else "需关注"
        color = "red" if level == "高风险" else "orange"
        return f"• <font color='{color}'>{level}</font> **{team_name}**（{first['leader']}）：{text}"

    cashflow_line = line(" ".join(cashflow_paragraphs), [
        item for item in items
        if item["rule_id"] in {
            "negative_cumulative_cashflow",
            "cashflow_negative_next_month_improves",
            "cashflow_negative_next_month_still_negative",
            "pms_in_transit_can_cover_cashflow_gap",
            "pms_in_transit_cannot_cover_cashflow_gap",
        }
    ]) if cashflow_paragraphs else ""
    order_line = line(" ".join(order_paragraphs), [
        item for item in items
        if item["rule_id"] in {
            "order_progress_behind_before_october",
            "order_progress_on_plan_before_october",
            "october_gap_not_ready",
            "year_end_gap_not_met",
        }
    ]) if order_paragraphs else ""
    return cashflow_line, order_line


def _metric_month(metric_name):
    """Extract a display month from a metric name."""
    if not metric_name:
        return "本月"
    match = re.search(r"(?:累计现金流_\d{4}\.)?(\d{1,2})(?:\.|月)", metric_name)
    return f"{match.group(1)}月" if match else "本月"


def _risk_card(team_name, value, leader_name, metric_type):
    """Build a KPI card for a risk-ranking entry (inline text, no heading)."""
    label = f"{team_name}（{leader_name}）"
    return _kpi_card(label, format_amount(value), value_color="red",
                     value_prefix="")


def _kpi_card_row(cards):
    """Wrap 2 or 3 KPI cards in a column_set row."""
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "horizontal_spacing": "8px",
        "margin": "0px 0px 12px 0px",
        "columns": cards,
    }


def build_overall_card(recipient, data, prev_data, month_label_str, month_key,
                       mapping, insights=None):
    """Build a Card 2.0 JSON object for the overall team view.

    Top half: 2×2 global KPIs from the 合计 column.
    Bottom half: one compact summary line per Leader.
    """
    cf_name, cf_data = find_latest_cashflow(data)

    TOTAL_COL = mapping.get("boss", "合计")

    # ── Global KPI values ────────────────────────────────────────────
    pms_val = data.get(METRIC_PMS_RECEIVABLE, {}).get(TOTAL_COL)
    cf_val = cf_data.get(TOTAL_COL) if cf_data else None
    target_val = data.get(METRIC_REVENUE_TARGET_2X, {}).get(TOTAL_COL)
    gap_val = data.get(METRIC_GAP_2X, {}).get(TOTAL_COL)
    july_cf = data.get(METRIC_JULY_CF_EST, {}).get(TOTAL_COL)

    subtitle = "电商团队 · 千元"

    body_elements = []

    # ── Row 1: 累计现金流 + PMS在途 ──────────────────────────────────
    pms_sub = _pms_mom_text(pms_val, prev_data, [TOTAL_COL])

    cf_sub_parts = []
    cf_status = _cf_status_text(cf_val)
    if cf_status:
        cf_sub_parts.append(cf_status)
    cf_mom = _cf_mom_text(cf_val, prev_data, [TOTAL_COL])
    if cf_mom:
        cf_sub_parts.append(cf_mom)
    cf_sub = "，".join(cf_sub_parts) if cf_sub_parts else None

    cf_color = "red" if (cf_val is not None and cf_val < 0) else "blue"
    if cf_name and "_" in cf_name:
        cf_date_label = cf_name.rsplit("_", 1)[-1]
    else:
        cf_date_label = cf_name or "累计现金流"

    body_elements.append(_kpi_row(
        _kpi_card(f"累计现金流（{cf_date_label}）", format_amount(cf_val), cf_sub,
                  value_color=cf_color),
        _kpi_card("PMS预计回款（在途）", format_amount(pms_val), pms_sub),
    ))

    # ── Row 2: 回款目标 + 在途差距 ──────────────────────────────────
    gap_color = "red" if (gap_val is not None and gap_val < 0) else \
                ("green" if (gap_val is not None and gap_val >= 0) else "blue")
    gap_sub = None
    gap_sub_color = "grey"
    if gap_val is not None:
        if gap_val >= 0:
            gap_sub = "超额"
        else:
            gap_sub = "落后"
            gap_sub_color = "red"

    body_elements.append(_kpi_row(
        _kpi_card("回款目标（2倍奖金）", format_amount(target_val)),
        _kpi_card("在途单回款差距（2倍奖金）", format_amount(gap_val), gap_sub,
                  value_color=gap_color, sub_color=gap_sub_color),
    ))

    # ── 7月现金流预估 ───────────────────────────────────────────────
    if july_cf is not None:
        tag_text, tag_color = _july_tag(july_cf, cf_val)
        body_elements.append({
            "tag": "markdown",
            "content": (
                f"7月现金流预估：**{format_amount(july_cf)} 千元**"
                f"（<font color='{tag_color}'>{tag_text}</font>）"
            ),
            "text_size": "normal",
            "margin": "0px 0px 8px 0px",
        })

    # ── Warning (only when overall gap is negative) ──────────────────
    if gap_val is not None and gap_val < 0:
        body_elements.append(_warning_block(gap_val, "全局", month_key))

    # ── Leader summary ──────────────────────────────────────────────
    body_elements.append(_section_title("Leader 摘要"))
    body_elements.append(_build_leader_summary(data, cf_data))

    # ── Risk rankings ────────────────────────────────────────────────
    ranked_teams = _add_worst_rankings(body_elements, data, cf_data, mapping)

    # ── Management insights for ranked teams ────────────────────────
    _add_management_insights(body_elements, insights or [], ranked_teams)

    # Footer
    body_elements.append(_footer(month_label_str))

    return {
        "schema": "2.0",
        "config": _card_config(),
        "header": _header(month_label_str, subtitle),
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 20px 12px",
            "elements": body_elements,
        },
    }


# ── Output ───────────────────────────────────────────────────────────────

def _write_card(path, card):
    """Write a single card JSON to *path*."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _send_card(path, open_id, dry_run=False):
    """Send one card via lark-cli. Returns (ok, message)."""
    cmd = [
        "lark-cli", "im", "+messages-send",
        "--user-id", open_id,
        "--msg-type", "interactive",
        "--content", path.read_text(encoding="utf-8"),
        "--as", "user",
    ]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30,
        cwd=BASE_DIR,
    )
    try:
        data = json.loads(result.stdout)
        if data.get("ok"):
            return True, data["data"].get("message_id", "sent")
        return False, data.get("error", {}).get("message", result.stderr.strip())
    except json.JSONDecodeError:
        return False, result.stderr.strip() or result.stdout.strip()


# ── Main ────────────────────────────────────────────────────────────────

def main():
    send = "--send" in sys.argv
    dry_run = "--dry-run" in sys.argv
    if send and not dry_run:
        print("⚠️  ⚠️  即将发送消息到飞书，收件人将收到真实通知 ⚠️  ⚠️")
        print()
        print("   添加 --dry-run 预览请求，或直接回车继续发送。")
        print()
        try:
            input("按 Enter 继续，Ctrl-C 取消... ")
        except (KeyboardInterrupt, EOFError):
            print("\n已取消。")
            return
        print()

    notification_config = load_yaml(NOTIFICATION_CONFIG)
    mapping = load_yaml(MAPPING_FILE)
    insights = load_insights()

    latest_file = find_latest_month()
    month_key = month_key_from_path(latest_file)
    month_label_str = month_label(month_key)

    print(f"📊 最新数据: {month_label_str}  ({latest_file.name})")
    data = parse_md(latest_file)
    print(f"   {len(data)} 个指标已解析")

    # Previous month for MoM
    prev_file = DATA_DIR / f"{prev_month_key(month_key)}.md"
    prev_data = None
    if prev_file.exists():
        prev_data = parse_md(prev_file)
        print(f"   上月数据: {prev_file.name} ({len(prev_data)} 个指标)")
    else:
        print(f"   ⚠️ 上月数据缺失，环比无法计算")
    print()

    out_dir = BASE_DIR / ".cards"
    out_dir.mkdir(exist_ok=True)

    for recipient in notification_config["recipients"]:
        name = recipient["name"]
        open_id = recipient.get("open_id", "")

        if recipient.get("card_type") == "overall":
            card = build_overall_card(
                recipient, data, prev_data, month_label_str, month_key, mapping,
                insights,
            )
        else:
            card = build_card(
                recipient, data, prev_data, month_label_str, month_key, mapping
            )
        path = out_dir / f"{name}.json"
        _write_card(path, card)

        scope_count = len(recipient.get("scopes", []))
        if scope_count:
            status = f"{scope_count} scope{'s' if scope_count > 1 else ''}"
        else:
            status = "整体卡"

        if send and open_id:
            ok, msg = _send_card(path, open_id, dry_run=dry_run)
            if ok:
                status += f" → ✅ 已发送 ({msg})"
            else:
                status += f" → ❌ 发送失败: {msg}"
        elif send and not open_id:
            status += " → ⚠️ 缺少 open_id，跳过发送"

        print(f"  {name} ({status})")

    if not send:
        print()
        print(f"发送: python scripts/notify.py --send [--dry-run]")


if __name__ == "__main__":
    main()
