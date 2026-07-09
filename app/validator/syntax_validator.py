import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError


def validate_syntax(sql: str, dialect: str = "postgres") -> dict:
    try:
        parsed = sqlglot.parse_one(sql, dialect=dialect, error_level=sqlglot.ErrorLevel.RAISE)
        if not isinstance(parsed, exp.Query):
            return {"valid": False, "error": "Parsed expression is not a query statement (e.g., SELECT)"}
        return {"valid": True, "error": None}
    except (ParseError, TokenError) as e:
        return {"valid": False, "error": str(e)}