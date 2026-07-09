from dataclasses import dataclass, field
from typing import List, Optional, Any

from app.db.schema_graph import resolve_joins


@dataclass
class WhereCondition:
    table: str
    column: str
    operator: str  # =, >, <, >=, <=, LIKE, BETWEEN, IN
    value: Any


@dataclass
class IR:
    select: List[str] = field(default_factory=list)
    from_: Optional[str] = None
    joins: List[dict] = field(default_factory=list)
    where: List[WhereCondition] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    order_by: Optional[str] = None
    order_dir: str = "ASC"
    limit: Optional[int] = None
    aggregation: Optional[str] = None
    intent: Optional[str] = None


def build_ir(intent: str, entities: dict, schema_links: dict, graph) -> IR:
    """
    schema_links: {table_name: [col1, col2, ...]}  -- empty list = table-only reference
    entities contract by intent:
      lookup       -> {}  (optionally {"where": [...]})
      filter       -> {"where": [{"column": "table.col", "operator": "=", "value": ...}]}
      aggregation  -> {"aggregation": "SUM", "aggregation_column": "table.col"}
      top_n        -> {"order_by": "table.col", "order_dir": "DESC", "limit": 10}
      group_by     -> {"group_by": ["table.col"], "aggregation": "COUNT", "aggregation_column": "table.col"}
      comparison   -> same shape as group_by
    """
    ir = IR(intent=intent)

    tables_needed = list(schema_links.keys())
    ir.from_, ir.joins = resolve_joins(graph, tables_needed)

    linked_columns = [
        f"{table}.{col}"
        for table, cols in schema_links.items()
        for col in cols
    ]

    if intent == "aggregation":
        agg_col = entities.get("aggregation_column") or (linked_columns[0] if linked_columns else None)
        ir.aggregation = entities.get("aggregation", "COUNT")
        ir.select = [f"{ir.aggregation}({agg_col})"]

    elif intent in ("group_by", "comparison"):
        ir.group_by = entities.get("group_by", linked_columns)
        agg_col = entities.get("aggregation_column") or (linked_columns[0] if linked_columns else None)
        ir.aggregation = entities.get("aggregation", "COUNT")
        ir.select = ir.group_by + [f"{ir.aggregation}({agg_col})"]

    elif intent == "top_n":
        ir.select = linked_columns or ["*"]
        ir.order_by = entities.get("order_by")
        ir.order_dir = entities.get("order_dir", "DESC")
        ir.limit = entities.get("limit", 10)

    else:  # lookup, filter
        ir.select = linked_columns or ["*"]

    for cond in entities.get("where", []):
        table, column = cond["column"].split(".")
        ir.where.append(WhereCondition(table=table, column=column,
                                        operator=cond["operator"], value=cond["value"]))

    return ir