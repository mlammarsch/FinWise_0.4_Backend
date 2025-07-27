# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Setze Arbeitsverzeichnis
WORKDIR /app

# Installiere System-Dependencies
RUN apt-get update && apt-get install -y \
  gcc \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Kopiere requirements.txt und installiere Python-Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Erstelle einen non-root User für Sicherheit
RUN useradd --create-home --shell /bin/bash app

# Erstelle notwendige Verzeichnisse und setze Berechtigungen
RUN mkdir -p /app/data/logo_storage /app/data/db /app/tenant_databases /app/logs && \
  chown -R app:app /app

# Kopiere Anwendungscode
COPY . .

# Setze Berechtigungen für den app User
RUN chown -R app:app /app

# Wechsle zum non-root User
USER app

# Exponiere Port
EXPOSE 8000

# Gesundheitscheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Startkommando
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
