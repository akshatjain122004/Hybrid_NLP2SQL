import os

from app.llm.prompt_builder import build_prompt


def call_llm_fallback(raw_query: str, schema_links: dict, intent: str, entities: dict, client=None) -> str:
    if client is None:
        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv()
        client = OpenAI()

    prompt = build_prompt(raw_query, schema_links, intent, entities)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content.strip().strip("`")
    if text.lower().startswith("sql"):
        text = text[3:].strip()
    return text