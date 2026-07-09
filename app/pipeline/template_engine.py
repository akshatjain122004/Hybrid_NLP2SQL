import json
from pathlib import Path

from app.pipeline.sql_compiler import format_value

TEMPLATES_PATH = Path(__file__).resolve().parents[2] / "schema" / "templates.json"

_TEMPLATES = None


def _load_templates(path: Path = TEMPLATES_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {(t["intent"], tuple(sorted(t["tables"]))): t for t in raw}


def _get_templates():
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = _load_templates()
    return _TEMPLATES


def _build_where_clause(where_conditions: list) -> str:
    if not where_conditions:
        return ""
    clauses = [f"{c['column']} {c['operator']} {format_value(c['value'])}" for c in where_conditions]
    return " WHERE " + " AND ".join(clauses)


def match_template(intent: str, schema_links: dict):
    key = (intent, tuple(sorted(schema_links.keys())))
    return _get_templates().get(key)


def fill_template(template: dict, entities: dict, schema_links: dict) -> str:
    select_cols = [f"{table}.{col}" for table, cols in schema_links.items() for col in cols]
    select = ", ".join(select_cols) if select_cols else template.get("default_select", "*")
    group_by_clause = ""
    order_clause = ""
    limit_clause = ""

    if template["intent"] == "aggregation":
        agg = entities.get("aggregation", template.get("default_aggregation", "COUNT"))
        agg_col = entities.get("aggregation_column", template.get("default_aggregation_column"))
        select = f"{agg}({agg_col})"

    elif template["intent"] in ("group_by", "comparison"):
        group_cols = entities.get("group_by", template.get("default_group_by", []))
        agg = entities.get("aggregation", template.get("default_aggregation", "COUNT"))
        agg_col = entities.get("aggregation_column", template.get("default_aggregation_column"))
        select = ", ".join(group_cols + [f"{agg}({agg_col})"])
        group_by_clause = " GROUP BY " + ", ".join(group_cols)

    elif template["intent"] == "top_n":
        order_col = entities.get("order_by", template.get("default_order_by"))
        order_dir = entities.get("order_dir", "DESC")
        limit = entities.get("limit", template.get("default_limit", 10))
        order_clause = f" ORDER BY {order_col} {order_dir}"
        limit_clause = f" LIMIT {limit}"

    where_clause = _build_where_clause(entities.get("where", []))

    return template["sql"].format(
        select=select, where_clause=where_clause,
        group_by_clause=group_by_clause, order_clause=order_clause, limit_clause=limit_clause,
    )


def compile_via_template(intent: str, entities: dict, schema_links: dict):
    """Returns SQL string on match, or None -- caller falls back to ir_builder + sql_compiler."""
    template = match_template(intent, schema_links)
    if template is None:
        return None
    return fill_template(template, entities, schema_links)