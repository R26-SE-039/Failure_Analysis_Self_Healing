"""
train_model.py
--------------
Trains the root cause classification model for NEXTGEN QA.

Models trained:
  - Random Forest
  - Gradient Boosting
  - Ensemble (Voting Classifier)

Features:
  - TF-IDF on error_message (500 features)
  - TF-IDF on stack_trace  (200 features)
  - Numeric: retry_count, test_duration_sec, cpu_usage_pct, memory_usage_mb
  - Encoded: failure_stage, severity, failure_type

Target: root_cause (6 classes)
Imbalance handling: class_weight='balanced' + SMOTE on minority classes

Output saved to:
  research/models/classifier.pkl
  research/models/vectorizer_msg.pkl
  research/models/vectorizer_trace.pkl
  research/models/label_encoder.pkl
  research/models/metrics.json
  (also copied to services/ml-service/models/)
"""

import os, sys, json, shutil
import numpy as np
import pandas as pd
import joblib
import warnings
warnings.filterwarnings("ignore")

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder, OrdinalEncoder
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    classification_report, accuracy_score,
    precision_score, recall_score, f1_score, confusion_matrix
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from scipy.sparse import hstack, csr_matrix
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from collections import Counter

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(BASE_DIR, "data")
MODELS_DIR  = os.path.join(BASE_DIR, "models")
SERVICES_ML = os.path.join(os.path.dirname(BASE_DIR), "services", "ml-service", "models")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(SERVICES_ML, exist_ok=True)

DATASET = os.path.join(DATA_DIR, "final_training_dataset.csv")

print("=" * 60)
print("  NEXTGEN QA — ML Root Cause Classifier Training")
print("=" * 60)

# ── 1. Load Data ───────────────────────────────────────────────────────────────
print("\n[1/7] Loading dataset...")
df = pd.read_csv(DATASET, low_memory=False)
print(f"  Loaded {len(df):,} records, {df.shape[1]} columns")

# Drop rows with missing target
df = df.dropna(subset=["root_cause"])
df["root_cause"] = df["root_cause"].str.strip().str.lower()

# Filter to valid classes only
VALID_CLASSES = [
    "locator_issue", "synchronization_issue", "test_data_issue",
    "environment_failure", "network_api_error", "application_defect"
]
df = df[df["root_cause"].isin(VALID_CLASSES)].reset_index(drop=True)
print(f"  After filtering: {len(df):,} records")

# ── DOWN-SAMPLING FOR PROTOTYPE SPEED ─────────────────────────────────────────
# Limit to max 2000 samples per class to speed up training drastically
print("\n  Down-sampling large classes for prototype speed...")
dfs = []
for label in VALID_CLASSES:
    subset = df[df["root_cause"] == label]
    if len(subset) > 2000:
        subset = subset.sample(n=2000, random_state=42)
    dfs.append(subset)
df = pd.concat(dfs).sample(frac=1, random_state=42).reset_index(drop=True)
print(f"  After down-sampling: {len(df):,} records")

print("\n  Root cause distribution:")
dist = df["root_cause"].value_counts()
for label, cnt in dist.items():
    pct = cnt / len(df) * 100
    print(f"    {label:<28} {cnt:>6} ({pct:.1f}%)")

# ── 2. Feature Engineering ─────────────────────────────────────────────────────
print("\n[2/7] Engineering features...")

# Fill nulls
df["error_message"]    = df["error_message"].fillna("").astype(str)
df["stack_trace"]      = df["stack_trace"].fillna("").astype(str)
df["failure_stage"]    = df["failure_stage"].fillna("unknown").astype(str)
df["severity"]         = df["severity"].fillna("MEDIUM").astype(str)
df["failure_type"]     = df["failure_type"].fillna("unknown").astype(str)
df["retry_count"]      = pd.to_numeric(df["retry_count"], errors="coerce").fillna(0)
df["test_duration_sec"]= pd.to_numeric(df["test_duration_sec"], errors="coerce").fillna(30)
df["cpu_usage_pct"]    = pd.to_numeric(df["cpu_usage_pct"], errors="coerce").fillna(50)
df["memory_usage_mb"]  = pd.to_numeric(df["memory_usage_mb"], errors="coerce").fillna(1024)
df["is_flaky_test"]    = df["is_flaky_test"].map(
    {True: 1, False: 0, "True": 1, "False": 0}
).fillna(0).astype(int)

