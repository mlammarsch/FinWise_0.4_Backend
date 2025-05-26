import logging
import os
from logging.handlers import RotatingFileHandler
from ..config import BACKEND_BASE_DIR # Importiere BACKEND_BASE_DIR aus config.py

# --- Konfiguration ---
LOG_FILE_NAME = "backend.log"
LOG_FILE_PATH = os.path.join(BACKEND_BASE_DIR, LOG_FILE_NAME)
LOG_LEVEL_ENV_VAR = "LOG_LEVEL" # Umgebungsvariable für das Log-Level
DEFAULT_LOG_LEVEL = "INFO"

# Log-Format
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# --- Logger Setup ---
def setup_logger():
    log_level_str = os.environ.get(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL).upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger("finwise_backend")
    logger.setLevel(numeric_level) # Setze das Level basierend auf der Umgebungsvariable
    logger.propagate = False

    if not logger.handlers:
        # File Handler
        # Rotiert die Log-Datei, wenn sie 5MB erreicht, behält 5 Backup-Dateien.
        file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setLevel(numeric_level) # Auch Handler-Level setzen
        file_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console Handler (optional, für lokale Entwicklung nützlich)
        # Kann auch über eine Umgebungsvariable gesteuert werden, ob dieser aktiv ist.
        # Für den Moment fügen wir ihn hinzu, damit Logs auch in der Konsole erscheinen.
        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level) # Auch Handler-Level setzen
        console_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger

# Globalen Logger initialisieren
_logger_instance = setup_logger()

# --- Wrapper-Funktionen ---
def _log(level: int, module_name: str, message: str, details: object = None):
    """Interne Log-Funktion."""
    log_message = message
    if details is not None:
        try:
            # Versuche, Details als JSON zu formatieren, falls es ein Objekt ist
            import json
            details_str = json.dumps(details, indent=2, ensure_ascii=False, default=str) # default=str für nicht-serialisierbare Objekte
            log_message = f"{message} | Details: {details_str}"
        except TypeError:
            log_message = f"{message} | Details: {details}" # Fallback, falls JSON-Serialisierung fehlschlägt

    module_specific_logger = logging.getLogger(f"finwise_backend.{module_name}")
    module_specific_logger.log(level, log_message)


def debugLog(module_name: str, message: str, details: object = None):
    _log(logging.DEBUG, module_name, message, details)

def infoLog(module_name: str, message: str, details: object = None):
    _log(logging.INFO, module_name, message, details)

def warnLog(module_name: str, message: str, details: object = None):
    _log(logging.WARNING, module_name, message, details)

def errorLog(module_name: str, message: str, details: object = None):
    _log(logging.ERROR, module_name, message, details)

if __name__ == '__main__':
    # Testaufrufe
    # Um dies zu testen, muss die Umgebungsvariable LOG_LEVEL ggf. gesetzt werden
    # z.B. export LOG_LEVEL=DEBUG (Linux/Mac) oder set LOG_LEVEL=DEBUG (Windows)
    # oder direkt im Code für Testzwecke ändern:
    # os.environ[LOG_LEVEL_ENV_VAR] = "DEBUG"
    # _logger_instance = setup_logger() # Logger neu initialisieren, wenn Level geändert wird

    infoLog("TestModul", "Dies ist eine Info-Nachricht.", {"user_id": 123, "action": "login"})
    debugLog("TestModul", "Dies ist eine Debug-Nachricht.", [1, 2, 3])
    warnLog("TestModul", "Dies ist eine Warnung.")
    errorLog("TestModul", "Dies ist eine Fehlermeldung.", SyntaxError("Test Fehler"))

    # Test mit einem anderen Modulnamen
    infoLog("AnderesModul", "Nachricht von einem anderen Modul.")

    print(f"Log-Datei sollte unter {LOG_FILE_PATH} erstellt/aktualisiert worden sein.")
    print(f"Aktuelles Log-Level des Hauptloggers: {logging.getLevelName(_logger_instance.getEffectiveLevel())}")
    child_logger = logging.getLogger("finwise_backend.TestModul")
    print(f"Aktuelles Log-Level des Child-Loggers (TestModul): {logging.getLevelName(child_logger.getEffectiveLevel())}")
