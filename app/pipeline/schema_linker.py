import json
from pathlib import Path
from typing import Dict, List, Optional

from rapidfuzz import fuzz, process


class SchemaLinker:
    """
    Layer 2

    Schema Linker

    Responsibilities
    ----------------
    1. Load schema.json
    2. Load synonyms.json
    3. Resolve query tokens using

            Synonym Match
                    ↓
            Fuzzy Match

    4. Return candidate matches with confidence scores.

    NOTE

    SQL generation DOES NOT happen here.
    """

    MATCH_THRESHOLD = 85
    TOP_K = 3

    ##########################################################

    def __init__(
        self,
        schema_path: str = "schema/schema.json",
        synonyms_path: str = "schema/synonyms.json",
    ):

        self.schema = self._load_json(schema_path)

        self.synonyms = self._load_json(synonyms_path)

        self.tables = {}

        self.columns = {}

        self.table_names = []

        self.column_names = []

        self._prepare_schema()

    ##########################################################
    # JSON LOADER
    ##########################################################

    def _load_json(self, path: str):

        path = Path(path)

        if not path.exists():

            raise FileNotFoundError(f"{path} does not exist.")

        with open(path, "r", encoding="utf-8") as file:

            return json.load(file)

    ##########################################################
    # PREPARE LOOKUP STRUCTURES
    ##########################################################

    def _prepare_schema(self):
        """
        Creates

        table_names

        column_names

        table lookup

        column lookup
        """

        tables = self.schema["tables"]

        for table_name, table_info in tables.items():

            self.table_names.append(table_name)

            self.tables[table_name] = {
                "columns": list(table_info["columns"].keys()),
                "primary_key": table_info["primary_key"],
                "foreign_keys": table_info["foreign_keys"],
            }

            for column in table_info["columns"]:

                self.column_names.append(column)

                self.columns[column] = table_name

    ##########################################################
    # EXACT SYNONYM MATCH
    ##########################################################

    def synonym_match(self, token: str) -> Optional[Dict]:

        token = token.lower()

        ##################################################
        # TABLE SYNONYMS
        ##################################################

        table_map = self.synonyms.get("tables", {})

        if token in table_map:

            table = table_map[token]

            return {
                "token": token,
                "table": table,
                "column": None,
                "score": 100,
                "source": "synonym",
            }

        ##################################################
        # COLUMN SYNONYMS
        ##################################################

        column_map = self.synonyms.get("columns", {})

        if token in column_map:

            value = column_map[token]

            ##################################################

            if isinstance(value, list):

                matches = []

                for column in value:

                    matches.append(
                        {
                            "table": self.columns.get(column),
                            "column": column,
                            "score": 100,
                            "source": "synonym",
                        }
                    )

                return {"token": token, "matches": matches}

            ##################################################

            return {
                "token": token,
                "table": self.columns.get(value),
                "column": value,
                "score": 100,
                "source": "synonym",
            }

        return None

    ##########################################################
    # RAPIDFUZZ MATCH
    ##########################################################

    def fuzzy_match(self, token: str) -> List[Dict]:

        candidates = []

        ##################################################
        # TABLE MATCHING
        ##################################################

        table_results = process.extract(
            token,
            self.table_names,
            scorer=fuzz.WRatio,
            limit=self.TOP_K,
        )

        for name, score, _ in table_results:

            if score >= self.MATCH_THRESHOLD:

                candidates.append(
                    {
                        "table": name,
                        "column": None,
                        "score": round(score, 2),
                        "source": "fuzzy",
                    }
                )

        ##################################################
        # COLUMN MATCHING
        ##################################################

        column_results = process.extract(
            token,
            self.column_names,
            scorer=fuzz.WRatio,
            limit=self.TOP_K,
        )

        for column, score, _ in column_results:

            if score >= self.MATCH_THRESHOLD:

                candidates.append(
                    {
                        "table": self.columns[column],
                        "column": column,
                        "score": round(score, 2),
                        "source": "fuzzy",
                    }
                )

        ##################################################

        candidates.sort(key=lambda x: x["score"], reverse=True)

        return candidates[: self.TOP_K]

    ##########################################################

    # REMOVE DUPLICATES
    ##########################################################

    ##########################################################
    # LINK SINGLE TOKEN
    ##########################################################

    def link_token(self, token: str):

        synonym = self.synonym_match(token)

        if synonym is not None:
            return synonym

        fuzzy = self.fuzzy_match(token)

        if fuzzy:
            return fuzzy[0]

        return None

    ##########################################################
    # MAIN API
    ##########################################################

    def link_schema(self, tokens):

        linked = {}

        for token in tokens:

            word = token["lemma"].lower()

            # Ignore semantic date tokens

            if word.startswith("date_"):
                continue

            if word.isdigit():
                continue

            # if token["is_stop"]:
            #     continue

            match = self.link_token(word)

            if match:

                linked[word] = match

        return linked

    ##########################################################
    # PRETTY PRINTER
    ##########################################################


def print_links(result: Dict):

    print("\n==============================")

    print("SCHEMA LINKS")

    print("==============================")

    for token, matches in result.items():

        print(f"\nToken : {token}")

        for match in matches:

            print(
                f"  -> "
                f"Table={match['table']} | "
                f"Column={match['column']} | "
                f"Score={match['score']} | "
                f"Source={match['source']}"
            )


def to_schema_links(linked: Dict) -> Dict[str, List[str]]:
    """
    Normalizes SchemaLinker's mixed output shapes into {table: [col, col, ...]}
    -- the exact input build_ir() expects.
    """
    schema_links: Dict[str, List[str]] = {}
    for match in linked.values():
        candidates = match["matches"] if "matches" in match else [match]
        for cand in candidates:
            table = cand.get("table")
            if table is None:
                continue
            schema_links.setdefault(table, [])
            column = cand.get("column")
            if column and column not in schema_links[table]:
                schema_links[table].append(column)
    return schema_links

    ##########################################################
    # LOCAL TESTING
    ##########################################################


if __name__ == "__main__":

    linker = SchemaLinker()

    while True:

        query = input("\nQuery : ")

        if query.lower() == "exit":

            break

        tokens = []

        for word in query.split():

            tokens.append({"text": word, "lemma": word.lower()})

        result = linker.link_schema(tokens)

        print_links(result)
