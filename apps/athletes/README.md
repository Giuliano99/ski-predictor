# Athletenübersicht

Die interne Athletenübersicht wird gemeinsam mit der Backend-API gestartet:

```powershell
.\scripts\game-master\Start-Dashboard.ps1
```

Danach ist sie unter `http://127.0.0.1:4175/athleten/` erreichbar. In einer Umgebung mit aktivierter Authentifizierung benötigen Benutzer die Rolle `GAME_MASTER`.

Die Seite zeigt ausschließlich Athleten des Skiteams Oberhaching aus den Altersjahrgängen der U14 und U16. Ergebnisse, veröffentlichte Rennanzahlen und Ranglistenstände werden saisonweise getrennt dargestellt.

Der Punkteverlauf verwendet veröffentlichte DSV-Listenstände. Mit einem einzelnen Listenstand wird ein Punkt, aber noch keine Veränderung angezeigt. Ab dem zweiten Stand derselben Saison wird die Differenz berechnet. Negative Werte bedeuten eine Verbesserung.
