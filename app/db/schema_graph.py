import json
from pathlib import Path
import networkx as nx

# app/db/schema_graph.py -> parents[2] = project root
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "schema.json"


def build_schema_graph(schema_path: Path = SCHEMA_PATH) -> nx.Graph:
    with open(schema_path) as f:
        schema = json.load(f)

    G = nx.Graph()
    for table in schema["tables"]:
        G.add_node(table)

    for table, meta in schema["tables"].items():
        for fk_col, fk in meta.get("foreign_keys", {}).items():
            ref_table = fk["referenced_table"]
            ref_col = fk["referenced_column"]
            G.add_edge(table, ref_table, cols={table: fk_col, ref_table: ref_col})
    return G


def resolve_joins(graph: nx.Graph, tables_needed: list[str], anchor: str | None = None):
    """
    tables_needed: every table required by the query (from schema links)
    Returns: (from_table, [{"table": ..., "on": ...}, ...])
    """
    anchor = anchor or tables_needed[0]
    joined = {anchor}
    joins = []

    for target in tables_needed:
        if target in joined:
            continue
        best_path = None
        for src in joined:
            try:
                path = nx.shortest_path(graph, src, target)
            except nx.NetworkXNoPath:
                continue
            if best_path is None or len(path) < len(best_path):
                best_path = path
        if best_path is None:
            raise ValueError(f"No FK path to '{target}' — check schema/schema.json edges")

        for a, b in zip(best_path, best_path[1:]):
            if b in joined:
                continue
            cols = graph.edges[a, b]["cols"]
            joins.append({"table": b, "on": f"{a}.{cols[a]} = {b}.{cols[b]}"})
            joined.add(b)
    return anchor, joins