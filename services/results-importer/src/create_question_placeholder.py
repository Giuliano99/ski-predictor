"""Create a UTF-8 placeholder shown until start lists produce concrete questions."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--weekend-date", required=True)
    arguments = parser.parse_args()
    content = (
        f"# Fragen für {arguments.title}\n\n"
        "<!-- AUTO_FRAGENVORSCHLAEGE -->\n"
        f"> Sobald die Startlisten hochgeladen sind, erzeugt der Assistent konkrete Fragen für das Wochenende ab {arguments.weekend_date}.\n"
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
