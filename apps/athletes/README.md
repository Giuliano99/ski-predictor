# Athletenübersicht

Die interne Athletenübersicht wird gemeinsam mit der Backend-API gestartet:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Danach ist die Übersicht unter `http://127.0.0.1:4175/athleten/` erreichbar. Der getrennte Importbereich liegt unter `http://127.0.0.1:4175/athleten/import.html`. In einer Umgebung mit aktivierter Authentifizierung benötigen Benutzer die Rolle `GAME_MASTER`.

Die Seite zeigt ausschließlich Athleten des Skiteams Oberhaching aus den Altersjahrgängen der U14 und U16. Ergebnisse, veröffentlichte Rennanzahlen und Ranglistenstände werden saisonweise getrennt dargestellt.

Der Punkteverlauf verwendet veröffentlichte DSV-Listenstände. Mit einem einzelnen Listenstand wird ein Punkt, aber noch keine Veränderung angezeigt. Ab dem zweiten Stand derselben Saison wird die Differenz berechnet. Negative Werte bedeuten eine Verbesserung.

## Ergebnislisten einer Saison

Für einen vollständigen Saison-Test können alle Ergebnislisten gemeinsam abgelegt werden:

```text
<Datenordner>\saisons\2025-2026\ergebnislisten
```

Startlisten sind für diese Ablage nicht erforderlich. Der Dokumentkatalog ordnet die PDFs der Saison zu. Datum, Disziplin und Altersklasse werden beim Import soweit möglich aus der jeweiligen Ergebnisliste gelesen. Dateien, deren Format zusätzliche Informationen benötigt, werden nicht stillschweigend verworfen, sondern im Prüfbericht markiert.

Der Import kann über die Schaltfläche `Saison-Ergebnislisten aus Ordner auslesen` gestartet werden. Für einen reproduzierbaren Terminal-Lauf inklusive Freigabe aller warnungsfreien Listen gilt:

```powershell
python services/api/src/import_season_results.py 2025-2026 --approve-clean
```

Der Prüfbericht wird lokal unter `output/reports/season-results-2025-2026.md` erzeugt. Die Athletenübersicht zeigt anschließend pro Saison Starts, gewertete Läufe, Podestplätze, bestes Ergebnis sowie DNS, DNF und DSQ.
