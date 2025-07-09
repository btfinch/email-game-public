# Dockerfile for The Email Game - Single Container
# Runs email server (with game logic) + dashboard together
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and data
COPY src/ src/
COPY docs/ docs/
COPY data/ data/
COPY templates/ templates/

# Create directories for game state and results
RUN mkdir -p session_results transcripts

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose port for unified email server (includes dashboard functionality)
EXPOSE 8000

# Health check for email server
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start email server (with integrated dashboard)
CMD ["python", "-m", "src.email_server", "--host", "0.0.0.0", "--port", "8000"]