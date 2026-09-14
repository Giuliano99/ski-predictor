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

## Backup und Wiederherstellungspruefung

Der Timer `ski-predictor-backup.timer` erstellt jeden Tag gegen 03:15 Uhr ein
Backup unter `/srv/ski-predictor/backups`. Gesichert werden PostgreSQL, der
Anwendungszustand und die Original-PDFs. Erfolgreiche Sicherungen bleiben
standardmaessig 14 Tage erhalten.

Backup sofort erstellen:

```bash
sudo systemctl start ski-predictor-backup.service
journalctl -u ski-predictor-backup.service --since today
```

Das aktuelle Backup wird in einer getrennten Testdatenbank wiederhergestellt und
mit den produktiven Datenmengen verglichen:

```bash
cd /home/pi/ski-predictor
./scripts/deploy/Verify-PiBackup.sh
```

Die produktive Datenbank wird bei dieser Pruefung nicht veraendert.

## Authentifizierung fuer den geschlossenen Test

Nach dem Deployment wird die Anmeldung einmalig interaktiv aktiviert. Das
Passwort wird verdeckt im Terminal abgefragt und nicht in der Shell-Historie
oder in Git gespeichert:

```bash
cd /home/pi/ski-predictor
sudo bash scripts/deploy/Enable-Auth-Pi.sh
```

Das Skript erstellt den Spielleiter, erzeugt einen zufaelligen Einladungscode
fuer die Testgruppe und startet nur den App-Container neu. Teilnehmer
registrieren sich anschliessend unter `/login/`. Der Spielleiterbereich ist nur
fuer die Rolle `GAME_MASTER` erreichbar.

Solange der Pi nur per HTTP im lokalen Netz laeuft, bleibt
`SKI_SECURE_COOKIES=0`. Vor einer Freigabe im Internet muessen HTTPS und
`SKI_SECURE_COOKIES=1` aktiviert werden.

## Oeffentlicher HTTPS-Test ohne Routerfreigabe

Der temporaere Testzugang nutzt einen Cloudflare Quick Tunnel. Er ist fuer
Entwicklung und begrenzte Tests gedacht und benoetigt weder eine eigene Domain
noch eine Portfreigabe am Router:

```bash
cd /home/pi/ski-predictor
sudo bash scripts/deploy/Enable-Https-Test-Pi.sh
```

Das Skript aktiviert sichere Cookies, bindet den direkten Host-Port nur noch an
`127.0.0.1` und gibt die oeffentliche HTTPS-Adresse aus. Die zufaellige
`trycloudflare.com`-Adresse kann sich bei einer Neuerstellung des
Tunnel-Containers aendern. Der Einladungscode bleibt weiterhin erforderlich.

Der Testzugang wird so wieder abgeschaltet:

```bash
cd /home/pi/ski-predictor
sudo bash scripts/deploy/Disable-Https-Test-Pi.sh
```

Fuer den dauerhaften Betrieb folgt spaeter ein benannter Tunnel mit eigener
Domain und stabiler Adresse.
