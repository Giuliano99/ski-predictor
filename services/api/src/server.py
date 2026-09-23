"""Local backend API for Ski Predictor documents, workflows and submissions."""

from __future__ import annotations

import argparse
import hmac
import ipaddress
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

from auth_service import AuthError, AuthService
from document_catalog import DOCUMENT_KINDS, DocumentCatalog
from database import Database, DatabaseError
from data_quality import audit_database
from extraction_service import ExtractionError, ExtractionService
from workflow_service import (
    MAX_UPLOAD_BYTES,
    WorkflowError,
    all_weekends,
    close_expired_weekends,
    create_weekend,
    latest_public_submissions,
    perform_action,
    read_json,
    result_list_overview,
    resolve_path,
    save_questions,
    save_submission,
    start_list_overview,
    upload_file,
    weekend_config_path,
)


WORKSPACE = Path(__file__).resolve().parents[3]
API_VERSION = "1.12.0"
MAX_JSON_BYTES = 256 * 1024
LOCAL_ORIGIN_PATTERN = re.compile(r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$")
DASHBOARD_DIRECTORY = WORKSPACE / "apps" / "game-master"
WEB_DIRECTORY = WORKSPACE / "apps" / "web"
AUTH_DIRECTORY = WORKSPACE / "apps" / "auth"


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
            "/auth/register": {"post": {"summary": "Mit Einladungscode registrieren", "responses": {"201": {"description": "Registriert und angemeldet"}}}},
            "/auth/login": {"post": {"summary": "Anmelden", "responses": {"200": {"description": "Angemeldet"}, "401": {"description": "Anmeldung fehlgeschlagen"}}}},
            "/auth/logout": {"post": {"summary": "Sitzung beenden", "responses": {"200": {"description": "Abgemeldet"}}}},
            "/auth/me": {"get": {"summary": "Aktuelle Sitzung", "responses": {"200": {"description": "Angemeldeter Benutzer"}, "401": {"description": "Nicht angemeldet"}}}},
            "/admin/data-quality": {"get": {"summary": "Datenqualitaet pruefen", "responses": {"200": {"description": "Aktueller Pruefbericht"}, "400": {"description": "Datenbank nicht aktiviert"}}}},
            "/weekends/{weekendId}/extractions/approve-ready": {"post": {"summary": "Gepruefte Extraktionen gemeinsam freigeben", "responses": {"200": {"description": "Freigegebene Extraktionen"}}}},
            "/documents": {"get": {"summary": "Dokumente suchen", "parameters": [
                {"name": "kind", "in": "query", "schema": {"enum": sorted(DOCUMENT_KINDS)}},
                {"name": "seasonId", "in": "query", "schema": {"type": "string"}},
                {"name": "weekendDate", "in": "query", "schema": {"type": "string", "format": "date"}},
                {"name": "contentHash", "in": "query", "schema": {"type": "string"}},
                {"name": "archived", "in": "query", "schema": {"type": "boolean"}},
            ], "responses": {"200": {"description": "Gefundene Dokumente"}}}},
            "/documents/{documentId}": {"get": {"summary": "Metadaten eines Dokuments", "responses": {"200": {"description": "Dokument"}, "404": {"description": "Nicht gefunden"}}}},
            "/documents/{documentId}/file": {"get": {"summary": "Original-PDF abrufen", "responses": {"200": {"description": "PDF-Datei"}, "404": {"description": "Nicht gefunden"}}}},
            "/documents/{documentId}/extract": {"post": {"summary": "PDF-Extraktion starten", "responses": {"202": {"description": "Auftrag gestartet"}}}},
            "/documents/{documentId}/extraction": {"get": {"summary": "Letzte prüfbare Extraktion", "responses": {"200": {"description": "Extraktion und Prüfbericht"}}}},
            "/collections": {"get": {"summary": "Sammlungen nach Saison und Wochenende", "responses": {"200": {"description": "Sammlungen"}}}},
            "/imports": {"get": {"summary": "Versionierte PDF-Rohimporte", "responses": {"200": {"description": "Rohimporte"}}}},
            "/imports/{importId}": {"get": {"summary": "Vollständiger Rohimport mit PDF-Text", "responses": {"200": {"description": "Rohimport"}}}},
            "/health": {"get": {"summary": "Verfügbarkeit prüfen", "responses": {"200": {"description": "API ist bereit"}}}},
            "/weekends": {"get": {"summary": "Spielleiter-Wochenenden", "responses": {"200": {"description": "Wochenenden"}}}},
            "/extraction-jobs": {"get": {"summary": "Extraktionsaufträge", "responses": {"200": {"description": "Aufträge"}}}},
            "/extraction-jobs/{jobId}": {"get": {"summary": "Extraktionsstatus", "responses": {"200": {"description": "Auftrag"}}}},
            "/extraction-jobs/{jobId}/approve": {"post": {"summary": "Extraktion freigeben", "responses": {"200": {"description": "Freigegeben"}}}},
            "/events": {"get": {"summary": "Freigegebene Veranstaltungen", "responses": {"200": {"description": "Veranstaltungen"}}}},
            "/races": {"get": {"summary": "Freigegebene Rennen", "responses": {"200": {"description": "Rennen"}}}},
            "/races/{raceId}": {"get": {"summary": "Freigegebenes Rennen mit Startlisten und Ergebnissen", "responses": {"200": {"description": "Rennen"}}}},
            "/races/{raceId}/start-list": {"get": {"summary": "Freigegebene Startlisten eines Rennens", "responses": {"200": {"description": "Startlisten"}}}},
            "/races/{raceId}/results": {"get": {"summary": "Freigegebene Ergebnisse eines Rennens", "responses": {"200": {"description": "Ergebnisse"}}}},
            "/athletes": {"get": {"summary": "Kanonische Athleten", "responses": {"200": {"description": "Athleten"}}}},
            "/athletes/{athleteId}": {"get": {"summary": "Athlet mit Starts und Ergebnissen", "responses": {"200": {"description": "Athlet"}}}},
            "/athletes/{athleteId}/results": {"get": {"summary": "Ergebnisse eines Athleten", "responses": {"200": {"description": "Ergebnisse"}}}},
            "/athletes/{athleteId}/rankings": {"get": {"summary": "DSV-Ranglistenstände eines Athleten", "responses": {"200": {"description": "Ranglistenstände"}}}},
            "/athletes/{athleteId}/race-counts": {"get": {"summary": "Veröffentlichte Rennanzahlstände eines Athleten", "responses": {"200": {"description": "Rennanzahlstände"}}}},
            "/athletes/{athleteId}/analytics": {"get": {"summary": "Saisonweise Athletenübersicht", "responses": {"200": {"description": "Ergebnisse, Punkteverlauf und Ranglistenstände"}}}},
            "/athlete-identities/merge": {"post": {"summary": "Doppelte Athletenidentitäten zusammenführen", "responses": {"200": {"description": "Zusammengeführt"}}}},
            "/predictor/rounds/current": {"get": {"summary": "Aktuelle öffentliche Tipprunde", "responses": {"200": {"description": "Tipprunde"}}}},
            "/predictor/rounds/{tipRoundId}/submissions": {
                "get": {"summary": "Mitspieler-Tipps nach Abgabeschluss", "responses": {"200": {"description": "Sichtbarkeitsstatus und freigegebene Tipps"}}},
                "post": {"summary": "Tippabgabe speichern", "responses": {"201": {"description": "Abgabe gespeichert"}, "400": {"description": "Abgabe ungültig"}}},
            },
            "/predictor/rounds/{tipRoundId}/start-list": {"get": {"summary": "Startlistenübersicht", "responses": {"200": {"description": "Starter nach Altersklasse"}}}},
            "/predictor/rounds/{tipRoundId}/result-list": {"get": {"summary": "Ergebnislistenübersicht", "responses": {"200": {"description": "Ergebnisse nach Altersklasse"}}}},
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
<li><code>POST /api/v1/predictor/rounds/{{tipRoundId}}/submissions</code> Tippabgabe speichern</li>
</ul><p>Die API ist nur lokal unter <code>127.0.0.1:{port}</code> erreichbar. Dokumentzugriffe sind lesend; Änderungen am Spielbetrieb erfolgen kontrolliert über die Spielleiter-Oberfläche. Geöffnete Tipprunden nehmen validierte Abgaben über die API entgegen.</p><p><a href="/spielleiter/">Spielleiter öffnen</a> · <a href="/tippspiel/">Tippspiel öffnen</a></p></div></body></html>""".encode("utf-8")


def current_config() -> dict[str, Any]:
    paths = sorted((WORKSPACE / "config" / "weekends").glob("tip-round-????-??-??.json"), reverse=True)
    if not paths:
        raise ValueError("Keine Tipprunde vorhanden.")
    configs = [read_json(path) for path in paths]
    return next((config for config in configs if config.get("status", "DRAFT") == "OPEN"), configs[0])


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

    @property
    def extractions(self) -> ExtractionService:
        return self.server.extractions  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[API] {format % args}")

    def cors_origin(self) -> str | None:
        origin = self.headers.get("Origin", "")
        return origin if LOCAL_ORIGIN_PATTERN.fullmatch(origin) else None

    def common_headers(self, content_type: str, length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if self.server.auth.secure_cookie:  # type: ignore[attr-defined]
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        origin = self.cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.common_headers("application/json; charset=utf-8", len(body))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def authenticated_user(self, role: str | None = None) -> dict[str, Any] | None:
        user = self.server.auth.authenticate(self.headers.get("Cookie"))  # type: ignore[attr-defined]
        if not user:
            self.send_api_error(HTTPStatus.UNAUTHORIZED, "AUTH_REQUIRED", "Bitte zuerst anmelden.")
            return None
        if role and user.get("role") != role:
            self.send_api_error(HTTPStatus.FORBIDDEN, "ACCESS_DENIED", "Fuer diesen Bereich fehlen die Berechtigungen.")
            return None
        return user

    def valid_csrf(self, user: dict[str, Any]) -> bool:
        if not self.server.auth.enabled:  # type: ignore[attr-defined]
            return True
        if hmac.compare_digest(str(self.headers.get("X-CSRF-Token", "")), str(user.get("csrfToken", ""))):
            return True
        self.send_api_error(HTTPStatus.FORBIDDEN, "CSRF_INVALID", "Die Sitzung konnte nicht sicher bestaetigt werden. Bitte neu anmelden.")
        return False

    def client_key(self) -> str:
        forwarded = str(self.headers.get("CF-Connecting-IP", "")).strip()
        try:
            return str(ipaddress.ip_address(forwarded)) if forwarded else self.client_address[0]
        except ValueError:
            return self.client_address[0]

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

    def read_body(self, maximum: int = MAX_UPLOAD_BYTES) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length > maximum:
            raise WorkflowError("Die Anfrage ist zu groß.")
        return self.rfile.read(length)

    def read_json_body(self, maximum: int = MAX_JSON_BYTES) -> dict[str, Any]:
        try:
            value = json.loads(self.read_body(maximum).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WorkflowError("Die Anfrage enthält kein gültiges JSON.") from error
        if not isinstance(value, dict):
            raise WorkflowError("Die JSON-Anfrage muss ein Objekt enthalten.")
        return value

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        origin = self.cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type, X-CSRF-Token")
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
            if parts[0] == "login":
                relative = Path(*parts[1:]) if len(parts) > 1 else Path("index.html")
                candidate = (AUTH_DIRECTORY / relative).resolve()
                try:
                    candidate.relative_to(AUTH_DIRECTORY.resolve())
                except ValueError:
                    self.send_api_error(HTTPStatus.NOT_FOUND, "FILE_NOT_FOUND", "Die Datei wurde nicht gefunden.")
                    return
                self.send_file(candidate)
                return
            if parts == ["spielleiter"]:
                user = self.server.auth.authenticate(self.headers.get("Cookie"))  # type: ignore[attr-defined]
                if not user or user.get("role") != "GAME_MASTER":
                    self.redirect("/login/?next=/spielleiter/")
                    return
                self.send_file(DASHBOARD_DIRECTORY / "index.html")
                return
            if parts[:2] == ["spielleiter", "assets"] and len(parts) == 3:
                user = self.server.auth.authenticate(self.headers.get("Cookie"))  # type: ignore[attr-defined]
                if not user or user.get("role") != "GAME_MASTER":
                    self.send_api_error(HTTPStatus.UNAUTHORIZED, "AUTH_REQUIRED", "Bitte zuerst anmelden.")
                    return
                self.send_file(DASHBOARD_DIRECTORY / "assets" / Path(parts[2]).name)
                return
            if parts == ["tippspiel", "public", "images", "skiteam-logo.png"]:
                self.send_file(WEB_DIRECTORY / "public" / "images" / "skiteam-logo.png")
                return
            if parts[0] == "tippspiel":
                if not self.server.auth.authenticate(self.headers.get("Cookie")):  # type: ignore[attr-defined]
                    self.redirect("/login/?next=/tippspiel/")
                    return
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
                database_status = "disabled"
                if self.server.database:  # type: ignore[attr-defined]
                    database_status = "available" if self.server.database.ping() else "unavailable"  # type: ignore[attr-defined]
                self.send_json({"status": "ok", "version": API_VERSION, "storage": "available", "database": database_status, "authentication": "required" if self.server.auth.enabled else "disabled", "documents": len(self.catalog.documents())})
                return
            if parts == ["api", "v1", "openapi.json"]:
                self.send_json(openapi_document(self.server.server_port))
                return
            if parts == ["api", "v1", "auth", "me"]:
                user = self.authenticated_user()
                if user:
                    self.send_json({"user": user, "authentication": "required" if self.server.auth.enabled else "disabled"})
                return
            if parts[:2] == ["api", "v1"]:
                role = None if len(parts) > 2 and parts[2] == "predictor" else "GAME_MASTER"
                if not self.authenticated_user(role):
                    return
            if parts == ["api", "v1", "admin", "data-quality"]:
                if not self.server.database:  # type: ignore[attr-defined]
                    raise DatabaseError("Die Datenbank ist nicht aktiviert.")
                document_ids = {document.document_id for document in self.catalog.documents()}
                self.send_json(audit_database(self.server.database, document_ids))  # type: ignore[attr-defined]
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
            if parts == ["api", "v1", "imports"]:
                if not self.server.database:  # type: ignore[attr-defined]
                    raise DatabaseError("Die Datenbank ist nicht aktiviert.")
                imports = self.server.database.imports(first(query, "documentId"))  # type: ignore[attr-defined]
                self.send_json({"items": imports, "total": len(imports)})
                return
            if len(parts) == 4 and parts[:3] == ["api", "v1", "imports"]:
                if not self.server.database:  # type: ignore[attr-defined]
                    raise DatabaseError("Die Datenbank ist nicht aktiviert.")
                self.send_json(self.server.database.import_by_id(parts[3]))  # type: ignore[attr-defined]
                return
            if parts == ["api", "v1", "weekends"]:
                self.send_json({"weekends": all_weekends()})
                return
            if parts == ["api", "v1", "extraction-jobs"]:
                self.send_json({"items": self.extractions.jobs(first(query, "weekendDate"))})
                return
            if len(parts) == 4 and parts[:3] == ["api", "v1", "extraction-jobs"]:
                self.send_json(self.extractions.job(parts[3]))
                return
            if parts == ["api", "v1", "events"]:
                events = self.extractions.events()
                self.send_json({"items": events, "total": len(events)})
                return
            if parts == ["api", "v1", "races"]:
                races = self.extractions.races()
                self.send_json({"items": races, "total": len(races)})
                return
            if parts == ["api", "v1", "athletes"]:
                athletes = self.extractions.athletes(boolean_filter(first(query, "targetClub")))
                self.send_json({"items": athletes, "total": len(athletes)})
                return
            if len(parts) in {4, 5} and parts[:3] == ["api", "v1", "athletes"]:
                athlete = self.extractions.athlete(parts[3])
                if len(parts) == 4:
                    self.send_json(athlete)
                    return
                if parts[4] == "results":
                    self.send_json({"athlete": {key: value for key, value in athlete.items() if key not in {"starts", "results", "rankings", "raceCounts"}}, "items": athlete["results"], "total": len(athlete["results"])})
                    return
                if parts[4] == "rankings":
                    self.send_json({"athlete": {key: value for key, value in athlete.items() if key not in {"starts", "results", "rankings", "raceCounts"}}, "items": athlete["rankings"], "total": len(athlete["rankings"])})
                    return
                if parts[4] == "race-counts":
                    self.send_json({"athlete": {key: value for key, value in athlete.items() if key not in {"starts", "results", "rankings", "raceCounts"}}, "items": athlete["raceCounts"], "total": len(athlete["raceCounts"])})
                    return
                if parts[4] == "analytics":
                    self.send_json(self.extractions.athlete_analytics(parts[3]))
                    return
            if len(parts) == 4 and parts[:3] == ["api", "v1", "races"]:
                self.send_json(self.extractions.race(parts[3]))
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "races"]:
                race = self.extractions.race(parts[3])
                if parts[4] == "start-list":
                    self.send_json({"items": race["startLists"], "total": len(race["startLists"])})
                    return
                if parts[4] == "results":
                    self.send_json({"items": race["results"], "total": len(race["results"])})
                    return
            if parts == ["api", "v1", "predictor", "rounds", "current"]:
                stored = self.server.database.current_tip_round() if self.server.database else None  # type: ignore[attr-defined]
                if stored:
                    self.send_json(stored)
                else:
                    config = current_config()
                    self.send_json(optional_artifact(config["tipRound"]["websiteOutput"]) or optional_artifact(config["tipRound"]["output"]))
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "predictor", "rounds"] and parts[5] == "submissions":
                stored = self.server.database.submissions(parts[4]) if self.server.database else None  # type: ignore[attr-defined]
                evaluation = self.server.database.weekend_evaluation(parts[4]) if self.server.database else None  # type: ignore[attr-defined]
                self.send_json(latest_public_submissions(parts[4], stored, evaluation))
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "predictor", "rounds"] and parts[5] == "start-list":
                self.send_json(start_list_overview(parts[4]))
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "predictor", "rounds"] and parts[5] == "result-list":
                self.send_json(result_list_overview(parts[4]))
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "predictor", "rounds"] and parts[5] == "evaluation":
                stored = self.server.database.weekend_evaluation(parts[4]) if self.server.database else None  # type: ignore[attr-defined]
                if stored:
                    self.send_json(stored)
                else:
                    config = read_json(weekend_config_path(parts[4]))
                    self.send_json(optional_artifact(config["weekendEvaluation"]["websiteOutput"]) or {})
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "predictor", "seasons"] and parts[5] == "leaderboard":
                stored = self.server.database.season_leaderboard(parts[4]) if self.server.database else None  # type: ignore[attr-defined]
                if stored:
                    self.send_json(stored)
                    return
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
                if parts[4] == "extraction":
                    self.send_json(self.extractions.extraction(parts[3]))
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
        except (ValueError, OSError, WorkflowError, ExtractionError, DatabaseError) as error:
            self.send_api_error(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST", str(error))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if parts == ["api", "v1", "auth", "register"]:
                try:
                    payload = self.read_json_body()
                    self.server.auth.register(payload, self.client_key())  # type: ignore[attr-defined]
                    user, token = self.server.auth.login(payload, self.client_key())  # type: ignore[attr-defined]
                except AuthError as error:
                    self.send_api_error(HTTPStatus.BAD_REQUEST, "REGISTRATION_FAILED", str(error))
                    return
                self.send_json({"user": user}, HTTPStatus.CREATED, {"Set-Cookie": self.server.auth.cookie_header(token)})  # type: ignore[attr-defined]
                return
            if parts == ["api", "v1", "auth", "login"]:
                try:
                    user, token = self.server.auth.login(self.read_json_body(), self.client_key())  # type: ignore[attr-defined]
                except AuthError as error:
                    self.send_api_error(HTTPStatus.UNAUTHORIZED, "LOGIN_FAILED", str(error))
                    return
                self.send_json({"user": user}, headers={"Set-Cookie": self.server.auth.cookie_header(token)})  # type: ignore[attr-defined]
                return
            if parts == ["api", "v1", "auth", "logout"]:
                user = self.authenticated_user()
                if not user or not self.valid_csrf(user):
                    return
                self.server.auth.logout(self.headers.get("Cookie"))  # type: ignore[attr-defined]
                self.send_json({"message": "Abgemeldet."}, headers={"Set-Cookie": self.server.auth.cookie_header("", clear=True)})  # type: ignore[attr-defined]
                return
            role = None if len(parts) > 2 and parts[:3] == ["api", "v1", "predictor"] else "GAME_MASTER"
            user = self.authenticated_user(role)
            if not user or not self.valid_csrf(user):
                return
            if parts == ["api", "v1", "weekends"]:
                self.send_json(create_weekend(self.read_json_body()), HTTPStatus.CREATED)
                return
            if len(parts) == 6 and parts[:3] == ["api", "v1", "weekends"] and parts[4] == "files":
                self.send_json(upload_file(parts[3], parts[5], first(query, "filename") or "", self.read_body()), HTTPStatus.CREATED)
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "weekends"] and parts[4] == "actions":
                result = perform_action(parts[3], str(self.read_json_body().get("action", "")))
                self.server.sync_predictor()  # type: ignore[attr-defined]
                self.send_json(result)
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "weekends"] and parts[4] == "extractions":
                weekend_id = parts[3]
                config = read_json(weekend_config_path(weekend_id))
                jobs = self.extractions.start_weekend(weekend_id.removeprefix("tip-round-"))
                self.send_json({"message": f"{len(jobs)} Extraktionsaufträge wurden berücksichtigt.", "items": jobs, "seasonId": config.get("seasonId")}, HTTPStatus.ACCEPTED)
                return
            if len(parts) == 6 and parts[:3] == ["api", "v1", "weekends"] and parts[4:] == ["extractions", "approve-ready"]:
                weekend_id = parts[3]
                weekend_config_path(weekend_id)
                approved = self.extractions.approve_ready(weekend_id.removeprefix("tip-round-"))
                self.send_json({"message": f"{len(approved)} gepruefte Extraktionen wurden freigegeben.", "items": approved})
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "predictor", "rounds"] and parts[5] == "submissions":
                stored_round = self.server.database.tip_round(parts[4]) if self.server.database else None  # type: ignore[attr-defined]
                submission = self.read_json_body()
                if self.server.auth.enabled:  # type: ignore[attr-defined]
                    submission["player"] = {"id": user["id"], "displayName": user["displayName"]}
                    submission["authenticatedUserId"] = user["id"]
                result = save_submission(parts[4], submission, stored_round)
                if self.server.database:  # type: ignore[attr-defined]
                    self.server.database.save_submission(result["submission"])  # type: ignore[attr-defined]
                self.send_json(result, HTTPStatus.CREATED)
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "documents"] and parts[4] == "extract":
                job, created = self.extractions.start(parts[3], self.read_json_body())
                self.send_json({"job": job, "created": created}, HTTPStatus.ACCEPTED if created else HTTPStatus.OK)
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "extraction-jobs"] and parts[4] == "approve":
                self.send_json({"message": "Die Extraktion wurde freigegeben.", "job": self.extractions.approve(parts[3])})
                return
            if parts == ["api", "v1", "athlete-identities", "merge"]:
                payload = self.read_json_body()
                athlete = self.extractions.merge_athletes(str(payload.get("sourceAthleteId", "")), str(payload.get("targetAthleteId", "")))
                self.send_json({"message": "Die Athletenidentitäten wurden zusammengeführt.", "athlete": athlete})
                return
            self.send_api_error(HTTPStatus.NOT_FOUND, "ROUTE_NOT_FOUND", "Dieser API-Endpunkt existiert nicht.")
        except (ValueError, OSError, WorkflowError, ExtractionError, DatabaseError) as error:
            self.send_api_error(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST", str(error))

    def do_PUT(self) -> None:
        parts = [part for part in urllib.parse.urlsplit(self.path).path.split("/") if part]
        try:
            user = self.authenticated_user("GAME_MASTER")
            if not user or not self.valid_csrf(user):
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "weekends"] and parts[4] == "questions":
                self.send_json(save_questions(parts[3], str(self.read_json_body().get("content", ""))))
                return
            self.send_api_error(HTTPStatus.NOT_FOUND, "ROUTE_NOT_FOUND", "Dieser API-Endpunkt existiert nicht.")
        except (ValueError, OSError, WorkflowError, ExtractionError, DatabaseError) as error:
            self.send_api_error(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST", str(error))


class ApiServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], catalog: DocumentCatalog, database: Database | None = None):
        super().__init__(address, ApiHandler)
        self.catalog = catalog
        self.database = database
        self.auth = AuthService(database)
        self.extractions = ExtractionService(catalog, database=database)

    def sync_predictor(self) -> dict[str, int]:
        return self.database.sync_predictor_files(WORKSPACE) if self.database else {"rounds": 0, "evaluations": 0, "leaderboards": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4175)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--start-page", choices=["api", "spielleiter", "tippspiel"], default="api")
    arguments = parser.parse_args()
    catalog = DocumentCatalog(load_storage_root())
    database = Database.configured()
    if database:
        try:
            applied = database.migrate()
            documents = database.sync_documents(catalog.documents())
            predictor = database.sync_predictor_files(WORKSPACE)
            print(f"{database.provider_name} bereit: {documents} Dokumente und {predictor['rounds']} Tipprunden synchronisiert, {len(applied)} Migrationen angewendet.")
        except DatabaseError as error:
            print(f"WARNUNG: {error}")
            print("Die API startet vorübergehend mit JSON-Dateien. Es werden keine Datenbankeinträge geschrieben.")
            database = None
    else:
        print("Keine Datenbank konfiguriert. Die API verwendet weiterhin JSON-Dateien.")
    server = ApiServer((arguments.host, arguments.port), catalog, database)
    server.extractions.resume_incomplete()
    stop_event = threading.Event()
    def deadline_loop() -> None:
        while not stop_event.is_set():
            close_expired_weekends()
            server.sync_predictor()
            stop_event.wait(30)
    threading.Thread(target=deadline_loop, daemon=True).start()
    display_host = "127.0.0.1" if arguments.host in {"0.0.0.0", "::"} else arguments.host
    url = f"http://{display_host}:{arguments.port}"
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
