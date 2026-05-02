import pandas as pd

# Load dataset
df = pd.read_csv("../data/ci_cd_pipeline_failure_logs_dataset.csv")

# Basic info
print("Shape:", df.shape)
print("\nColumns:\n", df.columns)

# Show first rows
print("\nFirst 5 rows:\n", df.head())

# Check class distribution
print("\nFailure Type Counts:\n", df["failure_type"].value_counts())

# Check missing values
print("\nMissing Values:\n", df.isnull().sum())

# Sample error messages
print("\nSample Error Messages:\n", df["error_message"].head(10))