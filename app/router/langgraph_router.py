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


def _find_date_column(schema_links: dict, schema: dict) -> Optional[str]:
    for table in schema_links:
        for col, dtype in schema["tables"].get(table, {}).get("columns", {}).items():
            if dtype == "timestamp":
                return f"{table}.{col}"
    return None


def translate_entities(intent: str, raw_entities: dict, schema_links: dict, schema: dict) -> dict:
    """
    Translates entity_extractor.py's generic output into the per-intent shape
    build_ir() / template_engine.py expect.

    Known, deliberate scope limit: this only handles date-range WHERE clauses and
    top_n limit/order_dir -- the well-defined cases. It does NOT infer which column
    a proper noun (e.g. "India") should filter on, or which column to ORDER BY for
    top_n. Those require real semantic grounding this rule-based layer doesn't have.
    Leaving them empty is intentional: it lowers entity_completeness in the confidence
    scorer, which correctly routes those queries to the LLM fallback instead of
    producing a wrong deterministic answer with false confidence.
    """
    entities = {}

    if raw_entities.get("date_range"):
        date_col = _find_date_column(schema_links, schema)
        if date_col:
            entities.setdefault("where", []).append({
                "column": date_col, "operator": "BETWEEN", "value": raw_entities["date_range"],
            })

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
    sql = call_llm_fallback(state["raw_query"], state["schema_links"], state["intent"],
                             state["entities"], client=llm_client)
    return {**state, "sql": sql, "source": "llm_fallback", "error": None}


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