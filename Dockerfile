FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
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
