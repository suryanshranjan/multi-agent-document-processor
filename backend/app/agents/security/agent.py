from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.schemas import PIIFinding


@dataclass
class SecurityResult:
    masked_text: str
    findings: list[PIIFinding]


class SecurityAgent:
    # Order matters: labelled account numbers are masked before the generic
    # 12-digit Aadhaar rule, otherwise they are misreported as Aadhaar.
    PATTERNS: tuple[tuple[str, str, str], ...] = (
        ("email", r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL_MASKED]"),
        (
            "account",
            r"(\b(?:account|acct|a/c)\s*(?:no\.?|number)?\s*[:#-]?\s*)[0-9]{8,18}\b",
            r"\1[ACCOUNT_MASKED]",
        ),
        ("aadhaar", r"(?<![+\d])\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b", "[AADHAAR_MASKED]"),
        ("pan", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "[PAN_MASKED]"),
        ("phone", r"(?<![\w/(])(?:\+|\()?\d[\d ().-]{8,16}\d(?![\w/])", "[PHONE_MASKED]"),
    )

    def mask(self, text: str) -> SecurityResult:
        masked = text
        findings: list[PIIFinding] = []
        for pii_type, pattern, replacement in self.PATTERNS:
            regex = re.compile(pattern, flags=re.IGNORECASE)
            count = 0

            def substitute(match: re.Match[str]) -> str:
                nonlocal count
                # Phone candidates must hold 10-13 digits, so dates, amounts and
                # short IDs that happen to contain separators are left alone.
                if pii_type == "phone" and not 10 <= sum(c.isdigit() for c in match.group(0)) <= 13:
                    return match.group(0)
                count += 1
                return match.expand(replacement)

            masked = regex.sub(substitute, masked)
            if count:
                findings.append(
                    PIIFinding(
                        type=pii_type,
                        masked_value=f"[{pii_type.upper()}_MASKED]",
                        count=count,
                    )
                )
        return SecurityResult(masked_text=masked, findings=findings)
