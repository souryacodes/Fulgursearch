"""Instant top-K prefix trie with cumulative scores and O(prefix length) lookup."""

from __future__ import annotations

from config import TOP_K


def clean(text: str) -> str:
    """Lowercase text and collapse runs of whitespace into single spaces."""
    return " ".join(text.lower().split())


def bold_prefix_len(raw_input: str) -> int:
    """Return the character count to bold in suggestions for raw_input."""
    cleaned = clean(raw_input)
    if not cleaned:
        return 0
    trailing_space = 1 if raw_input and raw_input[-1].isspace() and raw_input.strip() else 0
    return len(cleaned) + trailing_space


class Node:
    """Trie node caching its top-K (score, word) entries."""

    __slots__ = ("children", "top")

    def __init__(self) -> None:
        self.children: dict[str, Node] = {}
        self.top: list[tuple[float, str]] = []


class Trie:
    """Prefix trie where every node caches its top-K suggestions."""

    def __init__(self, k: int = TOP_K) -> None:
        if k <= 0:
            raise ValueError("k must be positive")
        self.root: Node = Node()
        self.k: int = k
        self.scores: dict[str, float] = {}

    def add(self, word: str, score: float = 1.0) -> None:
        """Add cumulative score for word and refresh cached top-K lists along its path."""
        cleaned = clean(word)
        if not cleaned:
            return
        total = self.scores.get(cleaned, 0.0) + float(score)
        self.scores[cleaned] = total

        node = self.root
        self._update_node(node, cleaned, total)
        for ch in cleaned:
            child = node.children.get(ch)
            if child is None:
                child = Node()
                node.children[ch] = child
            node = child
            self._update_node(node, cleaned, total)

    def _update_node(self, node: Node, word: str, score: float) -> None:
        """Replace any prior entry for word, sort by score desc then word asc, slice to K."""
        updated = [(s, w) for s, w in node.top if w != word]
        updated.append((score, word))
        updated.sort(key=lambda item: (-item[0], item[1]))
        node.top = updated[: self.k]

    def suggest(self, prefix: str) -> list[str]:
        """Return top-K words matching prefix (preserving one trailing space after non-blank input)."""
        cleaned = clean(prefix)
        if not cleaned:
            return []
        trailing = " " if prefix and prefix[-1].isspace() and prefix.strip() else ""
        lookup = cleaned + trailing
        node = self.root
        for ch in lookup:
            node = node.children.get(ch)
            if node is None:
                return []
        return [word for _, word in node.top]
