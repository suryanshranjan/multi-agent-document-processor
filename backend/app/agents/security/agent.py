from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.schemas import PIIFinding


@dataclass
class SecurityResult:
    masked_text: str
    findings: list[PIIFinding]


class SecurityAgent:
    PATTERNS: tuple[tuple[str, str, str], ...] = (
        ("email", r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL_MASKED]"),
        ("aadhaar", r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[AADHAAR_MASKED]"),
        ("pan", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "[PAN_MASKED]"),
        (
            "account",
            r"\b(?:account|acct|a/c)\s*(?:no\.?|number)?\s*[:#-]?\s*[0-9]{8,18}\b",
            "account [ACCOUNT_MASKED]",
        ),
        ("phone", r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3,5}\)?[-.\s]?){2,3}\d{3,4}(?!\d)", "[PHONE_MASKED]"),
    )

    def mask(self, text: str) -> SecurityResult:
        masked = text
        findings: list[PIIFinding] = []
        for pii_type, pattern, replacement in self.PATTERNS:
            regex = re.compile(pattern, flags=re.IGNORECASE)
            matches = regex.findall(masked)
            if not matches:
                continue
            masked = regex.sub(replacement, masked)
            findings.append(
                PIIFinding(
                    type=pii_type,
                    masked_value=replacement,
                    count=len(matches),
                )
            )
        return SecurityResult(masked_text=masked, findings=findings)

