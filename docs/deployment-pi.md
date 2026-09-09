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

Der Dienst aktualisiert vorerst nur den Quellcode. Das Neubauen und Neustarten
der Container wird mit dem produktiven Compose-Deployment ergaenzt.
