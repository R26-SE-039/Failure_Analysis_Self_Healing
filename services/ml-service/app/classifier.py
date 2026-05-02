"""
classifier.py  — ML Service
Loads the trained model artifacts and exposes prediction logic.
"""
import os, json
import numpy as np
import joblib
from scipy.sparse import hstack, csr_matrix
from typing import Optional


MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")

# Lazy-load globals
_classifier    = None
_vec_msg       = None
_vec_trace     = None
_cat_encoder   = None
_label_encoder = None
_metrics       = None
_ready         = False
_error         = None


def load_models():
    global _classifier, _vec_msg, _vec_trace, _cat_encoder, _label_encoder, _metrics, _ready, _error
    try:
        _classifier    = joblib.load(os.path.join(MODELS_DIR, "classifier.pkl"))
        _vec_msg       = joblib.load(os.path.join(MODELS_DIR, "vectorizer_msg.pkl"))
        _vec_trace     = joblib.load(os.path.join(MODELS_DIR, "vectorizer_trace.pkl"))
        _cat_encoder   = joblib.load(os.path.join(MODELS_DIR, "cat_encoder.pkl"))
        _label_encoder = joblib.load(os.path.join(MODELS_DIR, "label_encoder.pkl"))
        metrics_path   = os.path.join(MODELS_DIR, "metrics.json")
        if os.path.exists(metrics_path):
            with open(metrics_path) as f:
                _metrics = json.load(f)
        _ready = True
        print("[ML Service] Models loaded successfully.")
    except Exception as e:
        _error = str(e)
        _ready = False
        print(f"[ML Service] WARNING: Models not loaded — {e}")


def is_ready() -> bool:
    return _ready


def get_metrics() -> Optional[dict]:
    return _metrics


def predict(
    error_message: str,
    stack_trace: str = "",
    failure_stage: str = "test",
    failure_type: str = "Test Failure",
    severity: str = "MEDIUM",
    retry_count: float = 0,
    test_duration_sec: float = 30,
    cpu_usage_pct: float = 50,
    memory_usage_mb: float = 1024,
    is_flaky_test: int = 0,
) -> dict:
    if not _ready:
        raise RuntimeError("Models not loaded. Please train the model first.")

    # TF-IDF features
    X_msg   = _vec_msg.transform([error_message])
    X_trace = _vec_trace.transform([stack_trace or ""])

    # Categorical encoding
    cat_input = [[failure_stage, severity, failure_type]]
    X_cat = _cat_encoder.transform(cat_input)

    # Numeric features
    X_num = np.array([[retry_count, test_duration_sec, cpu_usage_pct, memory_usage_mb, is_flaky_test]])

    # Combine
    X = hstack([X_msg, X_trace, csr_matrix(X_cat), csr_matrix(X_num)])

    # Predict
    pred_idx   = _classifier.predict(X)[0]
    pred_proba = _classifier.predict_proba(X)[0]
    root_cause = _label_encoder.inverse_transform([pred_idx])[0]
    confidence = float(round(pred_proba[pred_idx], 4))

    all_probs = {
        cls: float(round(prob, 4))
        for cls, prob in zip(_label_encoder.classes_, pred_proba)
    }

    model_name = _metrics["model_name"] if _metrics else "Unknown"

    return {
        "root_cause":        root_cause,
        "confidence":        confidence,
        "all_probabilities": all_probs,
        "model_used":        model_name,
    }
