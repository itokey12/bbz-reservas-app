# ---------------------------------------------------
# 1) Imagem base leve
# ---------------------------------------------------
FROM python:3.11-slim

# ---------------------------------------------------
# 2) Instala dependências do sistema (mínimas)
# ---------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------
# 3) Define diretório da aplicação
# ---------------------------------------------------
WORKDIR /app

# ---------------------------------------------------
# 4) Copia requirements
# ---------------------------------------------------
COPY requirements.txt .

# ---------------------------------------------------
# 5) Instala libs Python
# ---------------------------------------------------
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------
# 6) Copia o restante da aplicação
# ---------------------------------------------------
COPY . .

# ---------------------------------------------------
# 7) Variáveis de ambiente
# ---------------------------------------------------
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ---------------------------------------------------
# 8) Porta que o Render vai usar
# ---------------------------------------------------
EXPOSE 8080

# ---------------------------------------------------
# 9) Comando inicial — Render detecta automaticamente
# ---------------------------------------------------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
