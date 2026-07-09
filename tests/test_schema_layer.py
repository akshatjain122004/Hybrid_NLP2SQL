from app.pipeline.schema_linker import SchemaLinker

linker = SchemaLinker()

test_queries = [

    "show all customers",

    "top 10 products",

    "highest revenue",

    "supplier country",

    "average product price",

    "employee department",

    "customer city",

    "payment status",

    "orders last month",

    "quantity sold",

    "product rating",

    "vendor",

    "buyer",

    "staff",

    "goods",

    "inventory",

    "income",

    "telephone",

    "mail",

    "state"

]

for query in test_queries:

    print("=" * 70)

    print("QUERY :", query)

    tokens = []

    for word in query.split():

        tokens.append({

            "text": word,

            "lemma": word.lower()

        })

    result = linker.link_schema(tokens)

    for token, matches in result.items():

        print(f"\nTOKEN : {token}")

        for match in matches:

            print(match)