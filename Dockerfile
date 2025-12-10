FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
# Install Google Chrome
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application code
COPY . .

# Install Python dependencies
# We use the existing script to ensure consistency
RUN python install_dependencies.py

# Expose port
EXPOSE 8000

# Start command
# We also run init_tables.py before starting to ensure DB is ready
CMD sh -c "python init_tables.py && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
