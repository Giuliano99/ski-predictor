"""Local, read-only backend API for shared Ski Predictor source documents."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from document_catalog import DOCUMENT_KINDS, DocumentCatalog
from workflow_service import (
    MAX_UPLOAD_BYTES,
    WorkflowError,
    all_weekends,
    close_expired_weekends,
    create_weekend,
    perform_action,
    read_json,
    resolve_path,
    save_questions,
    upload_file,
    weekend_config_path,
)


WORKSPACE = Path(__file__).resolve().parents[3]
API_VERSION = "1.1.0"
LOCAL_ORIGIN_PATTERN = re.compile(r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$")
DASHBOARD_DIRECTORY = WORKSPACE / "apps" / "game-master"
WEB_DIRECTORY = WORKSPACE / "apps" / "web"


def load_storage_root(workspace: Path = WORKSPACE) -> Path:
    settings_path = workspace / "config" / "local-storage.json"
    if not settings_path.is_file():
        raise ValueError("Der externe Datenspeicher ist nicht konfiguriert.")
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    root = Path(str(settings.get("root", "")))
    if settings.get("provider") != "local-folder" or not root.is_absolute():
        raise ValueError("Die lokale Speicherkonfiguration ist ungültig.")
    return root


def first(query: dict[str, list[str]], name: str) -> str | None:
    value = query.get(name, [None])[0]
    return value.strip() if isinstance(value, str) and value.strip() else None


def boolean_filter(value: str | None) -> bool | None:
    if value is None:
        return None
    if value.casefold() in {"true", "1"}:
        return True
    if value.casefold() in {"false", "0"}:
        return False
    raise ValueError("archived muss true oder false sein.")


def integer_filter(value: str | None, default: int, maximum: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    if parsed < 0:
        raise ValueError("Pagination darf nicht negativ sein.")
    return min(parsed, maximum)


def openapi_document(port: int) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Ski Predictor API", "version": API_VERSION, "description": "Gemeinsames lokales Backend für Dokumente, Spielleiter und Tippspiel."},
        "servers": [{"url": f"http://127.0.0.1:{port}/api/v1"}],
        "paths": {
            "/documents": {"get": {"summary": "Dokumente suchen", "parameters": [
                {"name": "kind", "in": "query", "schema": {"enum": sorted(DOCUMENT_KINDS)}},
                {"name": "seasonId", "in": "query", "schema": {"type": "string"}},
                {"name": "weekendDate", "in": "query", "schema": {"type": "string", "format": "date"}},
                {"name": "contentHash", "in": "query", "schema": {"type": "string"}},
                {"name": "archived", "in": "query", "schema": {"type": "boolean"}},
            ], "responses": {"200": {"description": "Gefundene Dokumente"}}}},
            "/documents/{documentId}": {"get": {"summary": "Metadaten eines Dokuments", "responses": {"200": {"description": "Dokument"}, "404": {"description": "Nicht gefunden"}}}},
            "/documents/{documentId}/file": {"get": {"summary": "Original-PDF abrufen", "responses": {"200": {"description": "PDF-Datei"}, "404": {"description": "Nicht gefunden"}}}},
            "/collections": {"get": {"summary": "Sammlungen nach Saison und Wochenende", "responses": {"200": {"description": "Sammlungen"}}}},
            "/health": {"get": {"summary": "Verfügbarkeit prüfen", "responses": {"200": {"description": "API ist bereit"}}}},
            "/weekends": {"get": {"summary": "Spielleiter-Wochenenden", "responses": {"200": {"description": "Wochenenden"}}}},
            "/predictor/rounds/current": {"get": {"summary": "Aktuelle öffentliche Tipprunde", "responses": {"200": {"description": "Tipprunde"}}}},
            "/predictor/rounds/{tipRoundId}/evaluation": {"get": {"summary": "Öffentliche Wochenendauswertung", "responses": {"200": {"description": "Auswertung"}}}},
            "/predictor/seasons/{seasonId}/leaderboard": {"get": {"summary": "Öffentliche Saisonrangliste", "responses": {"200": {"description": "Rangliste"}}}},
        },
    }


def documentation_page(port: int) -> bytes:
    return f"""<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>Ski Document API</title><style>
