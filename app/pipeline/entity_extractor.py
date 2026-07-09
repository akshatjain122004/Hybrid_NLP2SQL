import re
from datetime import datetime, timedelta

import spacy
from dateutil.relativedelta import relativedelta

nlp = spacy.load("en_core_web_sm")

SUPERLATIVE_DESC = {"top", "highest", "most", "best", "largest", "maximum", "max"}
SUPERLATIVE_ASC = {"bottom", "lowest", "least", "worst", "smallest", "minimum", "min"}

RELATIVE_DATE_PATTERNS = {
    "today": lambda now: (now.date(), now.date()),
    "yesterday": lambda now: ((now - timedelta(days=1)).date(),) * 2,
    "this week": lambda now: (now.date() - timedelta(days=now.weekday()), now.date()),
    "last week": lambda now: (
        now.date() - timedelta(days=now.weekday() + 7),
        now.date() - timedelta(days=now.weekday() + 1),
    ),
    "this month": lambda now: (now.date().replace(day=1), now.date()),
    "last month": lambda now: (
        now.date().replace(day=1) - relativedelta(months=1),
        now.date().replace(day=1) - timedelta(days=1),
    ),
    "this year": lambda now: (now.date().replace(month=1, day=1), now.date()),
    "last year": lambda now: (
        now.date().replace(month=1, day=1) - relativedelta(years=1),
        now.date().replace(month=1, day=1) - timedelta(days=1),
    ),
}


def extract_entities(text: str, now: datetime | None = None) -> dict:
    """
    Raw, intent-agnostic extraction. Output shape:
      numbers: list[int]        -- e.g. "top 5" -> [5]
      date_range: (str, str)|None
      date_phrase: str|None
      proper_nouns: list[str]   -- candidate WHERE filter values
      order_dir: "DESC"|"ASC"|None
    """
    now = now or datetime.now()
    doc = nlp(text)          # keep original case -- NER needs it
    lower = text.lower()

    entities = {
        "numbers": [int(n) for n in re.findall(r"\b\d+\b", text)],
        "date_range": None,
        "date_phrase": None,
        "proper_nouns": [],
        "order_dir": None,
    }

    lower_tokens = {t.text.lower() for t in doc}
    if lower_tokens & SUPERLATIVE_DESC:
        entities["order_dir"] = "DESC"
    elif lower_tokens & SUPERLATIVE_ASC:
        entities["order_dir"] = "ASC"

    for phrase in sorted(RELATIVE_DATE_PATTERNS, key=len, reverse=True):
        if phrase in lower:
            start, end = RELATIVE_DATE_PATTERNS[phrase](now)
            entities["date_range"] = (str(start), str(end))
            entities["date_phrase"] = phrase
            break

    for ent in doc.ents:
        if ent.label_ in {"GPE", "ORG", "PERSON", "NORP"}:
            entities["proper_nouns"].append(ent.text)
    if not entities["proper_nouns"]:
        entities["proper_nouns"] = [t.text for t in doc if t.pos_ == "PROPN"]

    return entities