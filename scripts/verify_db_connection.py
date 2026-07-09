import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.executor import get_engine, execute_query
from app.db.result_formatter import format_result
from app.feedback.query_logger import ensure_log_table
from app.feedback.miss_tracker import ensure_review_table

engine = get_engine()  # reads DATABASE_URL from environment

print("Creating query_logs and review_queue tables if they don't exist...")
ensure_log_table(engine)
ensure_review_table(engine)

print("\nRunning a real query against your actual data:")
result = execute_query("SELECT * FROM customers LIMIT 5;", engine=engine)
formatted = format_result(result, source="compiled", nl_query="show first 5 customers")

print(f"success={formatted['success']}")
print(f"row_count={formatted['row_count']}")
print(f"execution_time_ms={formatted['execution_time_ms']}")
print(f"columns={formatted['columns']}")
for row in formatted["rows"]:
    print(row)