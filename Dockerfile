# Python slim
FROM python:3.11-slim

# variáveis para não pedir input
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instala Chromium + dependências
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    libnss3 \
    libasound2 \
    libx11-6 libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 \
    libxtst6 libxrandr2 libgbm1 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxfixes3 libxkbcommon0 libpango-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libatspi2.0-0 libgtk-3-0 curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Aponta o binário do Chromium para o app
ENV CHROME_BIN=/usr/bin/chromium
ENV GOOGLE_CHROME_BIN=/usr/bin/chromium

# Cria diretório e copia app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render usa $PORT; exponha e rode uvicorn
ENV PORT=8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
