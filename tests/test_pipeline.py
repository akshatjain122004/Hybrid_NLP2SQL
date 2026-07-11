from app.pipeline.ir_builder import build_ir
from app.db.schema_graph import build_schema_graph
from app.db.schema_graph import resolve_joins
import pytest

ir_test_cases = [
    dict(
        name="lookup_single_table",
        intent="lookup", entities={},
        schema_links={"customers": ["email"]},
        expect=dict(from_="customers", select=["customers.email"], joins=0),
    ),
    dict(
        name="filter_where",
        intent="filter",
        entities={"where": [{"column": "orders.status", "operator": "=", "value": "shipped"}]},
        schema_links={"orders": []},
        expect=dict(from_="orders", select=["*"], where_len=1),
    ),
    dict(
        name="aggregation_total_revenue",
        intent="aggregation",
        entities={"aggregation": "SUM", "aggregation_column": "orders.total_amount"},
        schema_links={"orders": []},
        expect=dict(select=["SUM(orders.total_amount)"], aggregation="SUM"),
    ),
    dict(
        name="top_n_products_by_price",
        intent="top_n",
        entities={"order_by": "products.price", "order_dir": "DESC", "limit": 5},
        schema_links={"products": ["product_name", "price"]},
        expect=dict(select=["products.product_name", "products.price"], limit=5, order_dir="DESC"),
    ),
    dict(
        name="group_by_orders_per_employee",
        intent="group_by",
        entities={"group_by": ["employees.employee_name"], "aggregation": "COUNT", "aggregation_column": "orders.order_id"},
        schema_links={"employees": ["employee_name"], "orders": []},
        expect=dict(group_by=["employees.employee_name"],
                     select=["employees.employee_name", "COUNT(orders.order_id)"], joins=1),
    ),
    dict(
        name="filter_join_two_tables",
        intent="filter",
        entities={"where": [{"column": "suppliers.country", "operator": "=", "value": "India"}]},
        schema_links={"products": ["product_name"], "suppliers": []},
        expect=dict(select=["products.product_name"], where_len=1, joins=1),
    ),
    dict(
        name="lookup_two_tables",
        intent="lookup", entities={},
        schema_links={"customers": ["city"], "orders": ["order_date"]},
        expect=dict(select=["customers.city", "orders.order_date"], joins=1),
    ),
    dict(
        name="aggregation_avg_with_where",
        intent="aggregation",
        entities={"aggregation": "AVG", "aggregation_column": "orders.total_amount",
                   "where": [{"column": "customers.country", "operator": "=", "value": "USA"}]},
        schema_links={"orders": [], "customers": []},
        expect=dict(select=["AVG(orders.total_amount)"], where_len=1, joins=1),
    ),
    dict(
        name="comparison_sales_by_category",
        intent="comparison",
        entities={"group_by": ["categories.category_name"], "aggregation": "SUM", "aggregation_column": "order_items.quantity"},
        schema_links={"categories": ["category_name"], "products": [], "order_items": []},
        expect=dict(group_by=["categories.category_name"], joins=2),
    ),
    dict(
        name="top_n_no_explicit_columns",
        intent="top_n",
        entities={"order_by": "products.rating", "limit": 3},
        schema_links={"products": []},
        expect=dict(select=["*"], limit=3, order_dir="DESC"),
    ),
]

join_test_cases = [
    (["customers"],                                                          "customers", 0),
    (["products", "categories"],                                             "products", 1),
    (["orders", "customers"],                                                "orders", 1),
    (["order_items", "products", "orders", "customers"],                     "order_items", 3),
    (["payments", "orders", "customers"],                                    "payments", 2),
    (["products", "suppliers"],                                              "products", 1),
    (["order_items", "orders", "employees"],                                 "order_items", 2),
    (["payments", "products"],                                               "payments", 3),
    (["employees", "customers"],                                             "employees", 2),
    (["categories", "products", "order_items", "orders", "customers"],       "categories", 4),
]

