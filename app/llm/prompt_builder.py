def build_prompt(raw_query: str, schema_links: dict, intent: str, entities: dict) -> str:
    lines = []
    for table, cols in schema_links.items():
        col_str = ", ".join(cols) if cols else "(table referenced, no specific column)"
        lines.append(f"- {table}: {col_str}")
    tables_block = "\n".join(lines) if lines else "(no tables confidently linked)"

    return f"""You are a SQL generator for a PostgreSQL e-commerce database.
Detected intent: {intent}
Extracted entities: {entities}

Relevant tables/columns identified by the schema linker:
{tables_block}

User question: "{raw_query}"

Return ONLY the SQL query. No explanation, no markdown formatting, no backticks."""