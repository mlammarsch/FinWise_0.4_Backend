# FinWise 0.4 - Backend Planung

## 1. Übersicht der API-Endpunkte

*   `POST /users`
*   `GET /users`
*   `POST /tenants`
*   `GET /tenants`
*   `DELETE /tenants/{id}`

**Hinweis:** UUIDs werden clientseitig erzeugt und als String zurückgegeben.

## 2. Beschreibung der Datenbankarchitektur

### Zentrale User-Datenbank (`users.db`)
Die zentrale Datenbank wird in der Datei `users.db` im Hauptverzeichnis des Backends (`C:\00_mldata\programming\FinWise\FinWise_0.4_BE\users.db`) gespeichert.

*   **Tabelle `users`:**
    *   `uuid`: TEXT (Primärschlüssel, UUID als String)
    *   `name`: TEXT
    *   `email`: TEXT (eindeutig)
    *   `hashed_password`: TEXT (optional)
*   **Tabelle `tenants`:**
    *   `uuid`: TEXT (Primärschlüssel, UUID als String)
    *   `name`: TEXT
    *   `user_id`: TEXT (Fremdschlüssel zu `users.uuid`)

### Mandantendatenbanken
*   Für jeden Mandanten wird eine separate SQLite-Datei (`tenant_<TENANT_UUID>.db`) dynamisch im Verzeichnis `C:\00_mldata\programming\FinWise\FinWise_0.4_BE\tenant_databases\` erzeugt.
*   Kein automatischer Initialimport eines Schemas in Tenant-Datenbanken.

## 3. Konzept für Datenbanktrennung und dynamisches Routing

FastAPI wird Anfragen, die einen Mandantenkontext erfordern (z.B. über einen Pfadparameter oder einen Header, der die Tenant-ID enthält), so verarbeiten, dass die entsprechende mandantenspezifische Datenbankverbindung dynamisch hergestellt wird.

*   **Dynamische Erstellung:** Beim Anlegen eines neuen Mandanten wird die zugehörige `tenant_<TENANT_UUID>.db` im Verzeichnis `tenant_databases/` erstellt.
*   **Zugriff:** Für mandantenspezifische Operationen wird eine Abhängigkeit (Dependency) in FastAPI verwendet, die die Tenant-ID aus der Anfrage extrahiert und eine SQLAlchemy-Session zur korrekten `tenant_<TENANT_UUID>.db` bereitstellt.

## 4. Synchronisierungsstrategie (Frontend → API → SQLite)

*   **Asynchrone Übertragung:** Daten werden zwischen Frontend (IndexedDB) und Backend (FastAPI/SQLite) asynchron synchronisiert.
*   **Lokales Caching im Frontend:** Das Frontend hält Daten in IndexedDB vor, um Offline-Fähigkeit und schnelle Zugriffe zu ermöglichen.
*   **Expliziter Push/Pull:** Die Synchronisation wird durch explizite Aktionen des Benutzers oder periodische Hintergrundprozesse (Push/Pull-Mechanismen) angestoßen.
*   **Zeitstempelbasierter Vergleich:** Für jede zu synchronisierende Entität werden Zeitstempel (`created_at`, `updated_at`) sowohl im Frontend als auch im Backend verwaltet. Beim Synchronisieren werden diese Zeitstempel verglichen, um festzustellen, welche Datensätze neuer sind und übertragen/aktualisiert werden müssen. (Detailimplementierung später)
*   **Keine Konfliktauflösung (aktuelle Stufe):** In dieser Ausbaustufe ist keine automatische Konfliktauflösung vorgesehen. Bei Konflikten könnte die letzte Schreiboperation gewinnen oder ein Fehler gemeldet werden.

## 5. Testkonzept mit Coverage-Zielen

*   **Unit-Tests:** Alle API-Endpunkte, die Logik zur Datenbankerzeugung (zentral und mandantenspezifisch) sowie die Mechanismen zur Mandantentrennung werden durch Unit-Tests abgedeckt.
*   **SQLite In-Memory:** Für Testläufe wird primär SQLite In-Memory (`sqlite:///:memory:`) verwendet, um schnelle und isolierte Tests zu ermöglichen. Für Tests, die das Dateisystem betreffen (z.B. Erstellung von `tenant_*.db` Dateien), können temporäre Dateien genutzt werden.
*   **Test-Coverage:** Ein angestrebtes Code-Coverage-Ziel von mindestens 80% für die Backend-Logik.