def test_joins():
    graph = build_schema_graph()
    for tables, expected_anchor, expected_join_count in join_test_cases:
        anchor, joins = resolve_joins(graph, tables)
        assert anchor == expected_anchor
        assert len(joins) == expected_join_count, f"{tables}: got {joins}"

def test_ir_builder():
    graph = build_schema_graph()
    for case in ir_test_cases:
        ir = build_ir(case["intent"], case["entities"], case["schema_links"], graph)
        exp = case["expect"]
        if "from_" in exp:
            assert ir.from_ == exp["from_"], case["name"]
        if "select" in exp:
            assert ir.select == exp["select"], f'{case["name"]}: got {ir.select}'
        if "joins" in exp:
            assert len(ir.joins) == exp["joins"], f'{case["name"]}: got {ir.joins}'
        if "where_len" in exp:
            assert len(ir.where) == exp["where_len"], case["name"]
        if "group_by" in exp:
            assert ir.group_by == exp["group_by"], case["name"]
        if "aggregation" in exp:
            assert ir.aggregation == exp["aggregation"], case["name"]
        if "limit" in exp:
            assert ir.limit == exp["limit"], case["name"]
        if "order_dir" in exp:
            assert ir.order_dir == exp["order_dir"], case["name"]
            
from app.pipeline.sql_compiler import compile_sql

def test_sql_compiler():
    graph = build_schema_graph()

    ir = build_ir("filter",
                   {"where": [{"column": "orders.status", "operator": "=", "value": "shipped"}]},
                   {"orders": []}, graph)
    assert "WHERE orders.status = 'shipped'" in compile_sql(ir)

    ir = build_ir("aggregation",
                   {"aggregation": "SUM", "aggregation_column": "orders.total_amount"},
                   {"orders": []}, graph)
    assert "SELECT SUM(orders.total_amount)" in compile_sql(ir)

    ir = build_ir("top_n",
                   {"order_by": "products.price", "order_dir": "DESC", "limit": 5},
                   {"products": ["product_name", "price"]}, graph)
    sql = compile_sql(ir)
    assert "ORDER BY products.price DESC" in sql
    assert "LIMIT 5" in sql

    ir = build_ir("filter",
                   {"where": [{"column": "suppliers.country", "operator": "=", "value": "India"}]},
                   {"products": ["product_name"], "suppliers": []}, graph)
    assert "JOIN suppliers ON products.supplier_id = suppliers.supplier_id" in compile_sql(ir)
    
from app.pipeline.entity_extractor import extract_entities

def test_entity_extractor():
    r = extract_entities("Top 5 products by rating")
    assert r["numbers"] == [5]
    assert r["order_dir"] == "DESC"

    r = extract_entities("Show orders from last month")
    assert r["date_phrase"] == "last month"
    assert r["date_range"] is not None

    r = extract_entities("List customers in India")
    assert "India" in r["proper_nouns"]

    r = extract_entities("Show the lowest rated products")
    assert r["order_dir"] == "ASC"

    r = extract_entities("Orders placed this year")
    assert r["date_phrase"] == "this year"
    
from app.pipeline.intent_classifier import classify_intent

def test_intent_classifier():
    assert classify_intent("Show all customers")["intent"] == "lookup"
    assert classify_intent("Total revenue this month")["intent"] == "aggregation"
    assert classify_intent("Top 5 products by rating")["intent"] == "top_n"
    assert classify_intent("Sales by category")["intent"] == "group_by"
    assert classify_intent("Orders where status is shipped")["intent"] == "filter"
    assert classify_intent("Compare revenue this year vs last year")["intent"] == "comparison"
    
from app.pipeline.schema_linker import SchemaLinker, to_schema_links
from app.pipeline.intent_classifier import classify_intent

_linker = SchemaLinker()

# def _tokenize(text: str):
#     # placeholder until tokenizer.py (Phase 1) exists -- no lemmatization yet
#     return [{"text": w, "lemma": w.lower()} for w in text.split()]

