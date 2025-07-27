import os
from dotenv import load_dotenv

# Basisverzeichnis des Backend-Projekts
# C:\00_mldata\programming\FinWise\FinWise_0.4_BE
BACKEND_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Lade Umgebungsvariablen aus der .env-Datei im Backend-Root-Verzeichnis
# Die .env Datei sollte sich im BACKEND_BASE_DIR befinden.
dotenv_path = os.path.join(BACKEND_BASE_DIR, ".env")
load_dotenv(dotenv_path)

# URL für die zentrale Benutzerdatenbank
# SQLALCHEMY_DATABASE_URL = "sqlite:///./users.db" # Relativ zum Startverzeichnis der App
# Sicherstellen, dass der Pfad absolut ist oder korrekt relativ zum Ausführungsort von FastAPI.
# Für Konsistenz verwenden wir einen Pfad relativ zum Backend-Basisverzeichnis.
CENTRAL_DB_NAME = os.getenv("CENTRAL_DB_NAME", "users.db")

# Erstelle DB-Verzeichnis falls es nicht existiert
# Für lokale Entwicklung: verwende HOST_DB_PATH falls gesetzt, sonst Standard-Pfad
DB_DIR = os.getenv("HOST_DB_PATH", os.path.join(BACKEND_BASE_DIR, "data", "db"))
os.makedirs(DB_DIR, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(DB_DIR, CENTRAL_DB_NAME)}"

# Weitere Konfigurationen können hier hinzugefügt werden
# Z.B. Secret Key, Algorithmus für JWTs etc.
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key") # ÄNDERN SIE DAS IN EINER PRODUKTIVUMGEBUNG!
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# WebSocket-Einstellungen
CLIENT_PING_INTERVAL_SECONDS = int(os.getenv("CLIENT_PING_INTERVAL_SECONDS", "30"))
SERVER_INACTIVITY_TIMEOUT_SECONDS = int(os.getenv("SERVER_INACTIVITY_TIMEOUT_SECONDS", "65"))

# Pfad für die Speicherung von Logos
# Für lokale Entwicklung: HOST_LOGO_PATH, für Docker: LOGO_STORAGE_PATH
LOGO_STORAGE_PATH = os.getenv("LOGO_STORAGE_PATH", os.getenv("HOST_LOGO_PATH", os.path.join(BACKEND_BASE_DIR, "data/logo_storage")))

# Verzeichnis für die mandantenspezifischen Datenbanken
# Für lokale Entwicklung: HOST_TENANT_DB_PATH, für Docker: TENANT_DATABASE_DIR
TENANT_DATABASE_DIR = os.getenv("TENANT_DATABASE_DIR", os.getenv("HOST_TENANT_DB_PATH", os.path.join(BACKEND_BASE_DIR, "tenant_databases")))

# Loglevel
LOGLEVEL = os.getenv("LOGLEVEL", "WARNING")

# Log-Pfad
# Für lokale Entwicklung: HOST_LOG_PATH, für Docker: LOG_PATH
LOG_PATH = os.getenv("LOG_PATH", os.getenv("HOST_LOG_PATH", os.path.join(BACKEND_BASE_DIR, "logs")))

# CORS Origins - kommagetrennte Liste von erlaubten Origins
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
# Entferne Leerzeichen um die Origins
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS]

if __name__ == "__main__":
    print(f"Backend Base Directory: {BACKEND_BASE_DIR}")
    print(f"Tenant Database Directory: {TENANT_DATABASE_DIR}")
    print(f"SQLAlchemy Database URL: {SQLALCHEMY_DATABASE_URL}")
    print(f"Logo Storage Path: {LOGO_STORAGE_PATH}")
    print(f"Log Path: {LOG_PATH}")
    print(f"CORS Origins: {CORS_ORIGINS}")
