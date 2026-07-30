"""Generate traceable management insights from the latest monthly data."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_FILE = BASE_DIR / "knowledge-graph.yaml"
OUTPUT_FILE = DATA_DIR / "knowledge-graph-latest.json"

sys.path.insert(0, str(SCRIPT_DIR))
from notify import (
    METRIC_GAP_2X,
    METRIC_PMS_RECEIVABLE,
    METRIC_REVENUE_TARGET_2X,
    find_latest_cashflow,
    find_latest_month,
    load_yaml,
    month_key_from_path,
    parse_md,
)

METRIC_YEAR_END_GAP_2X = "全年回款差距（+超额/-落后）-2倍奖金"


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def normalize_amount_format(text):
    """Keep model-written monetary amounts in the dashboard's 千元 format."""
    if not isinstance(text, str):
        return text

    def add_grouping(match):
        amount = Decimal(match.group(1).replace(",", ""))
        return f"{amount:,.2f} 千元"

    return re.sub(
        r"(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*千元",
        add_grouping,
        text,
    )


def next_cashflow_forecast(data, month):
    """Return the next month's forecast metric name and row, if available."""
    next_month = month + 1
    if next_month > 12:
        return None, None
    metric = f"{next_month}月现金流预估"
    return metric, data.get(metric)


def entities(mapping, knowledge):
    """Return ordered big-team, sub-team, and small-team facts to inspect."""
    result = []
    leaders = mapping.get("leaders", {})
    leader_columns = knowledge.get("leader_columns", {})
    aliases = mapping.get("aggregate_column_names", {})
    virtual_by_subteam = {
        item["sub_team"]: item["name"]
        for item in mapping.get("virtual_aggregates", [])
    }

    for leader, subteams in leaders.items():
        leader_column = leader_columns.get(leader)
        if leader_column:
            result.append({
                "level": "big_team",
                "team": leader_column,
                "leader": leader,
                "column": leader_column,
            })
        for subteam, small_teams in subteams.items():
            subteam_column = aliases.get(subteam, subteam)
            result.append({
                "level": "sub_team",
                "team": subteam,
                "leader": leader,
                "column": subteam_column,
            })
            virtual_name = virtual_by_subteam.get(subteam)
            if virtual_name:
                result.append({
                    "level": "small_team",
                    "team": virtual_name,
                    "leader": leader,
                    "column": virtual_name,
                })
            for small_team in small_teams:
                result.append({
                    "level": "small_team",
                    "team": small_team,
                    "leader": leader,
                    "column": small_team,
                })
    return result


def ranked_team_names(data, cashflow, mapping):
    """Return the first three distinct teams used by the overall risk board."""
    team_leader = {}
    for leader, subteams in mapping.get("leaders", {}).items():
        for teams in subteams.values():
            for team in teams:
                team_leader[team] = leader

    cf_ranked = []
    gap_ranked = []
    for team in team_leader:
        cf_value = number(cashflow.get(team) if cashflow else None)
        if cf_value is not None:
            cf_ranked.append((team, cf_value))
        gap_value = number(data.get(METRIC_GAP_2X, {}).get(team))
        if gap_value is not None:
            gap_ranked.append((team, gap_value))

    cf_ranked.sort(key=lambda item: item[1])
    gap_ranked.sort(key=lambda item: item[1])
    ranked = []
    for team, _ in cf_ranked[:3] + gap_ranked[:3]:
        if team not in ranked:
            ranked.append(team)
        if len(ranked) == 3:
            break
    return set(ranked)


def fact(entity, metric_values):
    return {
        "level": entity["level"],
        "team": entity["team"],
        "leader": entity["leader"],
        "column": entity["column"],
        "values": metric_values,
    }


def add_insight(output, rule, entity, values, explanation, action, details=None):
    item = fact(entity, values)
    item.update({
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "risk_level": rule["risk_level"],
        "explanation": explanation,
        "action": action,
    })
    if details:
        item["details"] = details
    output.append(item)


