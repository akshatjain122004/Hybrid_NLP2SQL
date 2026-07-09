from pathlib import Path
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from sklearn.pipeline import Pipeline
import joblib

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = r"G:\projects_gen_ai\hybrid_nlp2sql\data\training\intent_dataset.csv"
MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)

df = pd.read_csv(DATA_PATH)
print(df["intent"].value_counts())

X, y = df["nl_query"], df["intent"]
label_encoder = LabelEncoder()
y_encoded = label_encoder.fit_transform(y)

pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
    ("clf", LogisticRegression(max_iter=1000, C=5.0)),
])

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(pipeline, X, y_encoded, cv=skf, scoring="accuracy")
print("5-fold CV accuracy scores:", scores)
print(f"Mean accuracy: {scores.mean():.4f}")

if scores.mean() < 0.85:
    raise SystemExit("Accuracy below 85% target -- expand intent_dataset.csv before proceeding.")

pipeline.fit(X, y_encoded)
joblib.dump(pipeline, MODELS_DIR / "intent_classifier.pkl")
joblib.dump(label_encoder, MODELS_DIR / "label_encoder.pkl")
print(f"Saved model + label encoder to {MODELS_DIR}")