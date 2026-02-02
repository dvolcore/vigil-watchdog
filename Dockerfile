FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY vigil_v5.py vigil.py
COPY vigil.py vigil_v4.py

# Create data directory
RUN mkdir -p /data/vigil

# Expose heartbeat port
EXPOSE 8765

# Run Vigil v5.0
CMD ["python", "-u", "vigil.py"]