def run_pipeline(text: str) -> str:
    normalized = _normalizer.normalize(text)
    tokens = _tokenizer.tokenize(normalized)
    linked = _linker.link_schema(tokens)
    schema_links = to_schema_links(linked)
    intent = classify_intent(text)["intent"]
    graph = build_schema_graph()
    ir = build_ir(intent, {}, schema_links, graph)
    return compile_sql(ir)

def test_integration_smoke():
    sql = run_pipeline("customer city")
    assert "customers" in sql

    sql = run_pipeline("employee department")
    assert "employees" in sql
    
from app.pipeline.normalizer import QueryNormalizer
from app.pipeline.tokenizer import QueryTokenizer

_normalizer = QueryNormalizer()
_tokenizer = QueryTokenizer()

def test_normalizer_fillers():
    assert _normalizer.normalize("Can you show me all customers") == "all customers"

def test_date_placeholder_survives_tokenization():
    normalized = _normalizer.normalize("orders last month")
    tokens = _tokenizer.tokenize(normalized)
    date_tokens = [t for t in tokens if t["lemma"].startswith("date_")]
    assert len(date_tokens) == 1, f"expected exactly 1 date token, got: {tokens}"

def test_date_token_not_fuzzy_matched():
    normalized = _normalizer.normalize("orders last month")
    tokens = _tokenizer.tokenize(normalized)
    linked = _linker.link_schema(tokens)
    linked_columns = [m.get("column") for m in linked.values() if "column" in m]
    assert "last_name" not in linked_columns
    
from app.pipeline.template_engine import compile_via_template

def test_template_lookup_match():
    sql = compile_via_template("lookup", {}, {"customers": []})
    assert sql is not None and "FROM customers" in sql

def test_template_aggregation_default():
    sql = compile_via_template("aggregation", {}, {"orders": []})
    assert "SUM(orders.total_amount)" in sql

def test_template_group_by_join():
    sql = compile_via_template("group_by", {}, {"employees": [], "orders": []})
    assert "JOIN employees" in sql
    assert "GROUP BY employees.employee_name" in sql

def test_template_top_n_limit():
    sql = compile_via_template("top_n", {"limit": 5, "order_dir": "DESC"}, {"products": []})
    assert "LIMIT 5" in sql
    assert "ORDER BY products.rating DESC" in sql

def test_template_no_match_falls_back_to_none():
    sql = compile_via_template("lookup", {}, {"customers": [], "payments": []})
    assert sql is None
    
from app.cache.cache_warmer import warm_cache, get_qdrant_client
from app.cache.semantic_cache import check_cache

_cache_client = get_qdrant_client(location=":memory:")
warm_cache(client=_cache_client)

def test_cache_hit_on_paraphrase():
    result = check_cache("show me every customer", client=_cache_client, threshold=0.80)
    assert result["hit"] is True
    assert result["matched_query"] == "show all customers"

def test_cache_miss_unrelated_query():
    result = check_cache("what is the weather today", client=_cache_client, threshold=0.90)
    assert result["hit"] is False

def test_cache_threshold_sensitivity():
    query = "top rated items"  # paraphrase of "highest rated products", not exact
    for threshold in (0.90, 0.92, 0.95):
        result = check_cache(query, client=_cache_client, threshold=threshold)
        print(f"threshold={threshold} -> hit={result['hit']} score={result['score']:.3f}")
        
from app.router.confidence_scorer import score_confidence
from app.router.langgraph_router import build_router

def test_confidence_scorer_high_signal():
    linked = {"customers": {"table": "customers", "column": None, "score": 100, "source": "synonym"}}
    score, signals = score_confidence(0.9, linked, {}, "lookup")
    assert score > 0.75  # matches HIGH_THRESHOLD; ir=None here so the ir signal is 0 by design

def test_confidence_scorer_low_signal():
    score, signals = score_confidence(0.3, {}, {}, "aggregation")
    assert score < 0.4

def test_router_rejects_unlinkable_query():
    router = build_router()
    result = router.invoke({"raw_query": "asdkjaslkdjaslkdj qwerty zxcvbn"})
    assert result["source"] == "rejected"
    assert result["sql"] is None