body{{max-width:900px;margin:60px auto;padding:0 24px;color:#211d20;background:#f6f4f5;font:16px/1.6 system-ui}}h1{{font-size:42px;margin-bottom:4px}}.tag{{color:#c90035;font-weight:800;text-transform:uppercase;letter-spacing:.12em}}code{{padding:3px 7px;background:white;border:1px solid #ddd}}li{{margin:10px 0}}a{{color:#a8002d}}.card{{margin-top:30px;padding:25px;background:white;border-top:4px solid #c90035}}
</style></head><body><span class=\"tag\">Ski Predictor Backend</span><h1>Document API</h1><p>Start- und Ergebnislisten als gemeinsame Datenquelle für mehrere lokale Projekte.</p><div class=\"card\"><h2>Endpunkte</h2><ul>
<li><a href=\"/api/v1/health\"><code>GET /api/v1/health</code></a> Status</li>
<li><a href=\"/api/v1/documents\"><code>GET /api/v1/documents</code></a> alle Dokumente</li>
<li><a href=\"/api/v1/documents?kind=RESULT_LIST\"><code>GET /api/v1/documents?kind=RESULT_LIST</code></a> Ergebnislisten</li>
<li><a href=\"/api/v1/collections\"><code>GET /api/v1/collections</code></a> Sammlungen</li>
<li><a href=\"/api/v1/openapi.json\"><code>GET /api/v1/openapi.json</code></a> API-Vertrag</li>
</ul><p>Die API ist nur lokal unter <code>127.0.0.1:{port}</code> erreichbar. Dokumentzugriffe sind lesend; Änderungen am Spielbetrieb erfolgen kontrolliert über die Spielleiter-Oberfläche.</p><p><a href="/spielleiter/">Spielleiter öffnen</a> · <a href="/tippspiel/">Tippspiel öffnen</a></p></div></body></html>""".encode("utf-8")


def current_config() -> dict[str, Any]:
    configs = sorted((WORKSPACE / "config" / "weekends").glob("tip-round-????-??-??.json"), reverse=True)
    if not configs:
        raise ValueError("Keine Tipprunde vorhanden.")
    return read_json(configs[0])


def optional_artifact(reference: str | None) -> dict[str, Any] | None:
    if not reference:
        return None
    path = resolve_path(reference)
    return read_json(path) if path.is_file() else None


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "SkiDocumentAPI/1.0"

    @property
    def catalog(self) -> DocumentCatalog:
        return self.server.catalog  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[API] {format % args}")

    def cors_origin(self) -> str | None:
        origin = self.headers.get("Origin", "")
        return origin if LOCAL_ORIGIN_PATTERN.fullmatch(origin) else None

    def common_headers(self, content_type: str, length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        origin = self.cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.common_headers("application/json; charset=utf-8", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_api_error(self, status: HTTPStatus, code: str, message: str) -> None:
        self.send_json({"error": {"code": code, "message": message}}, status)

    def send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_api_error(HTTPStatus.NOT_FOUND, "FILE_NOT_FOUND", "Die Datei wurde nicht gefunden.")
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.common_headers(f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type, len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD_BYTES:
            raise WorkflowError("Die Anfrage ist größer als 25 MB.")
        return self.rfile.read(length)

    def read_json_body(self) -> dict[str, Any]:
        try:
            return json.loads(self.read_body().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkflowError("Die Anfrage enthält kein gültiges JSON.") from error

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        origin = self.cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type")
            self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if not parts:
                body = documentation_page(self.server.server_port)
                self.send_response(HTTPStatus.OK)
                self.common_headers("text/html; charset=utf-8", len(body))
                self.end_headers()
                self.wfile.write(body)
                return
            if parts == ["spielleiter"]:
                self.send_file(DASHBOARD_DIRECTORY / "index.html")
                return
            if parts[:2] == ["spielleiter", "assets"] and len(parts) == 3:
                self.send_file(DASHBOARD_DIRECTORY / "assets" / Path(parts[2]).name)
                return
            if parts[0] == "tippspiel":
                relative = Path(*parts[1:]) if len(parts) > 1 else Path("index.html")
                candidate = (WEB_DIRECTORY / relative).resolve()
                try:
                    candidate.relative_to(WEB_DIRECTORY.resolve())
                except ValueError:
                    self.send_api_error(HTTPStatus.NOT_FOUND, "FILE_NOT_FOUND", "Die Datei wurde nicht gefunden.")
                    return
                self.send_file(candidate)
                return
            if parts == ["api", "v1", "health"]:
                self.send_json({"status": "ok", "version": API_VERSION, "storage": "available", "documents": len(self.catalog.documents())})
                return
            if parts == ["api", "v1", "openapi.json"]:
                self.send_json(openapi_document(self.server.server_port))
                return
            if parts == ["api", "v1", "documents"]:
                kind = first(query, "kind")
                if kind and kind not in DOCUMENT_KINDS:
                    raise ValueError(f"Unbekannte Dokumentart: {kind}")
                documents = self.catalog.query(
                    kind=kind,
                    season_id=first(query, "seasonId"),
                    weekend_date=first(query, "weekendDate"),
                    content_hash=first(query, "contentHash"),
                    archived=boolean_filter(first(query, "archived")),
                )
                offset = integer_filter(first(query, "offset"), 0, 100_000)
                limit = integer_filter(first(query, "limit"), 100, 500)
                self.send_json({"items": [item.public_value() for item in documents[offset:offset + limit]], "total": len(documents), "offset": offset, "limit": limit})
                return
            if parts == ["api", "v1", "collections"]:
                self.send_json({"items": self.catalog.collections()})
                return
            if parts == ["api", "v1", "weekends"]:
                self.send_json({"weekends": all_weekends()})
                return
            if parts == ["api", "v1", "predictor", "rounds", "current"]:
                config = current_config()
                self.send_json(optional_artifact(config["tipRound"]["websiteOutput"]) or optional_artifact(config["tipRound"]["output"]))
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "predictor", "rounds"] and parts[5] == "evaluation":
                config = read_json(weekend_config_path(parts[4]))
                self.send_json(optional_artifact(config["weekendEvaluation"]["websiteOutput"]) or {})
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "predictor", "seasons"] and parts[5] == "leaderboard":
                configs = [read_json(path) for path in (WORKSPACE / "config" / "weekends").glob("*.json")]
                config = next((item for item in configs if str(item.get("seasonId")) == parts[4]), None)
                if not config:
                    self.send_api_error(HTTPStatus.NOT_FOUND, "SEASON_NOT_FOUND", "Die Saison wurde nicht gefunden.")
                    return
                self.send_json(optional_artifact(config["seasonLeaderboard"]["websiteOutput"]) or {})
                return
            if len(parts) in {4, 5} and parts[:3] == ["api", "v1", "documents"]:
                document = self.catalog.find(parts[3])
                if not document:
                    self.send_api_error(HTTPStatus.NOT_FOUND, "DOCUMENT_NOT_FOUND", "Das Dokument wurde nicht gefunden.")
                    return
                if len(parts) == 4:
                    self.send_json(document.public_value())
                    return
                if parts[4] == "file":
                    body = document.path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.common_headers(document.media_type, len(body))
                    self.send_header("Content-Disposition", f'inline; filename="{document.original_name.replace(chr(34), "")}"')
                    self.send_header("ETag", f'"sha256-{document.content_hash}"')
                    self.end_headers()
                    self.wfile.write(body)
                    return
            self.send_api_error(HTTPStatus.NOT_FOUND, "ROUTE_NOT_FOUND", "Dieser API-Endpunkt existiert nicht.")
        except (ValueError, OSError, WorkflowError) as error:
            self.send_api_error(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST", str(error))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if parts == ["api", "v1", "weekends"]:
                self.send_json(create_weekend(self.read_json_body()), HTTPStatus.CREATED)
                return
            if len(parts) == 6 and parts[:3] == ["api", "v1", "weekends"] and parts[4] == "files":
                self.send_json(upload_file(parts[3], parts[5], first(query, "filename") or "", self.read_body()), HTTPStatus.CREATED)
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "weekends"] and parts[4] == "actions":
                self.send_json(perform_action(parts[3], str(self.read_json_body().get("action", ""))))
                return
            self.send_api_error(HTTPStatus.NOT_FOUND, "ROUTE_NOT_FOUND", "Dieser API-Endpunkt existiert nicht.")
        except (ValueError, OSError, WorkflowError) as error:
            self.send_api_error(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST", str(error))

    def do_PUT(self) -> None:
        parts = [part for part in urllib.parse.urlsplit(self.path).path.split("/") if part]
        try:
            if len(parts) == 5 and parts[:3] == ["api", "v1", "weekends"] and parts[4] == "questions":
                self.send_json(save_questions(parts[3], str(self.read_json_body().get("content", ""))))
                return
            self.send_api_error(HTTPStatus.NOT_FOUND, "ROUTE_NOT_FOUND", "Dieser API-Endpunkt existiert nicht.")
        except (ValueError, OSError, WorkflowError) as error:
            self.send_api_error(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST", str(error))


class ApiServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], catalog: DocumentCatalog):
        super().__init__(address, ApiHandler)
        self.catalog = catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4175)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--start-page", choices=["api", "spielleiter", "tippspiel"], default="api")
    arguments = parser.parse_args()
    catalog = DocumentCatalog(load_storage_root())
    server = ApiServer(("127.0.0.1", arguments.port), catalog)
    stop_event = threading.Event()
    def deadline_loop() -> None:
        while not stop_event.is_set():
            close_expired_weekends()
            stop_event.wait(30)
    threading.Thread(target=deadline_loop, daemon=True).start()
    url = f"http://127.0.0.1:{arguments.port}"
    print(f"Ski Document API: {url}")
    print("Zum Beenden Strg+C drücken.")
    if not arguments.no_browser:
        suffix = {"api": "/", "spielleiter": "/spielleiter/", "tippspiel": "/tippspiel/"}[arguments.start_page]
        threading.Timer(0.6, lambda: webbrowser.open(url + suffix)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBackend API beendet.")
    finally:
        stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
