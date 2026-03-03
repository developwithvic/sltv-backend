FROM python:3.10-slim

# Step 1: Install system dependencies & Chrome's required shared libraries
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libxshmfence1 \
    --no-install-recommends

# Step 2: Install Google Chrome Stable
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Step 3: Copy only requirements/scripts first (Better Docker caching)
COPY requirements.txt . 
COPY install_dependencies.py .

# Step 4: Install Python dependencies
# Note: Using a requirements.txt is standard, but keeping your script since you prefer it
RUN python install_dependencies.py

# Step 5: Copy the rest of the application
COPY . .

EXPOSE 8000

# Start command (Added --proxy-headers for Render/Uvicorn stability)
CMD sh -c "python init_tables.py && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"
