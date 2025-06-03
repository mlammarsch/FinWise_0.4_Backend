import os
from dotenv import load_dotenv

# Basisverzeichnis des Backend-Projekts
# C:\00_mldata\programming\FinWise\FinWise_0.4_BE
BACKEND_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Lade Umgebungsvariablen aus der .env-Datei im Backend-Root-Verzeichnis
# Die .env Datei sollte sich im BACKEND_BASE_DIR befinden.
dotenv_path = os.path.join(BACKEND_BASE_DIR, ".env")
load_dotenv(dotenv_path)

# Verzeichnis für die mandantenspezifischen Datenbanken
TENANT_DATABASE_DIR = os.path.join(BACKEND_BASE_DIR, "tenant_databases")

# URL für die zentrale Benutzerdatenbank
# SQLALCHEMY_DATABASE_URL = "sqlite:///./users.db" # Relativ zum Startverzeichnis der App
# Sicherstellen, dass der Pfad absolut ist oder korrekt relativ zum Ausführungsort von FastAPI.
# Für Konsistenz verwenden wir einen Pfad relativ zum Backend-Basisverzeichnis.
CENTRAL_DB_NAME = "users.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(BACKEND_BASE_DIR, CENTRAL_DB_NAME)}"

# Weitere Konfigurationen können hier hinzugefügt werden
# Z.B. Secret Key, Algorithmus für JWTs etc.
SECRET_KEY = "your-secret-key" # ÄNDERN SIE DAS IN EINER PRODUKTIVUMGEBUNG!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

if __name__ == "__main__":
    print(f"Backend Base Directory: {BACKEND_BASE_DIR}")
    print(f"Tenant Database Directory: {TENANT_DATABASE_DIR}")
    print(f"SQLAlchemy Database URL: {SQLALCHEMY_DATABASE_URL}")
