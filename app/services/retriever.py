from pathlib import Path


class KBRetriever:
    def __init__(self, kb_dir: str) -> None:
        self.kb_dir = Path(kb_dir)

    def _read_docs(self) -> list[tuple[str, str]]:
        if not self.kb_dir.exists():
            return []

        docs: list[tuple[str, str]] = []
        for path in self.kb_dir.glob("*.md"):
            docs.append((path.name, path.read_text(encoding="utf-8", errors="ignore")))
        return docs

    def retrieve(self, query: str, top_k: int = 3) -> list[tuple[str, str]]:
        """Simple keyword overlap retrieval for local markdown KB."""
        query_terms = {t for t in query.lower().split() if len(t) > 2}
        scored: list[tuple[int, str, str]] = []

        for name, text in self._read_docs():
            text_l = text.lower()
            score = sum(1 for term in query_terms if term in text_l)
            if score > 0:
                scored.append((score, name, text))

        scored.sort(key=lambda row: row[0], reverse=True)
        return [(name, text) for _, name, text in scored[:top_k]]
