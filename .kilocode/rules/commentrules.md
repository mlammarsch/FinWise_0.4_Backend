# Kommentarregeln für KiloCode AI

## Ziel
Der Code soll selbsterklärend sein. Kommentare dienen der Orientierung bei komplexeren Methoden – nicht der Redundanz. Fokus liegt auf Klarheit und Relevanz.

## Regeln

1. **Selbsterklärende Methoden = keine Kommentare**
   - Wenn der Methodenname und die Struktur klar zeigen, was passiert, **keine Kommentare innerhalb der Methode** einfügen.
   - Beispiel: `calculateMonthlyBalance()` erklärt sich selbst – kein zusätzlicher Inline-Kommentar nötig.

2. **Nur Hauptmethode kommentieren**
   - Pro Datei oder Modul wird **nur die zentrale Methode** (sofern vorhanden) mit **einem prägnanten Einzeiler** beschrieben.
   - Kommentar beantwortet die Frage: *Was tut diese Methode – und warum ist sie zentral?*

3. **Kein Kommentar-Spam**
   - Keine Schritt-für-Schritt-Erklärung von Codezeilen.
   - Kommentare wie `// addiere Betrag`, `// überprüfe Konto-ID` o. Ä. sind **zu entfernen**.

4. **Bestehende Kommentare prüfen**
   - Wo bereits Kommentare vorhanden sind:
     - Prüfen, ob sie **wirklich Mehrwert bieten**.
     - Falls sie nur beschreiben, was ohnehin im Code steht: **löschen**.

5. **Ausnahmen**
   - Komplexe Logik oder Sonderfälle (z. B. edge case Handling) dürfen kurz erläutert werden – aber nur dann.
   - Max. 1 Kommentarblock pro Methode.

## Zielbild
Der Code liest sich wie ein gut strukturiertes Skript:
- Methodennamen = Klartext
- Kommentare = Kontext, nicht Nachlese
- Kein Textballast, keine Wiederholung, keine Deko

## Umsetzungspflicht
Dieser Kommentarstil ist verbindlich für alle Python-Dateien im Backend. Frontend (Vue/TS) folgt denselben Grundprinzipien, wo zutreffend.
