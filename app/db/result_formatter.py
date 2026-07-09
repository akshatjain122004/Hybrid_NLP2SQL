import json


def format_result(execution_result: dict, source: str, nl_query: str = None) -> dict:
    return {
        "success": execution_result["success"],
        "nl_query": nl_query,
        "source": source,
        "columns": execution_result["columns"],
        "rows": execution_result["rows"],
        "row_count": execution_result["row_count"],
        "execution_time_ms": execution_result["execution_time_ms"],
        "error": execution_result["error"],
    }


def to_json(formatted_result: dict) -> str:
    return json.dumps(formatted_result, default=str)  # default=str handles Decimal/datetime from DB rows