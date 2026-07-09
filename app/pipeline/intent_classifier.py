import joblib
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "intent_classifier.pkl"
ENCODER_PATH = Path(__file__).resolve().parents[2] / "models" / "label_encoder.pkl"

_pipeline = None
_label_encoder = None


def _load():
    global _pipeline, _label_encoder
    if _pipeline is None:
        _pipeline = joblib.load(MODEL_PATH)
        _label_encoder = joblib.load(ENCODER_PATH)
    return _pipeline, _label_encoder


def classify_intent(text: str) -> dict:
    pipeline, label_encoder = _load()
    pred_encoded = pipeline.predict([text])[0]
    intent = label_encoder.inverse_transform([pred_encoded])[0]
    confidence = float(pipeline.predict_proba([text]).max())
    return {"intent": intent, "confidence": confidence}