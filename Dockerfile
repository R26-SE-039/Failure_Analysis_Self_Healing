# C3 — Failure Analysis & Self-Healing (FastAPI, :8000)
#
# Build context is the REPO ROOT, not backend/, because the nine-class
# root-cause model is loaded from ../research/models relative to the app
# (root_cause_service.py resolves parents[3]/research/models). Both trees
# must land in the image with that same relative layout.
FROM python:3.11-slim

WORKDIR /app/backend

# scikit-learn / scipy / numpy / pandas / psycopg2-binary all ship manylinux
# wheels, so no compiler or libpq-dev is needed here.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code and the trained model, preserving the parents[3] layout:
#   /app/backend/app/...            <- code
#   /app/research/models/*.joblib   <- model the service loads at import
COPY backend/ /app/backend/
COPY research/models/ /app/research/models/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
