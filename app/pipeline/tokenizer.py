import spacy


class QueryTokenizer:
    """
    Layer 1
    Tokenization + POS tagging
    """

    def __init__(self):

        self.nlp = spacy.load("en_core_web_sm")

    def tokenize(self, query: str):

        doc = self.nlp(query)

        tokens = []

        for token in doc:

            tokens.append(
                {
                    "text": token.text,
                    "lemma": token.lemma_,
                    "pos": token.pos_,
                    "tag": token.tag_,
                    "dependency": token.dep_,
                    "is_stop": token.is_stop,
                    "is_alpha": token.is_alpha,
                    "shape": token.shape_,
                }
            )

        return tokens

    def get_nouns(self, tokens):

        return [
            token["lemma"]
            for token in tokens
            if token["pos"] in ("NOUN", "PROPN")
        ]

    def get_verbs(self, tokens):

        return [
            token["lemma"]
            for token in tokens
            if token["pos"] == "VERB"
        ]

    def get_numbers(self, tokens):

        return [
            token["text"]
            for token in tokens
            if token["pos"] == "NUM"
        ]

    def get_adjectives(self, tokens):

        return [
            token["lemma"]
            for token in tokens
            if token["pos"] == "ADJ"
        ]


if __name__ == "__main__":

    tokenizer = QueryTokenizer()

    while True:

        query = input("Query : ")

        tokens = tokenizer.tokenize(query)

        print()

        for token in tokens:

            print(token)

        print()

        print("Nouns :", tokenizer.get_nouns(tokens))
        print("Verbs :", tokenizer.get_verbs(tokens))
        print("Numbers :", tokenizer.get_numbers(tokens))
        print("Adjectives :", tokenizer.get_adjectives(tokens))