def test_router_compiles_known_query():
    router = build_router()
    result = router.invoke({"raw_query": "show all customers"})
    assert result["source"] == "compiled"
    assert "customers" in result["sql"]

def test_router_fallback_uses_injected_client():
    class FakeMessage:
        content = "SELECT * FROM customers;"
    class FakeChoice:
        message = FakeMessage()
    class FakeResponse:
        choices = [FakeChoice()]
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return FakeResponse()

    from app.router.langgraph_router import fallback_node
    state = {"raw_query": "some vague thing", "schema_links": {"customers": []},
             "intent": "lookup", "entities": {}}
    result = fallback_node(state, deps=None, llm_client=FakeClient())
    assert result["source"] == "llm_fallback"
    assert "customers" in result["sql"]
    
from app.validator.syntax_validator import validate_syntax
from app.validator.safety_guard import check_safety
from app.validator.whitelist import check_whitelist
from app.validator.dry_run import dry_run

def test_syntax_validator_valid():
    assert validate_syntax("SELECT * FROM customers;")["valid"] is True

def test_syntax_validator_catches_garbage():
    assert validate_syntax("SELEC * FORM customers")["valid"] is False

def test_safety_guard_allows_select():
    assert check_safety("SELECT * FROM customers;")["safe"] is True

def test_safety_guard_blocks_drop():
    assert check_safety("SELECT * FROM customers; DROP TABLE customers;")["safe"] is False

def test_safety_guard_blocks_delete():
    assert check_safety("DELETE FROM orders WHERE order_id = 1;")["safe"] is False

def test_safety_guard_blocks_update():
    assert check_safety("UPDATE customers SET email = 'x' WHERE customer_id = 1;")["safe"] is False

def test_safety_guard_blocks_stacked_statements():
    assert check_safety("SELECT * FROM customers; SELECT * FROM orders;")["safe"] is False

def test_safety_guard_blocks_injection_attempt():
    injected = "SELECT * FROM customers WHERE customer_id = 1; DROP TABLE customers; --"
    assert check_safety(injected)["safe"] is False

def test_whitelist_allows_real_schema():
    result = check_whitelist("SELECT customers.email FROM customers;")
    assert result["allowed"] is True

def test_whitelist_blocks_fake_table():
    result = check_whitelist("SELECT * FROM admin_users;")
    assert result["allowed"] is False
    assert "admin_users" in result["bad_tables"]

def test_whitelist_blocks_fake_column():
    result = check_whitelist("SELECT customers.password_hash FROM customers;")
    assert result["allowed"] is False
    assert "password_hash" in result["bad_columns"]

def test_dry_run_skips_without_engine():
    result = dry_run("SELECT * FROM customers;")
    assert result["ok"] is None
    assert "Phase 9" in result["note"]

def test_all_guards_reject_llm_hallucinated_table():
    # simulates the exact failure mode these guards exist for: LLM fallback
    # invents a table that sounds plausible but isn't in schema.json
    hallucinated_sql = "SELECT * FROM user_accounts;"
    assert validate_syntax(hallucinated_sql)["valid"] is True   # syntactically fine
    assert check_safety(hallucinated_sql)["safe"] is True        # it's a SELECT, "safe"
    assert check_whitelist(hallucinated_sql)["allowed"] is False # but whitelist catches it
    
import asyncio
from sqlalchemy import create_engine, text, select
from sqlalchemy.pool import StaticPool

from app.db.executor import execute_query
from app.db.result_formatter import format_result, to_json
from app.feedback.query_logger import ensure_log_table, log_query, query_logs
from app.feedback.miss_tracker import ensure_review_table, flag_for_review, get_pending_reviews, mark_reviewed
from app.feedback.dataset_grower import grow_dataset


@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool,
                            connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE customers (customer_id INTEGER, city TEXT)"))
        conn.execute(text("INSERT INTO customers VALUES (1, 'Mumbai'), (2, 'Delhi')"))
    return engine


