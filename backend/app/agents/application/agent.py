from __future__ import annotations

import re
import csv
from datetime import date
from io import StringIO
from dataclasses import dataclass, field


@dataclass
class ApplicationResult:
    document_type: str
    confidence: float
    extracted_fields: dict[str, str] = field(default_factory=dict)


class ApplicationAgent:
    def analyze(self, text: str) -> ApplicationResult:
        lowered = text.lower()
        tabular = self._analyze_tabular(text)
        invoice_score = sum(
            keyword in lowered
            for keyword in ("invoice", "invoice_number", "bill to", "gst", "tax invoice", "amount due", "grand total", "due date")
        )
        erp_score = sum(
            keyword in lowered
            for keyword in ("erp", "sap", "oracle", "material", "vendor code", "purchase order", "purchase_order", "po number")
        )

        if tabular and invoice_score >= 1 and erp_score >= 1:
            document_type = "Invoice/ERP Dataset"
            confidence = 0.9
        elif tabular and invoice_score >= 1:
            document_type = "Invoice Dataset"
            confidence = 0.86
        elif tabular and erp_score >= 1:
            document_type = "ERP Dataset"
            confidence = 0.84
        elif invoice_score >= max(2, erp_score):
            document_type = "Invoice"
            confidence = min(0.95, 0.55 + invoice_score * 0.08)
        elif erp_score >= 2:
            document_type = "ERP"
            confidence = min(0.92, 0.52 + erp_score * 0.08)
        elif tabular:
            document_type = "Tabular Dataset"
            confidence = 0.72
        else:
            document_type = "General Document"
            confidence = 0.5

        fields = self._extract_fields(text, document_type)
        fields.update(tabular)
        return ApplicationResult(document_type=document_type, confidence=round(confidence, 2), extracted_fields=fields)

    def _analyze_tabular(self, text: str) -> dict[str, str]:
        try:
            sample = text.strip()
            if not sample or "," not in sample:
                return {}
            reader = csv.DictReader(StringIO(sample))
            if not reader.fieldnames or len(reader.fieldnames) < 2:
                return {}
            rows = list(reader)
        except csv.Error:
            return {}

        headers = [header.strip() for header in reader.fieldnames if header and header.strip()]
        if len(headers) < 2 or not rows:
            return {}

        missing_values = 0
        duplicate_rows = 0
        seen_rows: set[tuple[str, ...]] = set()
        invalid_amounts = 0
        negative_amounts = 0
        invalid_dates = 0

        for row in rows:
            values = tuple(str(row.get(header) or "").strip() for header in headers)
            missing_values += sum(1 for value in values if not value)
            if values in seen_rows:
                duplicate_rows += 1
            seen_rows.add(values)

            for key, value in row.items():
                key_lower = (key or "").lower()
                clean_value = str(value or "").strip()
                if "amount" in key_lower or "total" in key_lower:
                    try:
                        amount = float(clean_value.replace(",", ""))
                        if amount < 0:
                            negative_amounts += 1
                    except ValueError:
                        if clean_value:
                            invalid_amounts += 1
                if "date" in key_lower and clean_value and not self._looks_like_date(clean_value):
                    invalid_dates += 1

        quality_flags = []
        if missing_values:
            quality_flags.append(f"{missing_values} missing values")
        if duplicate_rows:
            quality_flags.append(f"{duplicate_rows} duplicate rows")
        if invalid_dates:
            quality_flags.append(f"{invalid_dates} invalid dates")
        if invalid_amounts:
            quality_flags.append(f"{invalid_amounts} invalid amounts")
        if negative_amounts:
            quality_flags.append(f"{negative_amounts} negative amounts")

        result = {
            "source_shape": "tabular",
            "row_count": str(len(rows)),
            "column_count": str(len(headers)),
            "columns": ", ".join(headers[:10]),
        }
        if quality_flags:
            result["data_quality_flags"] = "; ".join(quality_flags)
        else:
            result["data_quality_flags"] = "No obvious row-level issues detected"
        return result

    def _looks_like_date(self, value: str) -> bool:
        match = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})|(\d{1,2})[-/](\d{1,2})[-/](\d{4})", value)
        if not match:
            return False
        numbers = [int(part) for part in match.groups() if part is not None]
        if len(numbers) != 3:
            return False
        if numbers[0] > 31:
            year, month, day = numbers
        else:
            day, month, year = numbers
        if not 1900 <= year <= 2200:
            return False
        try:
            date(year, month, day)
        except ValueError:
            return False
        return True

    def _extract_fields(self, text: str, document_type: str) -> dict[str, str]:
        field_patterns = {
            "invoice_number": r"\b(?:invoice\s*(?:no\.?|number|#)|inv\s*(?:no\.?|number|#)?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{2,29})",
            "purchase_order": r"\b(?:po\s*(?:no\.?|number|#)?|purchase order\s*(?:no\.?|number|#)?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{2,29})",
            "date": r"\b(?:date|invoice date|posting date)\s*[:#-]?\s*([0-3]?\d[-/][01]?\d[-/][12]\d{3}|[12]\d{3}[-/][01]?\d[-/][0-3]?\d)",
            "total_amount": r"\b(?:grand total|total amount|amount due|total)\s*[:#-]?\s*(?:rs\.?|inr|usd|\$)?\s*([0-9,]+(?:\.\d{1,2})?)",
            # Lazy match that stops at a line break, a run of spaces, or the next known field label,
            # so single-line documents don't pull the following field into the vendor name.
            "vendor": (
                r"\b(?:vendor|supplier|bill from|from)\s*[:#-]\s*([A-Za-z0-9 .,&-]{3,80}?)"
                r"(?=[ \t]*(?:\n|$)|[ \t]{2,}|[ \t]+(?:grand total|total|amount|invoice|date|due date|po|"
                r"purchase order|gst|gstin|contact|phone|email|bill to|ship to|material|address|tax)\b\s*[:#-])"
            ),
            "material": r"\b(?:material|item code|sku)\s*[:#-]?\s*([A-Z0-9/-]{3,40})",
        }
        fields: dict[str, str] = {}
        for name, pattern in field_patterns.items():
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .,-")
                if name in {"invoice_number", "purchase_order", "material"} and not any(char.isdigit() for char in value):
                    continue
                fields[name] = value

        if document_type == "ERP" and "purchase_order" not in fields:
            match = re.search(r"\b(?:transaction|document)\s*(?:id|number|#)?\s*[:#-]?\s*([A-Z0-9/-]{4,40})", text, re.I)
            if match:
                fields["transaction_id"] = match.group(1).strip()

        return fields
