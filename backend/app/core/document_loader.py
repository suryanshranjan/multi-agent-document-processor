from __future__ import annotations

import base64
import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LoadedDocument:
    text: str
    source_type: str
    filename: str | None = None
    warnings: list[str] = field(default_factory=list)


class DocumentLoader:
    def load(
        self,
        text: str = "",
        file_bytes: bytes | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> LoadedDocument:
        parts: list[str] = []
        warnings: list[str] = []
        source_type = "text"

        if text and text.strip():
            parts.append(text.strip())

        if file_bytes:
            lower_name = (filename or "").lower()
            if lower_name.endswith(".pdf") or content_type == "application/pdf":
                source_type = "pdf"
                pdf_text, pdf_warnings = self._extract_pdf_text(file_bytes)
                warnings.extend(pdf_warnings)
                parts.append(pdf_text)
            else:
                decoded_text = self._decode_text_file(file_bytes)
                source_type = self._infer_source_type(decoded_text, filename, content_type)
                parts.append(decoded_text)

        combined = "\n\n".join(part for part in parts if part.strip()).strip()
        if not combined:
            raise ValueError("Provide document text or upload a readable text-based file.")

        return LoadedDocument(
            text=combined,
            source_type=source_type,
            filename=filename,
            warnings=warnings,
        )

    def _decode_text_file(self, file_bytes: bytes) -> str:
        if self._looks_binary(file_bytes):
            raise ValueError("This file appears to be binary. Upload a text-based CSV, TXT, JSON, XML, HTML, log, or selectable-text PDF.")

        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Unable to decode uploaded file as text.")

    def _looks_binary(self, file_bytes: bytes) -> bool:
        if b"\x00" in file_bytes[:4096]:
            return True
        sample = file_bytes[:4096]
        if not sample:
            return False
        textish = sum(byte in b"\n\r\t\b\f" or 32 <= byte <= 126 for byte in sample)
        return textish / len(sample) < 0.72

    def _infer_source_type(self, text: str, filename: str | None, content_type: str | None) -> str:
        extension = Path(filename or "").suffix.lower()
        stripped = text.lstrip()
        first_lines = [line for line in text.splitlines()[:5] if line.strip()]
        first_line = first_lines[0] if first_lines else ""

        if extension == ".csv" or content_type in {"text/csv", "application/csv"} or self._looks_like_csv(first_lines):
            return "csv"
        if extension == ".json" or content_type == "application/json" or stripped.startswith(("{", "[")):
            return "json"
        if extension in {".xml", ".xhtml"} or stripped.startswith("<?xml"):
            return "xml"
        if extension in {".html", ".htm"} or re.search(r"<html|<!doctype html", stripped[:300], re.I):
            return "html"
        if extension in {".md", ".markdown"}:
            return "markdown"
        if extension in {".log"} or re.match(r"\d{4}-\d{2}-\d{2}[ T]", first_line):
            return "log"
        if extension in {".txt", ".text"} or (content_type or "").startswith("text/"):
            return "text"
        return "text file"

    def _looks_like_csv(self, lines: list[str]) -> bool:
        if len(lines) < 2:
            return False
        comma_counts = [line.count(",") for line in lines[:3]]
        return min(comma_counts) >= 1 and len(set(comma_counts)) <= 2

    def _extract_pdf_text(self, file_bytes: bytes) -> tuple[str, list[str]]:
        warnings: list[str] = []
        try:
            from pypdf import PdfReader  # type: ignore

            import io

            reader = PdfReader(io.BytesIO(file_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(page for page in pages if page.strip()).strip()
            if text:
                return text, warnings
        except Exception:
            warnings.append("pypdf was unavailable or could not extract this PDF; used fallback extraction.")

        text = self._extract_simple_pdf_text(file_bytes).strip()
        if not text:
            raise ValueError("No selectable text found in the PDF. Scanned PDFs need OCR, which is future scope.")
        return text, warnings

    def _extract_simple_pdf_text(self, file_bytes: bytes) -> str:
        pdf = file_bytes.decode("latin-1", errors="ignore")
        blocks: list[str] = []

        for obj in re.finditer(r"\d+\s+0\s+obj(?P<body>.*?)endobj", pdf, re.DOTALL):
            body = obj.group("body")
            if "/Subtype /Image" in body:
                continue
            stream = re.search(r"stream\s*(?P<data>.*?)endstream", body, re.DOTALL)
            if not stream:
                continue

            data = stream.group("data").strip()
            try:
                decoded = data.encode("latin-1")
                if "/ASCII85Decode" in body:
                    ascii_data = data
                    if ascii_data.endswith("~>"):
                        ascii_data = ascii_data[:-2]
                    decoded = base64.a85decode(ascii_data.encode("latin-1"), adobe=False)
                if "/FlateDecode" in body:
                    decoded = zlib.decompress(decoded)
                content = decoded.decode("latin-1", errors="ignore")
            except Exception:
                continue

            extracted = self._extract_pdf_text_operators(content)
            if extracted:
                blocks.append(extracted)

        return "\n".join(blocks)

    def _extract_pdf_text_operators(self, content: str) -> str:
        strings: list[str] = []

        for match in re.finditer(r"\((?:\\.|[^\\()])*\)\s*Tj", content):
            raw = match.group(0)
            strings.append(self._decode_pdf_literal(raw[1 : raw.rfind(")")]))

        for array_match in re.finditer(r"\[(?P<items>.*?)\]\s*TJ", content, re.DOTALL):
            for item in re.finditer(r"\((?:\\.|[^\\()])*\)", array_match.group("items")):
                strings.append(self._decode_pdf_literal(item.group(0)[1:-1]))

        lines = [re.sub(r"\s+", " ", item).strip() for item in strings]
        return "\n".join(line for line in lines if line)

    def _decode_pdf_literal(self, raw: str) -> str:
        def replace_escape(match: re.Match[str]) -> str:
            token = match.group(1)
            if re.fullmatch(r"[0-7]{1,3}", token):
                code = int(token, 8)
                return "-" if code == 127 else chr(code)
            return {
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "b": "\b",
                "f": "\f",
                "(": "(",
                ")": ")",
                "\\": "\\",
            }.get(token, token)

        return re.sub(r"\\([0-7]{1,3}|[nrtbf()\\])", replace_escape, raw)
