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

# ── Key metric identifiers ──────────────────────────────────────────────
METRIC_PMS_RECEIVABLE = "PMS预计回款（在途）"
METRIC_CASH_FLOW_PREFIX = "累计现金流"
METRIC_REVENUE_TARGET_2X = "回款目标（考虑2倍奖金）"
METRIC_GAP_2X = "考虑2倍奖金在途回款差距（+超额/-落后）"

# Forward-looking estimates
METRIC_JULY_CF_EST = "7月现金流预估"

# Dashboard link template (update when deployed)
DASHBOARD_URL = "https://your-dashboard.example.com"


# ── Helpers ─────────────────────────────────────────────────────────────

def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


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

    # Only show sub-breakdowns when there is at least one virtual
    # aggregate.  Without one, the scope itself is the right level of
    # detail (e.g. 前端创新 with [前端创新, 数据]).
    if not sub_breakdowns:
        return teams, []

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


def _kpi_card(label, value, sub_text=None, value_color="blue", sub_color="grey"):
    """Build a single KPI card column.

    label:      metric name shown in grey notation above the value
    value:      big number (already formatted by format_amount)
    sub_text:   optional footnote (MoM, status, etc.), grey notation
    value_color: colour for the big number (blue / red / green)
    sub_color:   colour for sub_text (grey / red / green)
    """
    elements = [
        {"tag": "markdown", "content": f"<font color='grey'>{label}</font>",
         "text_align": "center", "text_size": "notation"},
        {"tag": "markdown", "content": f"## <font color='{value_color}'>{value}</font>",
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

        # ── Row 1: PMS在途 + 累计现金流 ─────────────────────────────
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
            _kpi_card("PMS预计回款（在途）", format_amount(pms_val), pms_sub),
            _kpi_card(f"累计现金流（{cf_date_label}）", format_amount(cf_val), cf_sub,
                      value_color=cf_color),
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
            _kpi_card("在途回款差距（2倍奖金）", format_amount(gap_val), gap_sub,
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

        card = build_card(
            recipient, data, prev_data, month_label_str, month_key, mapping
        )
        path = out_dir / f"{name}.json"
        _write_card(path, card)

        scope_count = len(recipient["scopes"])
        status = f"{scope_count} scope{'s' if scope_count > 1 else ''}"

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
