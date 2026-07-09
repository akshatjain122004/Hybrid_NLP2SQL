DEFAULT_WEIGHTS = {"intent": 0.35, "schema": 0.30, "entities": 0.20, "ir": 0.15}

REQUIRED_ENTITY_KEYS = {
    "aggregation": ["aggregation_column"],
    "top_n": ["limit"],
    "group_by": ["group_by", "aggregation_column"],
    "comparison": ["group_by", "aggregation_column"],
    "filter": ["where"],
    "lookup": [],
}


def schema_link_score(linked: dict) -> float:
    """linked = SchemaLinker.link_schema() output. Averages match scores, normalized to 0-1."""
    scores = [m["score"] for m in linked.values() if isinstance(m, dict) and "score" in m]
    if not scores:
        return 0.0
    return (sum(scores) / len(scores)) / 100.0


def entity_completeness(intent: str, entities: dict) -> float:
    required = REQUIRED_ENTITY_KEYS.get(intent, [])
    if not required:
        return 1.0
    filled = sum(1 for key in required if entities.get(key))
    return filled / len(required)


def ir_completeness(ir) -> float:
    if ir is None:
        return 0.0
    return 1.0 if (ir.from_ and ir.select) else 0.0


def score_confidence(intent_confidence: float, linked: dict, entities: dict,
                      intent: str, ir=None, weights: dict = None):
    """Returns (score: float 0-1, signals: dict) -- signals returned for debugging/tuning."""
    weights = weights or DEFAULT_WEIGHTS
    signals = {
        "intent": intent_confidence,
        "schema": schema_link_score(linked),
        "entities": entity_completeness(intent, entities),
        "ir": ir_completeness(ir),
    }
    score = sum(signals[k] * weights[k] for k in weights)
    return round(score, 4), signals