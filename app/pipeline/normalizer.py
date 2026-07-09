import re
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
from spellchecker import SpellChecker


class QueryNormalizer:
    """
    Layer 1:
    Normalize raw user query before NLP processing.
    """

    def __init__(self):

        self.spell = SpellChecker()
        
        self.spell.word_frequency.load_words(
            ["sku", "orders", "order", "customers", "customer", "employees",
             "employee", "suppliers", "supplier", "payments", "payment"]
        )

        self.filler_patterns = [
            r"\bcan you\b",
            r"\bcould you\b",
            r"\bplease\b",
            r"\bi want to know\b",
            r"\bi want\b",
            r"\bshow me\b",
            r"\bgive me\b",
            r"\btell me\b",
            r"\bfind\b",
            r"\bdisplay\b",
            r"\blist\b",
            r"\bfetch\b",
        ]

    def normalize(self, query: str) -> str:

        query = query.lower().strip()

        query = self.remove_fillers(query)

        query = self.correct_spelling(query)

        query = self.normalize_dates(query)

        query = self.clean_spaces(query)

        return query

    def remove_fillers(self, text: str) -> str:

        for pattern in self.filler_patterns:
            text = re.sub(pattern, "", text)

        return text

    def correct_spelling(self, text: str) -> str:

        words = text.split()

        corrected = []

        for word in words:

            if word.isnumeric():
                corrected.append(word)
                continue

            corrected.append(self.spell.correction(word) or word)

        return " ".join(corrected)

    def normalize_dates(self, text: str) -> str:

        today = datetime.today()

        ranges = {
            "today": (today, today),
            "yesterday": (today - timedelta(days=1), today),
            "last week": (today - relativedelta(weeks=1), today),
            "last month": (today - relativedelta(months=1), today),
            "last year": (today - relativedelta(years=1), today),
        }

        for phrase, (start, end) in ranges.items():
            placeholder = f"date_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
            text = text.replace(phrase, placeholder)

        return text
    

    def clean_spaces(self, text: str) -> str:

        text = re.sub(r"\s+", " ", text)

        return text.strip()


if __name__ == "__main__":

    normalizer = QueryNormalizer()

    while True:

        q = input("Query : ")

        print(normalizer.normalize(q))