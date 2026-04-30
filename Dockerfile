# EveryWifi – Docker image
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source and tests
COPY src/ ./src/
COPY tests/ ./tests/

# Default: run ledger tests
CMD ["python", "-m", "pytest", "tests/", "-v"]
