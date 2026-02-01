FROM python:3.11-slim

WORKDIR /app

# Ensure logs are not buffered and appear immediately
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_LOGGER_LEVEL=info

# System dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Make startup script executable
RUN chmod +x start.sh

EXPOSE 8501 8000

CMD ["./start.sh"]