# TF-IDF on error_message
print("  Fitting TF-IDF on error_message (500 features)...")
vec_msg = TfidfVectorizer(max_features=500, ngram_range=(1, 2), sublinear_tf=True)
X_msg = vec_msg.fit_transform(df["error_message"])

# TF-IDF on stack_trace
print("  Fitting TF-IDF on stack_trace (200 features)...")
vec_trace = TfidfVectorizer(max_features=200, ngram_range=(1, 2), sublinear_tf=True)
X_trace = vec_trace.fit_transform(df["stack_trace"])

# Ordinal encode categorical columns
cat_encoder = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
cat_cols = df[["failure_stage", "severity", "failure_type"]]
X_cat = cat_encoder.fit_transform(cat_cols)

# Numeric features
numeric_cols = ["retry_count", "test_duration_sec", "cpu_usage_pct", "memory_usage_mb", "is_flaky_test"]
X_num = df[numeric_cols].values

# Stack all features
X = hstack([X_msg, X_trace, csr_matrix(X_cat), csr_matrix(X_num)])
print(f"  Total feature matrix: {X.shape[0]:,} rows x {X.shape[1]:,} features")

# ── 3. Encode Labels ───────────────────────────────────────────────────────────
print("\n[3/7] Encoding labels...")
le = LabelEncoder()
y = le.fit_transform(df["root_cause"])
print(f"  Classes: {list(le.classes_)}")

# ── 4. Train / Test Split ──────────────────────────────────────────────────────
print("\n[4/7] Splitting train/test (80/20 stratified)...")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"  Train: {X_train.shape[0]:,}  |  Test: {X_test.shape[0]:,}")

# SMOTE on training set for minority classes
print("\n  Applying SMOTE to balance minority classes...")
train_dist = Counter(y_train)
print(f"  Before SMOTE: {dict(zip(le.classes_, [train_dist.get(i,0) for i in range(len(le.classes_))]))}")

# Only apply SMOTE if minority classes have < 500 samples
min_count = min(train_dist.values())
if min_count < 500:
    # k_neighbors must be < minority class count
    k = min(5, min_count - 1)
    if k >= 1:
        smote = SMOTE(random_state=42, k_neighbors=k)
        X_train, y_train = smote.fit_resample(X_train, y_train)
        after_dist = Counter(y_train)
        print(f"  After  SMOTE: {dict(zip(le.classes_, [after_dist.get(i,0) for i in range(len(le.classes_))]))}")
    else:
        print("  Skipping SMOTE (too few samples). Using class_weight='balanced' only.")
else:
    print("  Classes already balanced. Skipping SMOTE.")

# ── 5. Train Models ────────────────────────────────────────────────────────────
print("\n[5/7] Training models...")

# Random Forest
print("  Training Random Forest...")
rf = RandomForestClassifier(
    n_estimators=50, max_depth=10,
    class_weight="balanced", random_state=42, n_jobs=-1
)
rf.fit(X_train, y_train)
rf_acc = accuracy_score(y_test, rf.predict(X_test))
print(f"  Random Forest accuracy: {rf_acc:.4f}")

# Gradient Boosting
print("  Training Gradient Boosting...")
gb = GradientBoostingClassifier(
    n_estimators=50, max_depth=3,
    learning_rate=0.1, random_state=42
)
gb.fit(X_train, y_train)
gb_acc = accuracy_score(y_test, gb.predict(X_test))
print(f"  Gradient Boosting accuracy: {gb_acc:.4f}")

