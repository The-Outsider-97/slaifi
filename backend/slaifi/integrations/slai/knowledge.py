"""Adapter from SLAIFI's knowledge port to SLAI's KnowledgeAgent.

Only SLAIFI's own guides and methodology are indexed (they are public by nature). Nothing about the
person's portfolios, strategies, goals or trades is ever added, and web fetching is never used.
Results from the shared SLAI index are filtered to the documents SLAIFI itself added.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from logs.logger import get_logger

from slaifi.application.contracts import KnowledgeAnswer, KnowledgePassage

logger = get_logger("SLAIFI SLAI Knowledge")

ID_PREFIX = "slaifi:"
MAX_QUERY_CHARS = 300
MAX_PASSAGE_CHARS = 900
MIN_CHUNK_CHARS = 80
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


def chunk_markdown(text: str, source: str) -> list[tuple[str, str, str]]:
    """Split a markdown file into ``(doc_id, heading, body)`` pieces at its headings.

    Long sections are cut at paragraph breaks so each passage stays quotable.
    """

    chunks: list[tuple[str, str, str]] = []
    title = Path(source).stem
    heading = title
    lines: list[str] = []

    def flush() -> None:
        body = "\n".join(lines).strip()
        lines.clear()
        if len(body) < MIN_CHUNK_CHARS:
            return
        parts: list[str] = []
        current = ""
        for paragraph in re.split(r"\n\s*\n", body):
            if current and len(current) + len(paragraph) > MAX_PASSAGE_CHARS:
                parts.append(current)
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}" if current else paragraph
        if current:
            parts.append(current)
        for index, part in enumerate(parts, start=1):
            suffix = f"#{len(chunks) + 1}" if index == 1 else f"#{len(chunks) + 1}.{index}"
            chunks.append((f"{ID_PREFIX}{source}{suffix}", heading, part))

    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        match = None if in_code else _HEADING.match(line)
        if match:
            flush()
            heading = match.group(2)
        else:
            lines.append(line)
    flush()
    return chunks


def load_documents(root: Path) -> list[tuple[str, str, str, str]]:
    """``(doc_id, source, heading, text)`` for every markdown file under ``root`` (a docs folder)."""

    documents: list[tuple[str, str, str, str]] = []
    if not root.is_dir():
        return documents
    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Skipping unreadable guide %s: %s", path.name, exc)
            continue
        source = f"{root.name}/{path.relative_to(root).as_posix()}"
        for doc_id, heading, body in chunk_markdown(text, source):
            documents.append((doc_id, source, heading, body))
    return documents


class SlaiKnowledgeLibrary:
    """Search SLAIFI's guides through SLAI's KnowledgeAgent; degrades to "unavailable"."""

    def __init__(
        self,
        agent_provider: Callable[[str], Any],
        docs_dir: Path,
        *,
        enabled: Callable[[], bool],
        report: Callable[[bool, str | None], None] | None = None,
        agent_type: str = "knowledge",
    ) -> None:
        self._agent_provider = agent_provider
        self._docs_dir = docs_dir
        self._enabled = enabled
        self._report = report or (lambda ok, detail: None)
        self._agent_type = agent_type
        self._lock = threading.Lock()
        self._agent: Any = None
        self._indexed = 0

    def _ensure_index(self) -> Any:
        with self._lock:
            if self._agent is not None:
                return self._agent
            agent = self._agent_provider(self._agent_type)
            added = 0
            for doc_id, source, heading, text in load_documents(self._docs_dir):
                agent.add_document(
                    f"{heading}\n{text}",
                    doc_id=doc_id,
                    metadata={"visibility": "public", "source": source, "heading": heading},
                )
                added += 1
            if added == 0:
                raise FileNotFoundError("no SLAIFI guides were found to index")
            self._indexed = added
            self._agent = agent
            return agent

    def search(self, query: str, limit: int = 5) -> KnowledgeAnswer:
        if not self._enabled():
            return KnowledgeAnswer("disabled", detail="The Knowledge agent is switched off.")
        text = " ".join(query.split())[:MAX_QUERY_CHARS]
        if len(text) < 2:
            return KnowledgeAnswer("no_match", detail="Type a word or a question to look up.")
        limit = max(1, min(int(limit), 10))
        try:
            agent = self._ensure_index()
            # Ask for more than needed: the shared index may also hold documents that are not ours.
            raw = agent.retrieve(text, k=limit * 4)
        except Exception as exc:  # noqa: BLE001 - an unavailable agent must not break the app
            detail = f"{type(exc).__name__}: {exc}"[:240]
            logger.warning("SLAI knowledge lookup unavailable: %s", detail)
            self._report(False, detail)
            return KnowledgeAnswer(
                "unavailable", detail=f"The Knowledge agent is not available ({detail})."
            )
        self._report(True, None)
        passages: list[KnowledgePassage] = []
        for item in raw or []:
            try:
                score, doc = item
                doc_id = str(doc.get("doc_id", ""))
                meta = doc.get("metadata") or {}
            except (TypeError, ValueError, AttributeError):
                continue
            if not doc_id.startswith(ID_PREFIX):
                continue
            body = str(doc.get("text", ""))
            heading = str(meta.get("heading", ""))
            if heading and body.startswith(heading):
                body = body[len(heading) :].lstrip()
            passages.append(
                KnowledgePassage(
                    source=str(meta.get("source", doc_id.removeprefix(ID_PREFIX).split("#")[0])),
                    heading=heading,
                    text=body[:MAX_PASSAGE_CHARS],
                    score=float(score),
                )
            )
            if len(passages) >= limit:
                break
        if not passages:
            return KnowledgeAnswer("no_match", detail="Nothing in SLAIFI's guides matched that.")
        return KnowledgeAnswer("ok", tuple(passages))
