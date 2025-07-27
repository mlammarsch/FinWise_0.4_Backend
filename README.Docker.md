# FinWise Backend - Docker Setup

Dieses Dokument beschreibt, wie das FinWise Backend mit Docker betrieben wird.

## Voraussetzungen

- Docker
- Docker Compose

## Schnellstart

1. **Umgebungsvariablen konfigurieren:**
   ```bash
   cp .env.example .env
   ```
   Bearbeiten Sie die `.env` Datei und passen Sie die Werte an Ihre Bedürfnisse an.

2. **Anwendung starten:**
   ```bash
   docker-compose up -d --build
   ```

3. **Anwendung testen:**
   Die API ist unter `http://localhost:8000` verfügbar.

## Umgebungsvariablen

### Sicherheit
- `SECRET_KEY`: Geheimer Schlüssel für die Anwendung (ÄNDERN SIE DIES IN PRODUKTION!)
- `ALGORITHM`: Algorithmus für JWT-Token (Standard: HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Token-Ablaufzeit in Minuten (Standard: 30)

### Datenbank
- `CENTRAL_DB_NAME`: Name der zentralen Benutzerdatenbank (Standard: users.db)

### WebSocket
- `CLIENT_PING_INTERVAL_SECONDS`: Ping-Intervall für WebSocket-Clients (Standard: 30)
- `SERVER_INACTIVITY_TIMEOUT_SECONDS`: Server-Inaktivitäts-Timeout (Standard: 65)

### Pfade (für lokale Entwicklung und Docker)
- `HOST_DB_PATH`: Pfad für die zentrale Datenbank (Standard: ./data/db)
- `HOST_TENANT_DB_PATH`: Pfad für Mandanten-Datenbanken (Standard: ./tenant_databases)
- `HOST_LOGO_PATH`: Pfad für Logo-Speicherung (Standard: ./data/logo_storage)
- `HOST_LOG_PATH`: Pfad für Log-Dateien (Standard: ./logs)

**Hinweis:** Diese Pfade werden sowohl für die lokale Entwicklung als auch für Docker-Volume-Mounts verwendet. In Docker werden sie automatisch auf die entsprechenden Container-Pfade gemappt.

### Logging
- `LOGLEVEL`: Log-Level (Standard: WARNING)

### CORS
- `CORS_ORIGINS`: Kommagetrennte Liste von erlaubten Frontend-URLs (Standard: http://localhost:5173)
  - Beispiele:
    - Lokale Entwicklung: `http://localhost:5173`
    - Andere Systeme: `http://192.168.1.100:5173,http://example.com:3000`
    - Produktionsumgebung: `https://finwise.example.com,https://app.finwise.com`

## Persistente Daten

Die folgenden Daten werden als Host-Mounts gespeichert (konfigurierbar über .env):
- Zentrale Benutzerdatenbank: `${HOST_DB_PATH}` (Standard: ./data/db)
- Mandantenspezifische Datenbanken: `${HOST_TENANT_DB_PATH}` (Standard: ./tenant_databases)
- Logo-Dateien: `${HOST_LOGO_PATH}` (Standard: ./data/logo_storage)
- Log-Dateien: `${HOST_LOG_PATH}` (Standard: ./logs)

**Wichtig:** Diese Verzeichnisse werden automatisch auf Ihrem Host-System erstellt, wenn sie nicht existieren.

## Nützliche Befehle

### Anwendung starten
```bash
docker-compose up -d
```

### Anwendung stoppen
```bash
docker-compose down
```

### Logs anzeigen
```bash
docker-compose logs -f finwise-backend
```

### Container neu erstellen
```bash
docker-compose up -d --build
```

### Volumes löschen (ACHTUNG: Alle Daten gehen verloren!)
```bash
docker-compose down -v
```

### In den Container einsteigen
```bash
docker-compose exec finwise-backend bash
```

## Entwicklung

Für die Entwicklung können Sie das Volume für den Code mounten:

```yaml
# In docker-compose.override.yml
version: '3.8'
services:
  finwise-backend:
    volumes:
      - .:/app
    command: ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

## Gesundheitsprüfung

Der Container verfügt über einen Gesundheitscheck, der alle 30 Sekunden ausgeführt wird. Sie können den Status überprüfen mit:

```bash
docker-compose ps
```

## CORS-Konfiguration für verschiedene Deployment-Szenarien

### Lokale Entwicklung
```bash
CORS_ORIGINS=http://localhost:5173
```

### Docker auf anderem Server (z.B. 192.168.1.100)
```bash
CORS_ORIGINS=http://192.168.1.100:5173
```

### Mehrere Frontend-URLs
```bash
CORS_ORIGINS=http://localhost:5173,http://192.168.1.100:5173,https://app.example.com
```

### Produktionsumgebung
```bash
CORS_ORIGINS=https://finwise.example.com,https://app.finwise.com
```

**Wichtig:** Verwenden Sie niemals `*` als CORS-Origin in der Produktion, da dies ein Sicherheitsrisiko darstellt.

## Fehlerbehebung

### Container startet nicht
1. Überprüfen Sie die Logs: `docker-compose logs finwise-backend`
2. Stellen Sie sicher, dass Port 8000 nicht bereits verwendet wird
3. Überprüfen Sie die Umgebungsvariablen in der `.env` Datei

### Datenbank-Probleme
1. Überprüfen Sie die Volume-Berechtigungen
2. Stellen Sie sicher, dass die Datenbank-Verzeichnisse existieren

### Performance-Probleme
1. Erhöhen Sie die Docker-Ressourcen (CPU/RAM)
2. Überprüfen Sie die Log-Level-Einstellungen

### Log-Dateien-Probleme
1. Überprüfen Sie, ob das LOG_PATH-Verzeichnis existiert und beschreibbar ist
2. Stellen Sie sicher, dass die Log-Volumes korrekt gemountet sind

## Anpassung der Host-Pfade

Sie können die Host-Pfade für die persistenten Daten in der `.env` Datei anpassen:

```bash
# Beispiel für benutzerdefinierte Pfade
HOST_DB_PATH=/my/custom/db/path
HOST_TENANT_DB_PATH=/my/custom/tenant/path
HOST_LOGO_PATH=/my/custom/logos/path
HOST_LOG_PATH=/my/custom/logs/path
```

**Wichtig:** Die angegebenen Verzeichnisse werden automatisch erstellt, wenn sie nicht existieren.

## Deployment auf Linux-Server

Um Ihr Docker-Image auf einem Linux-Server bereitzustellen, gibt es zwei Hauptansätze:

### 1. Image auf Docker Hub (oder einer anderen Container Registry) hochladen

Dies ist der empfohlene und gängigste Weg für die Bereitstellung.

**Schritte auf Ihrem lokalen Rechner (Windows):**

1.  **Image bauen:**
    Stellen Sie sicher, dass Sie sich im Hauptverzeichnis Ihres Projekts befinden, wo sich das `Dockerfile` und die `docker-compose.yml` befinden.
    ```bash
    docker build -t your_dockerhub_username/finwise-backend:latest .
    ```
    -   Ersetzen Sie `your_dockerhub_username` durch Ihren tatsächlichen Docker Hub Benutzernamen.
    -   `finwise-backend` ist der Name Ihres Images.
    -   `:latest` ist der Tag für das Image (Sie können auch Versionsnummern wie `:1.0.0` verwenden).
    -   `.` am Ende bedeutet, dass der Build-Kontext das aktuelle Verzeichnis ist.

2.  **Bei Docker Hub anmelden:**
    ```bash
    docker login
    ```
    Geben Sie Ihre Docker Hub Anmeldedaten ein, wenn Sie dazu aufgefordert werden.

3.  **Image hochladen (pushen):**
    ```bash
    docker push your_dockerhub_username/finwise-backend:latest
    ```
    Ihr Image ist nun auf Docker Hub verfügbar.

**Schritte auf Ihrem Linux-Server:**

1.  **Docker und Docker Compose installieren:**
    Stellen Sie sicher, dass Docker und Docker Compose auf Ihrem Linux-Server installiert sind. Anleitungen dazu finden Sie auf der offiziellen Docker-Website.

2.  **Projektdateien vorbereiten:**
    Erstellen Sie ein Verzeichnis für Ihr Projekt auf dem Server und kopieren Sie die `docker-compose.yml` und die `.env.example` (oder Ihre angepasste `.env`) in dieses Verzeichnis. Sie benötigen das `Dockerfile` nicht auf dem Server, da das Image bereits gebaut und hochgeladen wurde.

    **Beispiel `docker-compose.yml` Anpassung für Docker Hub Image:**
    Ändern Sie in Ihrer `docker-compose.yml` die `build: .` Zeile zu `image: your_dockerhub_username/finwise-backend:latest`.

    ```yaml
    version: '3.8'

    services:
      finwise-backend:
        image: your_dockerhub_username/finwise-backend:latest # <-- Hier geändert
        container_name: finwise-backend
        ports:
          - "8000:8000"
        # ... Rest der Konfiguration bleibt gleich ...
    ```

3.  **Umgebungsvariablen konfigurieren:**
    Erstellen Sie eine `.env` Datei auf dem Server (falls noch nicht geschehen) und passen Sie die Werte an die Serverumgebung an, insbesondere `CORS_ORIGINS`.

4.  **Image herunterladen (pullen) und starten:**
    Navigieren Sie im Terminal auf dem Server zu dem Verzeichnis, in dem sich Ihre `docker-compose.yml` und `.env` befinden, und führen Sie aus:
    ```bash
    docker-compose pull
    docker-compose up -d
    ```
    -   `docker-compose pull`: Lädt das neueste Image von Docker Hub herunter.
    -   `docker-compose up -d`: Startet den Container im Hintergrund.

### 2. Projektdateien direkt auf den Server kopieren und dort bauen

Dieser Ansatz ist nützlich, wenn Sie keine Container Registry verwenden möchten oder können.

**Schritte auf Ihrem Linux-Server:**

1.  **Docker und Docker Compose installieren:**
    Stellen Sie sicher, dass Docker und Docker Compose auf Ihrem Linux-Server installiert sind.

2.  **Projektdateien kopieren:**
    Kopieren Sie das gesamte Projektverzeichnis (inklusive `Dockerfile`, `docker-compose.yml`, `.env.example`, `app/` etc.) auf Ihren Linux-Server. Dies kann per `scp`, `rsync` oder Git geschehen.

3.  **Umgebungsvariablen konfigurieren:**
    Erstellen Sie eine `.env` Datei auf dem Server (falls noch nicht geschehen) und passen Sie die Werte an die Serverumgebung an.

4.  **Image bauen und starten:**
    Navigieren Sie im Terminal auf dem Server zu dem Verzeichnis, in dem sich Ihre `docker-compose.yml` und `Dockerfile` befinden, und führen Sie aus:
    ```bash
    docker-compose up -d --build
    ```
    -   `--build`: Baut das Image direkt auf dem Server.

Beide Methoden führen zum Ziel, aber das Hochladen auf Docker Hub ist flexibler für CI/CD-Pipelines und die Verteilung auf mehrere Server.