# Ensemble
print("  Training Voting Ensemble...")
ensemble = VotingClassifier(
    estimators=[("rf", rf), ("gb", gb)],
    voting="soft"
)
ensemble.fit(X_train, y_train)
ens_acc = accuracy_score(y_test, ensemble.predict(X_test))
print(f"  Ensemble accuracy: {ens_acc:.4f}")

# Pick best model
best_name, best_model, best_acc = max(
    [("RandomForest", rf, rf_acc),
     ("GradientBoosting", gb, gb_acc),
     ("Ensemble", ensemble, ens_acc)],
    key=lambda x: x[2]
)
print(f"\n  Best model: {best_name} (accuracy={best_acc:.4f})")

# ── 6. Evaluate ────────────────────────────────────────────────────────────────
print("\n[6/7] Evaluating best model on test set...")
y_pred = best_model.predict(X_test)
y_pred_proba = best_model.predict_proba(X_test)

print("\n  Classification Report:")
print(classification_report(y_test, y_pred, target_names=le.classes_))

# Per-class metrics dict
report = classification_report(y_test, y_pred, target_names=le.classes_, output_dict=True)

overall_metrics = {
    "model_name": best_name,
    "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
    "macro_precision": round(float(precision_score(y_test, y_pred, average="macro")), 4),
    "macro_recall":    round(float(recall_score(y_test, y_pred, average="macro")), 4),
    "macro_f1":        round(float(f1_score(y_test, y_pred, average="macro")), 4),
    "weighted_f1":     round(float(f1_score(y_test, y_pred, average="weighted")), 4),
    "train_samples":   int(X_train.shape[0]),
    "test_samples":    int(X_test.shape[0]),
    "classes": list(le.classes_),
    "per_class": {
        cls: {
            "precision": round(report[cls]["precision"], 4),
            "recall":    round(report[cls]["recall"], 4),
            "f1":        round(report[cls]["f1-score"], 4),
            "support":   int(report[cls]["support"]),
        }
        for cls in le.classes_
    },
    "all_models": {
        "RandomForest":     round(rf_acc, 4),
        "GradientBoosting": round(gb_acc, 4),
        "Ensemble":         round(ens_acc, 4),
    }
}

print(f"\n  Overall accuracy : {overall_metrics['accuracy']}")
print(f"  Macro F1         : {overall_metrics['macro_f1']}")
print(f"  Weighted F1      : {overall_metrics['weighted_f1']}")

# ── 7. Save Artifacts ──────────────────────────────────────────────────────────
print("\n[7/7] Saving model artifacts...")

artifacts = {
    "classifier.pkl":        best_model,
    "vectorizer_msg.pkl":    vec_msg,
    "vectorizer_trace.pkl":  vec_trace,
    "cat_encoder.pkl":       cat_encoder,
    "label_encoder.pkl":     le,
}

for fname, obj in artifacts.items():
    path = os.path.join(MODELS_DIR, fname)
    joblib.dump(obj, path, compress=3)
    print(f"  Saved {fname} ({os.path.getsize(path)//1024} KB)")

# Save metrics JSON
metrics_path = os.path.join(MODELS_DIR, "metrics.json")
with open(metrics_path, "w") as f:
    json.dump(overall_metrics, f, indent=2)
print(f"  Saved metrics.json")

# Copy to services/ml-service/models/
print(f"\n  Copying artifacts to services/ml-service/models/...")
for fname in artifacts.keys():
    src = os.path.join(MODELS_DIR, fname)
    dst = os.path.join(SERVICES_ML, fname)
    if os.path.exists(src):
        shutil.copy2(src, dst)
shutil.copy2(metrics_path, os.path.join(SERVICES_ML, "metrics.json"))
print(f"  Done.")

print("\n" + "=" * 60)
print(f"  Training complete!")
print(f"  Best model : {best_name}")
print(f"  Accuracy   : {overall_metrics['accuracy']}")
print(f"  Macro F1   : {overall_metrics['macro_f1']}")
print(f"  Artifacts  : {MODELS_DIR}")
print("=" * 60)