def load_local_env():
    """Load simple KEY=VALUE pairs from the local, git-ignored env file."""
    values = dict(os.environ)
    env_path = BASE_DIR / ".env.local"
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def generate_llm_insights(knowledge, data, entities_list, ranked_teams, insights,
                          cashflow_name, cashflow, forecast_name, forecast):
    """Ask DeepSeek to turn ranked-team facts and durable rules into prose."""
    env = load_local_env()
    api_key = env.get("DEEPSEEK_API_KEY")
    if not api_key:
        return []

    entity_by_team = {
        entity["team"]: entity
        for entity in entities_list
        if entity["level"] == "small_team"
    }
    hits_by_team = {}
    for item in insights:
        if item["team"] in ranked_teams:
            hits_by_team.setdefault(item["team"], []).append({
                "rule": item["rule_name"],
                "risk_level": item["risk_level"],
                "values": item["values"],
                "action": item["action"],
            })

    teams = []
    for team, entity in entity_by_team.items():
        if team not in ranked_teams:
            continue
        column = entity["column"]
        teams.append({
            "team": team,
            "leader": entity["leader"],
            "current_cashflow": (cashflow or {}).get(column),
            "current_cashflow_metric": cashflow_name,
            "next_month_cashflow": (forecast or {}).get(column),
            "next_month_cashflow_metric": forecast_name,
            "pms_in_transit": data.get(METRIC_PMS_RECEIVABLE, {}).get(column),
            "two_x_target": data.get(METRIC_REVENUE_TARGET_2X, {}).get(column),
            "two_x_gap": data.get(METRIC_GAP_2X, {}).get(column),
            "matched_rules": hits_by_team.get(team, []),
        })

    rules = [
        {key: rule.get(key) for key in ("id", "name", "explanation", "action", "scope")}
        for rule in knowledge.get("rules", [])
    ]
    prompt = {
        "knowledge": rules,
        "ranked_team_facts": teams,
        "requirements": [
            "只分析输入中的排名团队和数据，不得编造数据、原因或已完成的动作。",
            "输出给公司老板看的管理层信息，判断要具体、简洁、可执行。",
            "所有金额的原始单位都是千元，输出金额时必须使用千元，禁止写万元或自行换算。",
            "所有金额必须保留两位小数并使用千分位逗号，例如 -1,547.45 千元。",
            "cashflow_analysis：比较当月累计现金流与下月预估，说明缺口是否扩大；PMS在途金额大于等于下月预估缺口时只能说理论上可覆盖，若仅高出缺口不超过10%，要说明两者基本持平、现金流转正挑战较大；并紧跟回款动作。",
            "order_analysis：说明当前2倍奖金在途回款差距是否符合出单计划；不符合时说明今年目标风险和业务Owner动作，符合时说明风险不大并说明继续出单。",
            "不要输出剩余月份、每月应出单额、出单还差金额、目标金额等派生数字；全年订单分析只引用当前2倍奖金在途回款差距。",
            "每个分析字段用1到2句话，必须包含关键数据依据和措施。",
            "只返回JSON，不要Markdown，不要解释JSON之外的内容。",
        ],
        "output_schema": {
            "insights": [
                {
                    "team": "团队名称",
                    "leader": "负责人",
                    "risk_level": "high 或 attention",
                    "cashflow_analysis": "现金流分析",
                    "order_analysis": "全年订单分析",
                }
            ]
        },
    }
    body = json.dumps({
        "model": env.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        "messages": [
            {
                "role": "system",
                "content": "你是负责给管理层写团队财务经营分析的资深财务分析师。",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 2500,
    }).encode("utf-8")
    request = Request(
        "https://api.deepseek.com/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (HTTPError, URLError, KeyError, IndexError, TypeError, ValueError, TimeoutError):
        print("DeepSeek insight generation failed; using deterministic insights.", file=sys.stderr)
        return []

    allowed = set(ranked_teams)
    result = []
    for item in parsed.get("insights", []):
        if not isinstance(item, dict) or item.get("team") not in allowed:
            continue
        if not item.get("cashflow_analysis") and not item.get("order_analysis"):
            continue
        result.append({
            "team": item["team"],
            "leader": item.get("leader") or entity_by_team[item["team"]]["leader"],
            "risk_level": item.get("risk_level", "attention"),
            "cashflow_analysis": normalize_amount_format(item.get("cashflow_analysis", "")),
            "order_analysis": normalize_amount_format(item.get("order_analysis", "")),
        })
    return result


def generate():
    knowledge = load_yaml(KNOWLEDGE_FILE) or {}
    mapping = load_yaml(BASE_DIR / "team-mapping.yaml") or {}
    latest_file = find_latest_month()
    month_key = month_key_from_path(latest_file)
    month = int(month_key[5:7])
    data = parse_md(latest_file)
    cashflow_name, cashflow = find_latest_cashflow(data)
    forecast_name, forecast = next_cashflow_forecast(data, month)
    ranked_teams = ranked_team_names(data, cashflow, mapping)
    pms = data.get(METRIC_PMS_RECEIVABLE, {})
    target = data.get(METRIC_REVENUE_TARGET_2X, {})
    gap = data.get(METRIC_GAP_2X, {})
    year_end_gap = data.get(METRIC_YEAR_END_GAP_2X, {})

    entities_list = entities(mapping, knowledge)
    insights = []
    for entity in entities_list:
        column = entity["column"]
        cf = number(cashflow.get(column) if cashflow else None)
        forecast_value = number(forecast.get(column) if forecast else None)
        pms_value = number(pms.get(column))
        target_value = number(target.get(column))
        gap_value = number(gap.get(column))
        year_end_value = number(year_end_gap.get(column))

        # Rule 1: a negative current cash flow must first be checked against
        # the next month's forecast before PMS is evaluated.
        if cf is not None and cf < 0:
            if forecast_value is None:
                rule_id = "negative_cumulative_cashflow"
            elif forecast_value < 0:
                rule_id = "cashflow_negative_next_month_still_negative"
            else:
                rule_id = "cashflow_negative_next_month_improves"
            rule = next(r for r in knowledge["rules"] if r["id"] == rule_id)
            values = {cashflow_name: cf}
            if forecast_name:
                values[forecast_name] = forecast_value
            add_insight(
                insights, rule, entity,
                values, rule["explanation"], rule["action"],
            )

        # Rule 2: only inspect PMS when both current and next-month cash flow
        # are negative.
        if cf is not None and cf < 0 and forecast_value is not None and forecast_value < 0 and pms_value is not None:
            forecast_gap = abs(forecast_value)
            if pms_value >= forecast_gap:
                rule_id = "pms_in_transit_can_cover_cashflow_gap"
            else:
                rule_id = "pms_in_transit_cannot_cover_cashflow_gap"
            rule = next(r for r in knowledge["rules"] if r["id"] == rule_id)
            add_insight(
                insights, rule, entity,
                {cashflow_name: cf, METRIC_PMS_RECEIVABLE: pms_value},
                rule["explanation"], rule["action"],
                {"cashflow_gap": forecast_gap, "coverage_ratio": pms_value / forecast_gap if forecast_gap else None},
            )

        # Rule 3: before October, compare the negative gap with the
        # remaining monthly order progress; October onward uses the deadline.
        if column in ranked_teams and gap_value is not None and target_value is not None and target_value > 0:
            if month < 10:
                remaining_months = 10 - month
                required_gap = remaining_months * target_value / 10
                if gap_value < -required_gap:
                    rule = next(r for r in knowledge["rules"] if r["id"] == "order_progress_behind_before_october")
                    add_insight(
                        insights, rule, entity,
                        {METRIC_GAP_2X: gap_value, METRIC_REVENUE_TARGET_2X: target_value},
                        rule["explanation"], rule["action"],
                        {"remaining_months": remaining_months, "required_gap": -required_gap},
                    )
                else:
                    rule = next(r for r in knowledge["rules"] if r["id"] == "order_progress_on_plan_before_october")
                    add_insight(
                        insights, rule, entity,
                        {METRIC_GAP_2X: gap_value, METRIC_REVENUE_TARGET_2X: target_value},
                        rule["explanation"], rule["action"],
                        {"remaining_months": remaining_months, "required_gap": -required_gap},
                    )
            elif month in (10, 11) and gap_value < 0:
                rule = next(r for r in knowledge["rules"] if r["id"] == "october_gap_not_ready")
                add_insight(
                    insights, rule, entity,
                    {METRIC_GAP_2X: gap_value, METRIC_REVENUE_TARGET_2X: target_value},
                    rule["explanation"], rule["action"],
                )

        if column in ranked_teams and month >= 12 and year_end_value is not None and year_end_value < 0:
            rule = next(r for r in knowledge["rules"] if r["id"] == "year_end_gap_not_met")
            add_insight(
                insights, rule, entity,
                {METRIC_YEAR_END_GAP_2X: year_end_value},
                rule["explanation"], rule["action"],
            )

    level_order = {"high": 0, "attention": 1}
    insights.sort(key=lambda item: (level_order.get(item["risk_level"], 9), item["level"], item["team"], item["rule_id"]))
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "month": month_key,
        "source_file": latest_file.name,
        "cashflow_metric": cashflow_name,
        "entities_checked": len(entities_list),
        "insights": insights,
    }
    result["llm_insights"] = generate_llm_insights(
        knowledge, data, entities_list, ranked_teams, insights,
        cashflow_name, cashflow, forecast_name, forecast,
    )
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Generated: {OUTPUT_FILE} ({len(insights)} insights)")
    return result


if __name__ == "__main__":
    generate()
