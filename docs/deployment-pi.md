# Deployment auf dem Raspberry Pi

Das Repository liegt auf dem Pi unter `/home/pi/ski-predictor`. Der Pi liest das
oeffentliche GitHub-Repository nur lesend ueber HTTPS.

## Automatische Code-Aktualisierung

Der Timer `ski-predictor-update.timer` prueft GitHub etwa einmal pro Minute. Ein
neuer Stand wird nur uebernommen, wenn `main` konfliktfrei per Fast-Forward
aktualisiert werden kann. Nicht eingecheckte Aenderungen am Pi stoppen das Update.

Status und Protokoll:

```bash
systemctl status ski-predictor-update.timer
journalctl -u ski-predictor-update.service --since today
```

Manueller Test:

```bash
sudo systemctl start ski-predictor-update.service
```

Wenn `/srv/ski-predictor/config/auto-deploy-enabled` vorhanden ist, baut der
Dienst nach einem neuen Commit die Container neu und startet sie kontrolliert.

## Laufzeitdaten

Quellcode und Laufzeitdaten sind getrennt:

```text
/home/pi/ski-predictor     Git-Klon
/srv/ski-predictor         Daten, Konfiguration und Backups
```

PostgreSQL ist nur im internen Docker-Netz erreichbar. Ausschliesslich Port 4175
der Anwendung wird im lokalen Netz veroeffentlicht. Die Ersteinrichtung erfolgt
auf dem Pi mit:

```bash
cd /home/pi/ski-predictor
sudo ./scripts/deploy/Install-Pi.sh
```
