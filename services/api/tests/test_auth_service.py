from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from auth_service import AuthError, AuthService, hash_password, verify_password  # noqa: E402
from database import SQLiteDatabase  # noqa: E402


class AuthServiceTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self) -> None:
        first = hash_password("ein langes Testpasswort")
        second = hash_password("ein langes Testpasswort")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("ein langes Testpasswort", first))
        self.assertFalse(verify_password("falsches Passwort", first))

    def test_registration_login_session_and_logout(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "SKI_AUTH_REQUIRED": "1", "SKI_REGISTRATION_CODE": "test-einladung",
        }, clear=False):
            database = SQLiteDatabase(Path(directory) / "auth.sqlite3")
            database.migrate()
            auth = AuthService(database)
            payload = {
                "username": "test.spieler", "displayName": "Test Spieler",
                "password": "sicheres Passwort 123", "inviteCode": "test-einladung",
            }
            registered = auth.register(payload, "local")
            user, token = auth.login(payload, "local")
            authenticated = auth.authenticate(f"other=x; ski_session={token}")
            auth.logout(f"ski_session={token}")
            after_logout = auth.authenticate(f"ski_session={token}")

        self.assertEqual(registered["role"], "PLAYER")
        self.assertEqual(user["id"], registered["id"])
        self.assertEqual(authenticated["displayName"], "Test Spieler")
        self.assertIsNone(after_logout)

    def test_rejects_wrong_invitation_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "SKI_AUTH_REQUIRED": "1", "SKI_REGISTRATION_CODE": "richtig",
        }, clear=False):
            database = SQLiteDatabase(Path(directory) / "auth.sqlite3")
            database.migrate()
            auth = AuthService(database)
            with self.assertRaises(AuthError):
                auth.register({
                    "username": "testuser", "displayName": "Test User",
                    "password": "sicheres Passwort 123", "inviteCode": "falsch",
                }, "local")


if __name__ == "__main__":
    unittest.main()
