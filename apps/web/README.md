# Web

Die öffentliche Ski Predictor Website.

Der aktuelle MVP verwendet HTML, CSS und JavaScript ohne Build Schritt. Dadurch lässt er sich schnell testen. Bei einer späteren Umstellung auf ein Frontend Framework bleibt dieser Ordner der Einstiegspunkt der Webanwendung.

Im normalen Betrieb lädt die Website Tipprunde, Auswertung und Saisonrangliste aus der gemeinsamen Backend API. Die Dateien unter `src/data` bleiben als Rückfall erhalten, damit die Website bei Bedarf weiterhin ohne Backend gestartet werden kann. Tippabgaben werden bis zur späteren Datenbankanbindung im `localStorage` des Browsers gespeichert.

Vor dem Speichern wird ein lokaler Ranglistenname eingegeben. Eine Anmeldung ist dafür nicht nötig. Nach dem Speichern kann die Abgabe über `Tipp exportieren` als JSON heruntergeladen werden. Diese Datei wird anschließend in den zur Tipprunde gehörenden Unterordner von `data/submissions/inbox` verschoben und vom lokalen Ergebnis Importer ausgewertet. Der Export bleibt auch nach dem Abgabeschluss verfügbar.

Eine lokale Tipprunde kann im offenen `testMode` laufen. Dadurch lässt sich ein Beispielrennen unabhängig vom offiziellen Datum ausfüllen, speichern und exportieren. Der Testmodus darf für eine echte Runde nicht gesetzt sein; dann gilt wieder der fachliche Abgabeschluss.

Nach dem Ergebnisimport kann optional `src/data/evaluation.local.json` erzeugt werden. Gehört sie zur geladenen Tipprunde, zeigt die Website automatisch die Wochenendpunkte und den Soll Ist Vergleich für jede Frage. Fehlt die Datei, wird der Auswertungsbereich ausgeblendet.

Bei mehreren Abgaben liefert die API die Wochenend- und Saisonwertung. Die Website zeigt die persönliche Auswertung nur dann, wenn deren Abgabe ID zum lokal gespeicherten Tipp passt.

## Lokal starten

Im Repository-Hauptordner:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Die Website ist danach unter `http://127.0.0.1:4175/tippspiel/` erreichbar.

Die Fragen werden außerhalb der Website in `data/questions/weekend-questions.md` gepflegt und beim Erzeugen der Tipprunde übernommen. Die Website dient ausschließlich zum Tippen.

Die Wochenendübersicht wird aus derselben generierten Tipprunde aufgebaut. Sie zeigt alle Bewerbe, die zugrunde liegenden Startlisten, Wertungsgruppen und die gekürzten Anzeigenamen aller Oberhachinger Starter. Jede Frage zeigt zusätzlich ihren Rennbezug.

Das Layout orientiert sich an der Farbwelt und Bildsprache des Skiteams Oberhaching. Das verwendete Logo und Rennbild stammen von der öffentlichen Vereinswebsite und liegen für den lokalen MVP unter `public/images`.

## Struktur

```text
web/
├── index.html
├── public/
│   └── images/
└── src/
    ├── scripts/
    │   └── app.js
    ├── data/
    │   └── tip-round.json
    └── styles/
        └── main.css
```
