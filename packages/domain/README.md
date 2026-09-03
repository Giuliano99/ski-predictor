# Domain

Vorgesehener Ort für gemeinsam genutzte Fachmodelle und Regeln.

Dazu gehören später Rennen, Fahrer, Tipps, Ergebnisse sowie die Punkteberechnung. Webanwendung, API und Ergebnisimport können diese Definitionen gemeinsam verwenden.

Die fachlichen Regeln sind in [`docs/product.md`](../../docs/product.md) beschrieben. Implementierungen in diesem Paket müssen diesen Regeln entsprechen.

Die technischen Datenverträge liegen unter `schemas`. Dazu gehören Tipprunde, Tippabgabe, Startliste, Rennergebnis, Wochenendauswertung, Saisonrangliste und Spielleiter-Workflow. Eine vollständige Demo-Tipprunde steht unter [`examples/tip-round.example.json`](examples/tip-round.example.json).
