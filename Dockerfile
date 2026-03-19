# Use a slim Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for psycopg2 and pandas
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Environment variables will be provided via .env or docker-compose
# For now, we'll keep the entrypoint flexible.
# The default command will be to run the agent in interactive mode if needed,
# but we'll likely use it for api.py soon.
CMD ["python", "agent.py"]
