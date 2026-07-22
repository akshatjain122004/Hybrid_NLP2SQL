from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from app.pipeline.normalizer import QueryNormalizer
from app.pipeline.tokenizer import QueryTokenizer
from app.pipeline.schema_linker import SchemaLinker, to_schema_links
from app.pipeline.intent_classifier import classify_intent
from app.pipeline.entity_extractor import extract_entities
from app.pipeline.template_engine import compile_via_template
from app.pipeline.ir_builder import build_ir
from app.pipeline.sql_compiler import compile_sql
from app.router.confidence_scorer import score_confidence
from app.llm.fallback_handler import call_llm_fallback
from app.db.schema_graph import build_schema_graph

HIGH_THRESHOLD = 0.75

KNOWN_CATEGORICAL_VALUES = {
    "country": ["india", "usa", "uk", "united states", "germany", "france", "canada", "japan", "brazil", "china", "australia"],
    "status": ["pending", "shipped", "delivered", "cancelled"],
    "department": ["sales", "support", "it", "marketing"],
    "payment_method": ["credit card", "paypal", "cash", "debit card"],
}


def _find_categorical_column(proper_noun: str, schema_links: dict, schema: dict):
    """
    Matches a proper noun (e.g. "India") against a curated set of known values per
    category, then looks for a column with that exact name among the schema-linked
    tables. Deliberately narrow -- a curated lookup for common filter cases (country,
    status, department, payment method), not general NER-to-column grounding for
    arbitrary free-text values. Returns (column, value) or None.
    """
    lowered = proper_noun.lower()
    for column_name, known_values in KNOWN_CATEGORICAL_VALUES.items():
        if lowered in known_values:
            for table in schema_links:
                if column_name in schema["tables"].get(table, {}).get("columns", {}):
                    return f"{table}.{column_name}", proper_noun
    return None

class PipelineState(TypedDict, total=False):
    raw_query: str
    schema_links: dict
    intent: str
    intent_confidence: float
    entities: dict
    confidence: float
    signals: dict
    sql: Optional[str]
    source: str
    error: Optional[str]
    _linked: dict
    tokens: Optional[dict]


def _find_date_column(schema_links: dict, schema: dict) -> Optional[str]:
    for table in schema_links:
        for col, dtype in schema["tables"].get(table, {}).get("columns", {}).items():
            if dtype == "timestamp":
                return f"{table}.{col}"
    return None


def translate_entities(intent: str, raw_entities: dict, schema_links: dict, schema: dict) -> dict:
    entities = {}

    if raw_entities.get("date_range"):
        date_col = _find_date_column(schema_links, schema)
        if date_col:
            entities.setdefault("where", []).append({
                "column": date_col, "operator": "BETWEEN", "value": raw_entities["date_range"],
            })

    for proper_noun in raw_entities.get("proper_nouns", []):
        match = _find_categorical_column(proper_noun, schema_links, schema)
        if match:
            column, value = match
            entities.setdefault("where", []).append({"column": column, "operator": "=", "value": value})

    if intent == "top_n":
        if raw_entities.get("numbers"):
            entities["limit"] = raw_entities["numbers"][0]
        entities["order_dir"] = raw_entities.get("order_dir") or "DESC"

    return entities


def _build_deps():
    return {
        "normalizer": QueryNormalizer(),
        "tokenizer": QueryTokenizer(),
        "linker": SchemaLinker(),
        "graph": build_schema_graph(),
    }


def preprocess_node(state, deps):
    raw = state["raw_query"]
    normalized = deps["normalizer"].normalize(raw)
    tokens = deps["tokenizer"].tokenize(normalized)
    linked = deps["linker"].link_schema(tokens)
    schema_links = to_schema_links(linked)
    intent_result = classify_intent(raw)
    raw_entities = extract_entities(raw)
    entities = translate_entities(intent_result["intent"], raw_entities, schema_links, deps["linker"].schema)
    return {
        **state,
        "schema_links": schema_links,
        "intent": intent_result["intent"],
        "intent_confidence": intent_result["confidence"],
        "entities": entities,
        "_linked": linked,
    }


def safety_gate(state):
    return "unsafe" if not state["schema_links"] else "continue"


def compile_node(state, deps):
    intent, schema_links, entities = state["intent"], state["schema_links"], state["entities"]

    sql = compile_via_template(intent, entities, schema_links)
    ir = None
    if sql is None:
        ir = build_ir(intent, entities, schema_links, deps["graph"])
        sql = compile_sql(ir)

    confidence, signals = score_confidence(state["intent_confidence"], state["_linked"], entities, intent, ir)
    return {**state, "sql": sql, "confidence": confidence, "signals": signals}


def confidence_gate(state):
    return "high" if state["confidence"] >= HIGH_THRESHOLD else "low"


def finalize_high(state):
    return {**state, "source": "compiled", "error": None}


def fallback_node(state, deps, llm_client=None):
    result = call_llm_fallback(state["raw_query"], state["schema_links"], state["intent"],
                                state["entities"], client=llm_client)
    if result["error"]:
        return {**state, "sql": None, "source": "llm_unavailable", "tokens": None, "error": result["error"]}

    sql, tokens = result["sql"], result["tokens"]
    if sql.strip() == "NOT_SUPPORTED":
        return {**state, "sql": None, "source": "unsupported", "tokens": tokens,
                "error": "This system can only answer questions about existing data -- it can't generate, insert, or modify records."}
    return {**state, "sql": sql, "source": "llm_fallback", "tokens": tokens, "error": None}


def reject_node(state):
    return {**state, "sql": None, "source": "rejected",
            "error": "No schema tables could be confidently linked -- rejected before compilation"}


def build_router(deps=None, llm_client=None):
    deps = deps or _build_deps()
    graph = StateGraph(PipelineState)

    graph.add_node("preprocess", lambda s: preprocess_node(s, deps))
    graph.add_node("compile", lambda s: compile_node(s, deps))
    graph.add_node("finalize_high", finalize_high)
    graph.add_node("fallback", lambda s: fallback_node(s, deps, llm_client))
    graph.add_node("reject", reject_node)

    graph.set_entry_point("preprocess")
    graph.add_conditional_edges("preprocess", safety_gate, {"unsafe": "reject", "continue": "compile"})
    graph.add_conditional_edges("compile", confidence_gate, {"high": "finalize_high", "low": "fallback"})
    graph.add_edge("finalize_high", END)
    graph.add_edge("fallback", END)
    graph.add_edge("reject", END)

    return graph.compile()


def run_query(text: str, compiled_graph=None) -> dict:
    compiled_graph = compiled_graph or build_router()
    return compiled_graph.invoke({"raw_query": text})