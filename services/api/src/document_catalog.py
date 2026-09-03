"""Provider-neutral catalog for reusable PDF source documents."""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DOCUMENT_KINDS = {"START_LIST", "RESULT_LIST", "UNKNOWN"}


def iso_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def classify_path(relative_path: Path) -> tuple[str, str | None, str | None, bool]:
    parts = relative_path.parts
    folded = [part.casefold() for part in parts]
    kind = "UNKNOWN"
    if "startlisten" in folded or relative_path.name.casefold().startswith("startliste"):
        kind = "START_LIST"
    elif "ergebnislisten" in folded or "ergebnis" in relative_path.name.casefold() or relative_path.name.casefold().startswith("rennen"):
        kind = "RESULT_LIST"

    season_id = None
    weekend_date = None
    if len(parts) >= 5 and folded[0] == "saisons" and folded[2] == "weekends":
        season_id = parts[1]
        weekend_date = parts[3]
    return kind, season_id, weekend_date, folded[0] == "archiv"


@dataclass(frozen=True)
class Document:
    document_id: str
    content_hash: str
    kind: str
    original_name: str
    storage_reference: str
    size_bytes: int
    modified_at: str
    media_type: str
    season_id: str | None
    weekend_date: str | None
    archived: bool
    path: Path

    def public_value(self) -> dict[str, Any]:
        return {
            "documentId": self.document_id,
            "contentHash": f"sha256-{self.content_hash}",
            "kind": self.kind,
            "originalName": self.original_name,
            "storageReference": self.storage_reference,
            "sizeBytes": self.size_bytes,
            "modifiedAt": self.modified_at,
            "mediaType": self.media_type,
            "seasonId": self.season_id,
            "weekendDate": self.weekend_date,
            "archived": self.archived,
            "links": {
                "self": f"/api/v1/documents/{self.document_id}",
                "file": f"/api/v1/documents/{self.document_id}/file",
            },
        }


class DocumentCatalog:
    def __init__(self, storage_root: Path):
        self.storage_root = storage_root.resolve()
        self._hash_cache: dict[tuple[str, int, int], str] = {}

    def _content_hash(self, path: Path) -> str:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = self._hash_cache.get(key)
        if cached:
            return cached
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        value = digest.hexdigest()
        self._hash_cache[key] = value
        return value

    def _document(self, path: Path) -> Document:
        resolved = path.resolve()
        relative = resolved.relative_to(self.storage_root)
        stat = resolved.stat()
        content_hash = self._content_hash(resolved)
        reference_hash = hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()[:20]
        kind, season_id, weekend_date, archived = classify_path(relative)
        return Document(
            document_id=f"doc-{reference_hash}",
            content_hash=content_hash,
            kind=kind,
            original_name=resolved.name,
            storage_reference=f"storage://{relative.as_posix()}",
            size_bytes=stat.st_size,
            modified_at=iso_timestamp(stat.st_mtime),
            media_type=mimetypes.guess_type(resolved.name)[0] or "application/pdf",
            season_id=season_id,
            weekend_date=weekend_date,
            archived=archived,
            path=resolved,
        )

    def documents(self) -> list[Document]:
        if not self.storage_root.is_dir():
            return []
        documents = []
        for path in self.storage_root.rglob("*.pdf"):
            if not path.is_file():
                continue
            try:
                documents.append(self._document(path))
            except (OSError, ValueError):
                continue
        return sorted(documents, key=lambda item: (item.weekend_date or "", item.original_name.casefold()), reverse=True)

    def find(self, document_id: str) -> Document | None:
        return next((document for document in self.documents() if document.document_id == document_id), None)

    def query(
        self,
        *,
        kind: str | None = None,
        season_id: str | None = None,
        weekend_date: str | None = None,
        content_hash: str | None = None,
        archived: bool | None = None,
    ) -> list[Document]:
        normalized_hash = content_hash.removeprefix("sha256-") if content_hash else None
        return [
            document
            for document in self.documents()
            if (not kind or document.kind == kind)
            and (not season_id or document.season_id == season_id)
            and (not weekend_date or document.weekend_date == weekend_date)
            and (not normalized_hash or document.content_hash == normalized_hash)
            and (archived is None or document.archived == archived)
        ]

    def collections(self, documents: Iterable[Document] | None = None) -> list[dict[str, Any]]:
        grouped: dict[tuple[str | None, str | None], dict[str, Any]] = {}
        for document in documents if documents is not None else self.documents():
            key = (document.season_id, document.weekend_date)
            item = grouped.setdefault(key, {
                "seasonId": document.season_id,
                "weekendDate": document.weekend_date,
                "documents": 0,
                "startLists": 0,
                "resultLists": 0,
                "unknown": 0,
                "archived": document.archived,
            })
            item["documents"] += 1
            counter = {"START_LIST": "startLists", "RESULT_LIST": "resultLists", "UNKNOWN": "unknown"}[document.kind]
            item[counter] += 1
        return sorted(grouped.values(), key=lambda item: (item["weekendDate"] or ""), reverse=True)
