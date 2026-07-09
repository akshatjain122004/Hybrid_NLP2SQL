# scripts/generate_intent_dataset.py  (one-time utility, not part of the pipeline itself)
import csv, random, itertools
from pathlib import Path

random.seed(42)
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "training" / "intent_dataset.csv"

tables = ["customers", "products", "orders", "employees", "suppliers", "categories", "payments", "order_items"]
metrics = ["revenue", "total amount", "quantity sold", "payment amount", "order value"]
group_cols = ["category", "employee", "department", "city", "country", "status", "payment method", "supplier"]
countries = ["India", "USA", "UK", "Germany", "France", "Canada"]
statuses = ["pending", "shipped", "delivered", "cancelled"]
depts = ["Sales", "Support", "IT", "Marketing"]
payment_methods = ["credit card", "paypal", "cash", "debit card"]
sort_cols = ["price", "rating", "stock", "total_amount", "quantity"]
n_values = [3, 5, 10, 15, 20]

rows = []

lookup_templates = ["list all {t}", "show all {t}", "show me all {t}", "list every {t}",
    "give me all {t} records", "display all {t}", "get all {t}", "view all {t}",
    "show the {t} table", "fetch all {t}", "list {t}", "show {t}"]
for tmpl in lookup_templates:
    for t in tables:
        rows.append((tmpl.format(t=t), "lookup"))

filter_templates_country = ["{t} in {c}", "show {t} in {c}", "list {t} from {c}", "{t} located in {c}", "get {t} from {c}"]
filter_templates_status = ["orders with status {s}", "show orders where status is {s}", "orders that are {s}", "list {s} orders"]
filter_templates_dept = ["employees in {d} department", "show employees from {d}", "list {d} department employees"]
filter_templates_payment = ["payments made by {p}", "show payments via {p}", "list {p} payments"]
for tmpl in filter_templates_country:
    for t in ["customers", "suppliers"]:
        for c in countries:
            rows.append((tmpl.format(t=t, c=c), "filter"))
for tmpl in filter_templates_status:
    for s in statuses:
        rows.append((tmpl.format(s=s), "filter"))
for tmpl in filter_templates_dept:
    for d in depts:
        rows.append((tmpl.format(d=d), "filter"))
for tmpl in filter_templates_payment:
    for p in payment_methods:
        rows.append((tmpl.format(p=p), "filter"))
rows += [("out of stock products", "filter"), ("products with low stock", "filter"),
         ("products under 50 dollars", "filter"), ("customers who signed up recently", "filter")]

agg_templates = ["total {m}", "what is the total {m}", "sum of {m}", "average {m}",
    "what is the average {m}", "how many {t} are there", "count of {t}",
    "total number of {t}", "number of {t}"]
for tmpl in agg_templates:
    if "{m}" in tmpl:
        for m in metrics:
            rows.append((tmpl.format(m=m), "aggregation"))
    else:
        for t in tables:
            rows.append((tmpl.format(t=t), "aggregation"))
rows += [("total revenue this month", "aggregation"), ("total revenue last month", "aggregation"),
         ("average order value", "aggregation"), ("how much revenue did we make", "aggregation")]

top_n_templates = ["top {n} {t} by {s}", "highest {n} {t} by {s}", "best {n} {t}",
    "lowest {n} {t} by {s}", "show the top {n} {t}", "top {n} selling products",
    "top {n} customers by spending", "cheapest {n} products",
    "highest rated products", "lowest rated products"]
for tmpl in top_n_templates:
    if "{n}" in tmpl and "{s}" in tmpl:
        for n in n_values:
            for s in sort_cols:
                rows.append((tmpl.format(n=n, t="products", s=s), "top_n"))
    elif "{n}" in tmpl:
        for n in n_values:
            rows.append((tmpl.format(n=n, t="products"), "top_n"))
    else:
        rows.append((tmpl, "top_n"))

group_by_templates = ["sales by {g}", "revenue by {g}", "{t} count per {g}", "number of {t} per {g}",
    "total revenue grouped by {g}", "orders by {g}", "{t} per {g}",
    "how many orders per {g}", "revenue for each {g}"]
for tmpl in group_by_templates:
    for g in group_cols:
        t = random.choice(["orders", "products", "order_items"])
        rows.append((tmpl.format(g=g, t=t), "group_by"))
rows += [("orders per employee", "group_by"), ("products by supplier", "group_by"),
         ("payment status of orders", "group_by")]

comparison_templates = ["compare revenue between {a} and {b}", "compare {m} this year vs last year",
    "difference in revenue between {a} and {b}", "compare sales across categories",
    "compare {m} between {a} and {b}", "compare order counts between {a} and {b}",
    "how does revenue this month compare to last month", "compare product ratings across categories"]
country_pairs = list(itertools.combinations(countries, 2))
for tmpl in comparison_templates:
    if "{a}" in tmpl and "{b}" in tmpl and "{m}" in tmpl:
        for a, b in country_pairs[:6]:
            for m in metrics[:2]:
                rows.append((tmpl.format(a=a, b=b, m=m), "comparison"))
    elif "{a}" in tmpl and "{b}" in tmpl:
        for a, b in country_pairs[:8]:
            rows.append((tmpl.format(a=a, b=b), "comparison"))
    elif "{m}" in tmpl:
        for m in metrics:
            rows.append((tmpl.format(m=m), "comparison"))
    else:
        rows.append((tmpl, "comparison"))

rows = list(set(rows))
random.shuffle(rows)

MAX_PER_CLASS = 45
by_class = {}
for text, label in rows:
    by_class.setdefault(label, []).append(text)
final_rows = []
for label, texts in by_class.items():
    random.shuffle(texts)
    for t in texts[:MAX_PER_CLASS]:
        final_rows.append((t, label))
random.shuffle(final_rows)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["nl_query", "intent"])
    writer.writerows(final_rows)

print(f"Wrote {len(final_rows)} rows to {OUT_PATH}")