import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

# Load dataset
df = pd.read_csv("../data/ci_cd_pipeline_failure_logs_dataset.csv")

# Select useful structured features
features = [
    "failure_stage",
    "error_code",
    "ci_tool",
    "language",
    "os",
    "cloud_provider",
    "severity",
    "retry_count",
    "cpu_usage_pct",
    "memory_usage_mb",
    "build_duration_sec",
    "test_duration_sec",
    "deploy_duration_sec"
]

df = df[features + ["failure_type"]].dropna()

# Encode categorical columns
label_encoders = {}

for col in df.columns:
    if df[col].dtype == "object":
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col])
        label_encoders[col] = le

# Features & target
X = df.drop("failure_type", axis=1)
y = df["failure_type"]

# Split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Model
model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

# Train
model.fit(X_train, y_train)

# Predict
y_pred = model.predict(X_test)

# Evaluate
accuracy = accuracy_score(y_test, y_pred)

print("\n=== RANDOM FOREST RESULTS ===")
print("Accuracy:", round(accuracy, 4))

print("\n=== CLASSIFICATION REPORT ===")
print(classification_report(y_test, y_pred))