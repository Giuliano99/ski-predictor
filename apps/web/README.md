# Web

Die öffentliche Ski Predictor Website.

Der aktuelle MVP verwendet HTML, CSS und JavaScript ohne Build Schritt. Dadurch lässt er sich schnell testen. Bei einer späteren Umstellung auf ein Frontend Framework bleibt dieser Ordner der Einstiegspunkt der Webanwendung.

Die Tipprunde wird aus `src/data/tip-round.local.json` oder als Rückfall aus `src/data/tip-round.json` geladen. Tippabgaben werden ohne Datenbank im `localStorage` des Browsers gespeichert.

Nach dem Speichern kann die Abgabe über `Tipp exportieren` als JSON heruntergeladen werden. Diese Datei wird anschließend nach `data/submissions/inbox` verschoben und vom lokalen Ergebnis Importer ausgewertet. Der Export bleibt auch nach dem Abgabeschluss verfügbar.

Nach dem Ergebnisimport kann optional `src/data/evaluation.local.json` erzeugt werden. Gehört sie zur geladenen Tipprunde, zeigt die Website automatisch die Wochenendpunkte und den Soll Ist Vergleich für jede Frage. Fehlt die Datei, wird der Auswertungsbereich ausgeblendet.

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
