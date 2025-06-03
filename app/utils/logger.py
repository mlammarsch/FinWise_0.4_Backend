import logging
import os
import json
from logging.handlers import RotatingFileHandler
# Stelle sicher, dass config.py zuerst geladen wird, um dotenv zu initialisieren
from ..config import BACKEND_BASE_DIR # Importiert BACKEND_BASE_DIR

# --- Konfiguration ---
LOG_FILE_NAME = "backend.log"
LOG_FILE_PATH = os.path.join(BACKEND_BASE_DIR, LOG_FILE_NAME)
LOG_LEVEL_ENV_VAR = "LOGLEVEL"  # Umgebungsvariable für das Log-Level (angepasst an .env)
DEFAULT_LOG_LEVEL = "INFO"

# Log-Format
LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# --- Logger Setup ---
def setup_logger():
    # Lese Log-Level aus Umgebungsvariable oder verwende Default
    # .upper() um sicherzustellen, dass "info", "DEBUG" etc. korrekt erkannt werden
    log_level_str = os.environ.get(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL).upper()

    # Konvertiere String-Level zu numerischem Level von logging Modul
    # logging.INFO ist der Fallback, falls ein ungültiger String angegeben wurde
    numeric_level = getattr(logging, log_level_str, logging.INFO)

    # Erstelle einen spezifischen Logger für die Anwendung statt des Root-Loggers
    # Dies verhindert Konflikte mit Loggern von Drittanbieter-Bibliotheken
    logger = logging.getLogger("finwise_backend")
    logger.setLevel(numeric_level)

    # Verhindere, dass Log-Nachrichten an den Root-Logger weitergegeben werden,
    # da wir unsere eigenen Handler konfigurieren.
    logger.propagate = False

    # Füge Handler nur hinzu, wenn noch keine konfiguriert sind,
    # um Duplizierung bei mehrmaligem Aufruf (z.B. in Tests) zu vermeiden.
    if not logger.handlers:
        # File Handler
        # Rotiert die Log-Datei, wenn sie 5MB erreicht, behält 5 Backup-Dateien.
        # encoding='utf-8' ist wichtig für korrekte Darstellung von Sonderzeichen.
        try:
            file_handler = RotatingFileHandler(
                LOG_FILE_PATH, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
            )
            file_handler.setLevel(numeric_level) # Setze das Level auch für den Handler
            file_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # Fallback, falls das Erstellen des FileHandlers fehlschlägt (z.B. Berechtigungsprobleme)
            # Logge diesen Fehler auf der Konsole, da der File-Logger nicht funktioniert.
            print(f"FEHLER: Konnte FileHandler für Logger nicht erstellen: {e}", flush=True)


        # Console Handler (stdout/stderr)
        # Gibt Logs auf der Konsole aus.
        console_handler = logging.StreamHandler() # Standardmäßig sys.stderr, für Fehler sys.stdout
        console_handler.setLevel(numeric_level) # Setze das Level auch für den Handler
        console_formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger

# Globalen Logger initialisieren, sobald das Modul geladen wird.
# Dieser Logger wird dann von den Wrapper-Funktionen verwendet.
_logger_instance = setup_logger()

# --- Wrapper-Funktionen ---
# Behalten die ursprüngliche Signatur bei.
def _log(level: int, module_name: str, message: str, details: object = None):
    """
    Interne Log-Funktion, die Nachrichten an den konfigurierten Logger sendet.
    Das `details`-Objekt wird als JSON-String formatiert, falls vorhanden.
    """
    log_message = message
    if details is not None:
        try:
            # Versuche, Details als JSON zu formatieren.
            # default=str hilft bei der Serialisierung von nicht direkt JSON-serialisierbaren Objekten (z.B. datetime).
            # ensure_ascii=False erlaubt Unicode-Zeichen direkt im Output.
            details_str = json.dumps(details, indent=2, ensure_ascii=False, default=str)
            log_message = f"{message} | Details: {details_str}"
        except TypeError:
            # Fallback, falls die JSON-Serialisierung fehlschlägt.
            log_message = f"{message} | Details (nicht serialisierbar): {details}"

    # Verwende den bereits initialisierten und konfigurierten Logger.
    # Der Name des Loggers wird hier nicht mehr dynamisch pro Modul geändert,
    # stattdessen wird der Modulname als Teil der Nachricht geloggt oder
    # es könnte ein Child-Logger verwendet werden, wenn eine feinere Steuerung pro Modul nötig wäre.
    # Für die aktuelle Anforderung reicht es, den Modulnamen in der Nachricht zu haben.
    # Der Logger-Name ist "finwise_backend", der Modulname wird Teil der Nachricht.
    # Alternativ: logger = logging.getLogger(f"finwise_backend.{module_name}") und dann logger.log(...)
    # Aber da _logger_instance bereits "finwise_backend" ist und propagate=False hat,
    # ist es besser, diesen direkt zu verwenden und den Modulnamen in die Nachricht zu integrieren.
    # Die Format-String "%(name)s" wird den Namen des Loggers ("finwise_backend") anzeigen.
    # Um den Modulnamen separat zu haben, müsste man den Formatter anpassen oder Child-Logger verwenden.
    # Für diese Aufgabe wird der Modulname in die Nachricht integriert.

    # Korrekte Verwendung: Child-Logger erstellen, damit %(name)s den Modulnamen enthält
    module_specific_logger = logging.getLogger(f"finwise_backend.{module_name}")
    # Das Level des Child-Loggers wird vom Parent geerbt, wenn nicht explizit gesetzt.
    # Da der Parent (finwise_backend) bereits das korrekte Level hat, ist das hier in Ordnung.
    module_specific_logger.log(level, log_message)


def debugLog(module_name: str, message: str, details: object = None):
    """Loggt eine Debug-Nachricht."""
    _log(logging.DEBUG, module_name, message, details)

def infoLog(module_name: str, message: str, details: object = None):
    """Loggt eine Info-Nachricht."""
    _log(logging.INFO, module_name, message, details)

def warnLog(module_name: str, message: str, details: object = None):
    """Loggt eine Warnungs-Nachricht."""
    _log(logging.WARNING, module_name, message, details)

def errorLog(module_name: str, message: str, details: object = None):
    """Loggt eine Fehler-Nachricht."""
    _log(logging.ERROR, module_name, message, details)

# --- Testaufrufe (optional, für direkte Ausführung des Skripts) ---
if __name__ == '__main__':
    # Setze eine Umgebungsvariable für den Test, falls nicht vorhanden
    # os.environ[LOG_LEVEL_ENV_VAR] = "DEBUG"
    # _logger_instance = setup_logger() # Logger neu initialisieren, wenn Level programmatisch geändert wird

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
    debugLog("NochEinModul", "Sehr detaillierte Debug-Info.", {"data_points": [1,2,3,4,5], "threshold": 0.5})

    # Test, ob Child-Logger das Level korrekt erben
    child_logger_test = logging.getLogger("finwise_backend.TestModul.Init")
    print(f"Effektives Log-Level des Child-Loggers ({child_logger_test.name}): {logging.getLevelName(child_logger_test.getEffectiveLevel())}")

    print(f"--- Logger Test Ende ---")
    print(f"Überprüfe die Konsolenausgabe und die Datei: {LOG_FILE_PATH}")
