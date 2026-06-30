from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SanitationResult:
    cleaned_text: str
    removed_duplicate_lines: int
    original_chars: int
    cleaned_chars: int


class SanitationAgent:
    def clean(self, text: str) -> SanitationResult:
        original_chars = len(text)
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+", " ", normalized)

        seen: set[str] = set()
        lines: list[str] = []
        duplicates = 0
        for line in normalized.split("\n"):
            clean_line = line.strip()
            if not clean_line:
                continue
            key = clean_line.lower()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            lines.append(clean_line)

        cleaned = "\n".join(lines).strip()
        return SanitationResult(
            cleaned_text=cleaned,
            removed_duplicate_lines=duplicates,
            original_chars=original_chars,
            cleaned_chars=len(cleaned),
        )

