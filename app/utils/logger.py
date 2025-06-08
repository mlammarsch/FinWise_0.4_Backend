import logging
import os
import json
import enum  # Hinzugefügt für Enum-Behandlung
from logging.handlers import RotatingFileHandler
# Stelle sicher, dass config.py zuerst geladen wird, um dotenv zu initialisieren
from ..config import BACKEND_BASE_DIR  # Importiert BACKEND_BASE_DIR

# --- Konfiguration ---
LOG_FILE_NAME = "backend.log"
LOG_FILE_PATH = os.path.join(BACKEND_BASE_DIR, LOG_FILE_NAME)
LOG_LEVEL_ENV_VAR = "LOGLEVEL"  # Umgebungsvariable für das Log-Level (angepasst an .env)
DEFAULT_LOG_LEVEL = "INFO"

# Log-Format
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger():
    """Konfiguriert den Logger für die gesamte Anwendung."""
    log_level_str = os.environ.get(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL).upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger("finwise_backend")
    logger.setLevel(numeric_level)
    logger.propagate = False

    if not logger.handlers:
        try:
            file_handler = RotatingFileHandler(
                LOG_FILE_PATH, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
            )
            file_handler.setLevel(numeric_level)
            file_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"FEHLER: Konnte FileHandler für Logger nicht erstellen: {e}", flush=True)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level)
        console_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


_logger_instance = setup_logger()


def enum_aware_default(obj):
    if isinstance(obj, enum.Enum):
        return obj.value
    try:
        return str(obj)
    except Exception:
        return f"<unserializable_object_type_{type(obj).__name__}>"


def _log(level: int, module_name: str, message: str, details: object = None):
    """Interne Log-Funktion, die Nachrichten formatiert und an den Logger sendet."""
    log_message = message
    if details is not None:
        try:
            details_str = json.dumps(details, indent=2, ensure_ascii=False, default=enum_aware_default)
            log_message = f"{message} | Details: {details_str}"
        except TypeError as e:
            _logger_instance.error(f"Failed to serialize log details for module {module_name}: {e}. Original details: {details}")
            log_message = f"{message} | Details (nicht serialisierbar, siehe vorherigen Log-Fehler)"
        except Exception as e_json:
            _logger_instance.error(f"Unexpected error serializing log details for module {module_name}: {e_json}. Original details: {details}")
            log_message = f"{message} | Details (Serialisierungsfehler, siehe vorherigen Log-Fehler)"

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
    print(f"--- Starte Logger Test ---")
    print(f"Log-Level aus Umgebung ({LOG_LEVEL_ENV_VAR}): {os.environ.get(LOG_LEVEL_ENV_VAR)}")
    print(f"Effektives Log-Level des Hauptloggers ({_logger_instance.name}): {logging.getLevelName(_logger_instance.getEffectiveLevel())}")
    print(f"Log-Datei: {LOG_FILE_PATH}")

    debugLog("TestModul.Init", "Initialisierung des Testmoduls.", {"version": "1.0", "mode": "test"})
    infoLog("TestModul.Core", "Kernfunktionalität ausgeführt.", {"user_id": "test_user", "items_processed": 150})
    warnLog("TestModul.Input", "Unerwartetes Eingabeformat erhalten.", {"input_value": "123,456", "expected_format": "integer"})

    try:
        x = 1 / 0
    except ZeroDivisionError as e:
        errorLog("TestModul.Calc", "Fehler bei der Berechnung.", {"error_type": str(type(e)), "details": str(e)})

    infoLog("AnderesModul", "Nachricht von einem anderen Modul ohne Details.")
    debugLog("NochEinModul", "Sehr detaillierte Debug-Info.", {"data_points": [1, 2, 3, 4, 5], "threshold": 0.5})

    child_logger_test = logging.getLogger("finwise_backend.TestModul.Init")
    print(f"Effektives Log-Level des Child-Loggers ({child_logger_test.name}): {logging.getLevelName(child_logger_test.getEffectiveLevel())}")

    print(f"--- Logger Test Ende ---")
    print(f"Überprüfe die Konsolenausgabe und die Datei: {LOG_FILE_PATH}")
