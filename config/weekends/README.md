# Rennwochenenden konfigurieren

Jedes Rennwochenende erhält eine JSON Konfiguration. Sie verbindet Originaldateien, normalisierte Daten, Fragen, Tippabgaben und Website-Ausgaben.

Für ein neues Wochenende wird `scripts/game-master/New-Weekend.ps1` verwendet. Unterstützt werden beliebig viele Start- und Ergebnislisten. Start- und Ergebnis-PDFs werden aus den konfigurierten Ordnern erkannt. Jede Ergebnisliste wird anhand ihrer Metadaten einer normalisierten Startliste zugeordnet und anschließend ausdrücklich in der Konfiguration hinterlegt.

`reviewReport` enthält die Prüfung vor der Veröffentlichung der Fragen. `resultReviewReport` enthält die Prüfung der offiziellen Ergebnisse unmittelbar vor der Punkteberechnung.

`testMode: true` hält nur eine lokale Testtipprunde unabhängig vom Datum offen. Bei echten Tipprunden wird der Wert entfernt oder auf `false` gesetzt.

Die Konfiguration enthält keine Namen oder Tippabgaben und kann eingecheckt werden.

Start- und Ergebnislisten werden über portable `storage://`-Referenzen angesprochen. Der tatsächliche lokale Stammordner steht ausschließlich in der von Git ignorierten Datei `config/local-storage.json`. Neue Wochenenden legt der Assistent automatisch unter `saisons/<Saison>/weekends/<Datum>` in diesem Datenspeicher an.
