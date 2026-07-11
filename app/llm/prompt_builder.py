import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "schema.json"


def _load_schema(path: Path = SCHEMA_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def _format_full_schema(schema: dict) -> str:
    lines = []
    for table, info in schema["tables"].items():
        cols = ", ".join(f"{col} ({dtype})" for col, dtype in info["columns"].items())
        lines.append(f"- {table} (PK: {info['primary_key']}): {cols}")
        for fk_col, fk in info.get("foreign_keys", {}).items():
            lines.append(f"    FK: {table}.{fk_col} -> {fk['referenced_table']}.{fk['referenced_column']}")
    return "\n".join(lines)


def build_prompt(raw_query: str, schema_links: dict, intent: str, entities: dict, schema: dict = None) -> str:
    schema = schema or _load_schema()
    schema_block = _format_full_schema(schema)

    return f"""You are a SQL generator for a PostgreSQL e-commerce database.
This system ONLY answers questions about existing data using read-only SELECT queries.
Never generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or any statement that
creates, modifies, or deletes data -- even if the user asks for it directly.

Use ONLY the exact table and column names listed below. Do not guess, abbreviate, or
assume a generic column name -- e.g. the primary key of customers is customer_id, NOT id.

Full database schema:
{schema_block}

If the user's request cannot be answered with a SELECT query against this schema
(e.g. they're asking to generate, insert, or modify data), respond with exactly:
NOT_SUPPORTED

Detected intent: {intent}
User question: "{raw_query}"

Return ONLY the SQL query, or the exact text NOT_SUPPORTED. No explanation, no markdown, no backticks."""