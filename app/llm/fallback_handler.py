import os

from app.llm.prompt_builder import build_prompt


def call_llm_fallback(raw_query: str, schema_links: dict, intent: str, entities: dict, client=None) -> dict:
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    prompt = build_prompt(raw_query, schema_links, intent, entities)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content.strip().strip("`")
    if text.lower().startswith("sql"):
        text = text[3:].strip()

    usage = getattr(response, "usage", None)
    tokens = {
        "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
    }
    return {"sql": text, "tokens": tokens}