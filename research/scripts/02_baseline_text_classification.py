import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

# 1. Load dataset
df = pd.read_csv("../data/ci_cd_pipeline_failure_logs_dataset.csv")

# 2. Keep only the columns we need
df = df[["error_message", "failure_type"]].dropna()

# 3. Features and labels
X = df["error_message"]
y = df["failure_type"]

# 4. Split dataset
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

# 5. Build baseline model
model = Pipeline([
    ("tfidf", TfidfVectorizer(
        stop_words="english",
        max_features=5000
    )),
    ("clf", LogisticRegression(
        max_iter=1000
    ))
])

# 6. Train
model.fit(X_train, y_train)

# 7. Predict
y_pred = model.predict(X_test)

# 8. Evaluate
accuracy = accuracy_score(y_test, y_pred)

print("\n=== BASELINE MODEL RESULTS ===")
print("Accuracy:", round(accuracy, 4))

print("\n=== CLASSIFICATION REPORT ===")
print(classification_report(y_test, y_pred))

print("\n=== CONFUSION MATRIX ===")
print(confusion_matrix(y_test, y_pred))