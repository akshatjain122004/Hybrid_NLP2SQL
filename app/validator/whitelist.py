import json
from pathlib import Path

import sqlglot
from sqlglot import exp

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "schema.json"


def _load_schema(path: Path = SCHEMA_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def check_whitelist(sql: str, schema: dict = None, dialect: str = "postgres") -> dict:
    """
    Note: column check is name-based, not table-scoped -- see prior caveat. Also
    excludes SELECT-list aliases (e.g. `SUM(...) AS total_profit`) from the check,
    since those are legitimate query-defined names, not schema references -- and
    they're commonly reused in ORDER BY / GROUP BY, which is valid standard SQL.
    """
    schema = schema or _load_schema()
    valid_tables = set(schema["tables"].keys())
    valid_columns = set()
    for table_info in schema["tables"].values():
        valid_columns.update(table_info["columns"].keys())

    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as e:
        return {"allowed": False, "bad_tables": [], "bad_columns": [], "error": f"unparseable: {e}"}

    select_aliases = set()
    for select_stmt in tree.find_all(exp.Select):
        for projection in select_stmt.expressions:
            alias = projection.alias
            if alias:
                select_aliases.add(alias)

    used_tables = {t.name for t in tree.find_all(exp.Table)}
    used_columns = {c.name for c in tree.find_all(exp.Column) if c.name != "*"}

    bad_tables = sorted(used_tables - valid_tables)
    bad_columns = sorted(used_columns - valid_columns - select_aliases)

    return {
        "allowed": not (bad_tables or bad_columns),
        "bad_tables": bad_tables,
        "bad_columns": bad_columns,
        "error": None,
    }