def test_executor_runs_select(sqlite_engine):
    result = execute_query("SELECT * FROM customers", engine=sqlite_engine)
    assert result["success"] is True
    assert result["row_count"] == 2
    assert "city" in result["columns"]


def test_executor_handles_bad_sql(sqlite_engine):
    result = execute_query("SELECT * FROM nonexistent_table", engine=sqlite_engine)
    assert result["success"] is False
    assert result["error"] is not None


def test_executor_handles_empty_result(sqlite_engine):
    result = execute_query("SELECT * FROM customers WHERE city = 'Nowhere'", engine=sqlite_engine)
    assert result["success"] is True
    assert result["row_count"] == 0


def test_result_formatter_shape(sqlite_engine):
    execution = execute_query("SELECT * FROM customers", engine=sqlite_engine)
    formatted = format_result(execution, source="compiled", nl_query="show all customers")
    assert formatted["source"] == "compiled"
    assert formatted["row_count"] == 2
    import json as _json
    _json.loads(to_json(formatted))  # must serialize without error


def test_query_logger_inserts_row(sqlite_engine):
    ensure_log_table(sqlite_engine)
    asyncio.run(log_query(sqlite_engine, nl_query="show all customers", sql_query="SELECT * FROM customers;",
                           source="compiled", success=True, row_count=2, execution_time_ms=5.2, confidence=0.9))
    with sqlite_engine.connect() as conn:
        rows = conn.execute(select(query_logs)).fetchall()
    assert len(rows) == 1
    assert rows[0].nl_query == "show all customers"


def test_miss_tracker_flags_and_reviews(sqlite_engine):
    ensure_review_table(sqlite_engine)
    flag_for_review(sqlite_engine, nl_query="something vague", sql_query="SELECT * FROM customers;",
                     intent="lookup", confidence=0.4)
    pending = get_pending_reviews(sqlite_engine)
    assert len(pending) == 1
    mark_reviewed(sqlite_engine, review_id=pending[0]["id"], confirmed_correct=True)
    assert len(get_pending_reviews(sqlite_engine)) == 0


def test_dataset_grower_appends_confirmed_pairs(sqlite_engine, tmp_path):
    ensure_review_table(sqlite_engine)
    flag_for_review(sqlite_engine, nl_query="new phrasing for lookup", sql_query="SELECT * FROM customers;",
                     intent="lookup", confidence=0.5)
    pending = get_pending_reviews(sqlite_engine)
    mark_reviewed(sqlite_engine, review_id=pending[0]["id"], confirmed_correct=True)

    fake_csv = tmp_path / "intent_dataset.csv"
    fake_csv.write_text("nl_query,intent\n")

    assert grow_dataset(sqlite_engine, dataset_path=fake_csv) == 1
    assert "new phrasing for lookup" in fake_csv.read_text()
    assert grow_dataset(sqlite_engine, dataset_path=fake_csv) == 0  # no duplicate on re-run
    
from fastapi.testclient import TestClient
from app.main import app

def test_api_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

def test_api_query_endpoint():
    with TestClient(app) as client:
        response = client.post("/query", json={"query": "show all customers"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "customers" in data["sql"]

def test_api_metrics_endpoint():
    with TestClient(app) as client:
        client.post("/query", json={"query": "show all customers"})
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.json()["total_queries"] >= 1

def test_api_empty_query_rejected():
    with TestClient(app) as client:
        response = client.post("/query", json={"query": "   "})
        assert response.status_code == 400
        
from app.cache.semantic_cache import add_to_cache

def test_cache_learns_from_llm_fallback():
    engine = get_qdrant_client(location=":memory:")
    warm_cache(client=engine)

    query = "revenue split across product categories"
    assert check_cache(query, client=engine, threshold=0.90)["hit"] is False

    add_to_cache(query, "SELECT categories.category_name, SUM(order_items.quantity) FROM order_items ...", client=engine)

    result = check_cache(query, client=engine, threshold=0.90)
    assert result["hit"] is True
    assert result["matched_query"] == query