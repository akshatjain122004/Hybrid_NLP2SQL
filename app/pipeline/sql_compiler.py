from app.pipeline.ir_builder import IR


def format_value(value):
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(format_value(v) for v in value) + ")"
    return f"'{value}'"


def compile_sql(ir: IR) -> str:
    if not ir.select:
        raise ValueError("IR has no SELECT columns")
    if not ir.from_:
        raise ValueError("IR has no FROM table")

    parts = [f"SELECT {', '.join(ir.select)}", f"FROM {ir.from_}"]

    for join in ir.joins:
        parts.append(f"JOIN {join['table']} ON {join['on']}")

    if ir.where:
        clauses = []
        for cond in ir.where:
            col = f"{cond.table}.{cond.column}"
            op = cond.operator.upper()
            if op == "BETWEEN":
                lo, hi = cond.value
                clauses.append(f"{col} BETWEEN {format_value(lo)} AND {format_value(hi)}")
            elif op == "IN":
                clauses.append(f"{col} IN {format_value(cond.value)}")
            elif op in ("=", "!=") and isinstance(cond.value, str):
                # case-insensitive by design -- exact casing in the DB isn't guaranteed
                # (e.g. status stored as 'Cancelled', filter value coming in as 'cancelled')
                clauses.append(f"LOWER({col}) {op} LOWER({format_value(cond.value)})")
            else:
                clauses.append(f"{col} {cond.operator} {format_value(cond.value)}")
        parts.append("WHERE " + " AND ".join(clauses))

    if ir.group_by:
        parts.append(f"GROUP BY {', '.join(ir.group_by)}")

    if ir.order_by:
        parts.append(f"ORDER BY {ir.order_by} {ir.order_dir}")

    if ir.limit:
        parts.append(f"LIMIT {ir.limit}")

    return "\n".join(parts) + ";"
