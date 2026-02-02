FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY vigil.py .

# Create data directory
RUN mkdir -p /data/vigil

# Expose heartbeat port
EXPOSE 8765

# Run Vigil
CMD ["python", "-u", "vigil.py"]
