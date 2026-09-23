# Athletenübersicht

Die interne Athletenübersicht wird gemeinsam mit der Backend-API gestartet:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Danach ist die Übersicht unter `http://127.0.0.1:4175/athleten/` erreichbar. Der getrennte Importbereich liegt unter `http://127.0.0.1:4175/athleten/import.html`. In einer Umgebung mit aktivierter Authentifizierung benötigen Benutzer die Rolle `GAME_MASTER`.

Die Seite zeigt ausschließlich Athleten des Skiteams Oberhaching aus den Altersjahrgängen der U14 und U16. Ergebnisse, veröffentlichte Rennanzahlen und Ranglistenstände werden saisonweise getrennt dargestellt.

Der Punkteverlauf verwendet veröffentlichte DSV-Listenstände. Mit einem einzelnen Listenstand wird ein Punkt, aber noch keine Veränderung angezeigt. Ab dem zweiten Stand derselben Saison wird die Differenz berechnet. Negative Werte bedeuten eine Verbesserung.

## Ergebnislisten einer Saison

Ergebnislisten werden nach dem echten Rennwochenende abgelegt:

```text
<Datenordner>\saisons\2025-2026\weekends\YYYY-MM-DD\ergebnislisten
```

Wenn eine passende Startliste vorhanden ist, gehört sie nach:

```text
<Datenordner>\saisons\2025-2026\weekends\YYYY-MM-DD\startlisten
```

`YYYY-MM-DD` ist jeweils das Datum des ersten Renntags. Die gemeinsame Ablage verbessert die Zuordnung von Rennen und Athleten.
