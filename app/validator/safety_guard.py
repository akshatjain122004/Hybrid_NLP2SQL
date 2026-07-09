import re
import sqlglot
from sqlglot import exp

BLOCKED_KEYWORDS = {"insert", "update", "delete", "drop", "alter", "truncate",
                     "create", "grant", "revoke", "merge"}


def check_safety(sql: str, dialect: str = "postgres") -> dict:
    # string-level guard: cheap first line of defense, catches obvious cases fast
    lowered = sql.lower()
    for kw in BLOCKED_KEYWORDS:
        if re.search(rf"\b{kw}\b", lowered):
            return {"safe": False, "reason": f"blocked keyword detected: {kw}"}

    # AST-level guard: the real check -- every statement must parse as a single SELECT
    try:
        statements = [s for s in sqlglot.parse(sql, dialect=dialect) if s is not None]
    except Exception as e:
        return {"safe": False, "reason": f"unparseable: {e}"}

    if len(statements) != 1:
        return {"safe": False, "reason": "multiple statements are not allowed"}

    if not isinstance(statements[0], exp.Select):
        return {"safe": False, "reason": f"only SELECT statements allowed, got {type(statements[0]).__name__}"}

    return {"safe": True, "reason": None}