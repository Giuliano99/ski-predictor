"""Small database-backed authentication service for the private predictor."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from typing import Any

from database import DatabaseError


PASSWORD_ITERATIONS = 600_000
SESSION_HOURS = 12
SESSION_COOKIE = "ski_session"
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


class AuthError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, iterations: int = PASSWORD_ITERATIONS) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return f"pbkdf2_sha256${iterations}${encode_bytes(salt)}${encode_bytes(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), decode_bytes(salt), int(iterations), dklen=32,
        )
        return hmac.compare_digest(digest, decode_bytes(expected))
    except (ValueError, TypeError):
        return False


def validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
        raise AuthError("Das Passwort muss zwischen 10 und 128 Zeichen lang sein.")


def normalize_username(username: str) -> str:
    normalized = str(username).strip().casefold()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise AuthError("Der Benutzername muss 3 bis 32 Zeichen lang sein und darf Buchstaben, Zahlen, Punkt, Minus und Unterstrich enthalten.")
    return normalized


def validate_display_name(display_name: str) -> str:
    normalized = " ".join(str(display_name).split())
    if len(normalized) < 2 or len(normalized) > 40 or any(ord(character) < 32 for character in normalized):
        raise AuthError("Der Anzeigename muss zwischen 2 und 40 Zeichen lang sein.")
    return normalized


DUMMY_PASSWORD_HASH = hash_password("ungueltiges Vergleichspasswort")


class AuthService:
    def __init__(self, database: Any | None):
        self.database = database
        self.enabled = os.environ.get("SKI_AUTH_REQUIRED", "").casefold() in {"1", "true", "yes"}
        self.registration_code = os.environ.get("SKI_REGISTRATION_CODE", "")
        self.secure_cookie = os.environ.get("SKI_SECURE_COOKIES", "").casefold() in {"1", "true", "yes"}
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        if self.enabled and not database:
            raise DatabaseError("Authentifizierung benoetigt eine aktive Datenbank.")

    def _rate_limit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [stamp for stamp in self._attempts.get(key, []) if now - stamp < 900]
            if len(recent) >= 10:
                raise AuthError("Zu viele Anmeldeversuche. Bitte spaeter erneut versuchen.")
            recent.append(now)
            self._attempts[key] = recent

    def register(self, payload: dict[str, Any], client_key: str) -> dict[str, Any]:
        if not self.enabled:
            raise AuthError("Die Registrierung ist nicht aktiviert.")
        self._rate_limit(f"register:{client_key}")
        if not self.registration_code or not hmac.compare_digest(str(payload.get("inviteCode", "")), self.registration_code):
            raise AuthError("Der Einladungscode ist ungueltig.")
        username = normalize_username(str(payload.get("username", "")))
        display_name = validate_display_name(str(payload.get("displayName", "")))
        password = str(payload.get("password", ""))
        user = {
            "id": f"user-{uuid.uuid4().hex}", "username": username, "displayName": display_name,
            "passwordHash": hash_password(password), "role": "PLAYER", "active": True,
        }
        self.database.create_user(user)
        return user

    def login(self, payload: dict[str, Any], client_key: str) -> tuple[dict[str, Any], str]:
        if not self.enabled:
            raise AuthError("Die Anmeldung ist nicht aktiviert.")
        username = normalize_username(str(payload.get("username", "")))
        self._rate_limit(f"login:{client_key}:{username}")
        user = self.database.user_by_username(username)
        password = str(payload.get("password", ""))
        validate_password(password)
        verified = verify_password(password, user.get("passwordHash", "") if user else DUMMY_PASSWORD_HASH)
        if not user or not user.get("active") or not verified:
            raise AuthError("Benutzername oder Passwort ist falsch.")
        token = secrets.token_urlsafe(32)
        session = {
            "tokenHash": hashlib.sha256(token.encode("ascii")).hexdigest(),
            "userId": user["id"], "csrfToken": secrets.token_urlsafe(24),
            "expiresAt": (utc_now() + timedelta(hours=SESSION_HOURS)).isoformat(),
        }
        self.database.create_session(session)
        return self.public_user(user, session["csrfToken"]), token

    def authenticate(self, cookie_header: str | None) -> dict[str, Any] | None:
        if not self.enabled:
            return {"id": "local-development", "username": "local", "displayName": "Lokale Entwicklung", "role": "GAME_MASTER", "csrfToken": "development"}
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header or "")
            token = cookie.get(SESSION_COOKIE).value if cookie.get(SESSION_COOKIE) else ""
        except (KeyError, AttributeError):
            return None
        if not token:
            return None
        session = self.database.session_by_token_hash(hashlib.sha256(token.encode("ascii")).hexdigest())
        if not session:
            return None
        try:
            expires_at = datetime.fromisoformat(str(session["expiresAt"]).replace("Z", "+00:00"))
        except ValueError:
            return None
        if expires_at <= utc_now():
            self.database.delete_session(session["tokenHash"])
            return None
        return self.public_user(session, session["csrfToken"])

    def logout(self, cookie_header: str | None) -> None:
        if not self.enabled:
            return
        cookie = SimpleCookie()
        cookie.load(cookie_header or "")
        morsel = cookie.get(SESSION_COOKIE)
        if morsel:
            self.database.delete_session(hashlib.sha256(morsel.value.encode("ascii")).hexdigest())

    def cookie_header(self, token: str, *, clear: bool = False) -> str:
        value = f"{SESSION_COOKIE}={'deleted' if clear else token}; Path=/; HttpOnly; SameSite=Strict"
        value += "; Max-Age=0" if clear else f"; Max-Age={SESSION_HOURS * 3600}"
        if self.secure_cookie:
            value += "; Secure"
        return value

    @staticmethod
    def public_user(user: dict[str, Any], csrf_token: str) -> dict[str, Any]:
        return {
            "id": user["id"], "username": user["username"], "displayName": user["displayName"],
            "role": user["role"], "csrfToken": csrf_token,
        }
