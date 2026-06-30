from __future__ import annotations

import re


class GuardrailsAgent:
    def __init__(self, max_chars: int = 50_000) -> None:
        self.max_chars = max_chars

    def validate_input(self, text: str) -> None:
        if len(text) > self.max_chars:
            raise ValueError(f"Document is too large for this PoC. Limit is {self.max_chars} characters.")
        if re.search(r"\b(ignore previous instructions|system prompt|developer message)\b", text, re.I):
            raise ValueError("Potential prompt-injection instruction detected in the document.")

    def validate_output(self, output: str) -> list[str]:
        warnings: list[str] = []
        if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", output, re.I):
            warnings.append("Output may contain an unmasked email address.")
        if re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", output):
            warnings.append("Output may contain an unmasked PAN-like identifier.")
        return warnings

