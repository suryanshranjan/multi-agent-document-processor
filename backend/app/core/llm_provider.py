from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Protocol


class LLMProvider(Protocol):
    name: str

    def summarize(self, document_type: str, masked_text: str, extracted_fields: dict[str, str]) -> str:
        ...

    def extract_fields(self, document_type: str, masked_text: str, wanted_fields: list[str]) -> dict[str, str]:
        ...


FIELD_DESCRIPTIONS = {
    "invoice_number": "the invoice / bill / receipt number",
    "date": "the invoice or document date",
    "total_amount": "the final payable total (number only)",
    "vendor": "the supplier / seller company name",
    "purchase_order": "the purchase order number",
    "material": "the material / part / product code",
}


def parse_json_object(content: str) -> dict[str, str]:
    """Pull the first JSON object out of an LLM reply (tolerates ```json fences)."""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value).strip() for key, value in data.items() if value not in (None, "", "null")}


class MockLLMProvider:
    name = "MockLLMProvider"

    def summarize(self, document_type: str, masked_text: str, extracted_fields: dict[str, str]) -> str:
        field_text = ", ".join(f"{key}: {value}" for key, value in extracted_fields.items())
        if not field_text:
            field_text = "no high-confidence structured fields"

        compact_text = " ".join(masked_text.split())[:420]
        return (
            f"The document is classified as {document_type}. "
            f"Detected fields include {field_text}. "
            f"The content indicates an enterprise document processing task that should be routed through "
            f"sanitation, security validation, application-specific extraction, and guarded final response generation. "
            f"Relevant masked context: {compact_text}"
        )


    # Label synonyms the regex rules don't cover. This stands in for the LLM when no
    # API key is set, so the fallback path can be demoed offline.
    FIELD_SYNONYMS = {
        "invoice_number": ("bill no", "bill number", "receipt no", "receipt number", "ref no", "reference no"),
        "date": ("dated", "bill date", "issued on", "issue date"),
        "total_amount": ("net payable", "amount payable", "payable", "balance due", "total due"),
        "vendor": ("seller", "sold by", "billed by", "issued by"),
        "purchase_order": ("order ref", "order no", "order number"),
        "material": ("part no", "part number", "product code"),
    }

    def extract_fields(self, document_type: str, masked_text: str, wanted_fields: list[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for line in masked_text.splitlines():
            label, sep, value = line.partition(":")
            if not sep or not value.strip():
                continue
            label = label.strip().lower()
            for field in wanted_fields:
                if field not in found and label in self.FIELD_SYNONYMS.get(field, ()):
                    found[field] = value.strip()
        return found


class NvidiaNimProvider:
    name = "NvidiaNimProvider"

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        fallback: LLMProvider | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model or os.getenv("NVIDIA_NIM_MODEL", "meta/llama-3.1-8b-instruct")
        self.base_url = (base_url or os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")).rstrip("/")
        self.fallback = fallback or MockLLMProvider()

    def summarize(self, document_type: str, masked_text: str, extracted_fields: dict[str, str]) -> str:
        prompt = self._build_prompt(document_type, masked_text, extracted_fields)
        system = (
            "You are an enterprise document analysis assistant. "
            "Return concise, manager-ready analysis. Do not reveal or reconstruct masked PII."
        )
        try:
            content = self._chat(system, prompt, max_tokens=450, temperature=0.2)
            if content:
                return content
        except (KeyError, IndexError, json.JSONDecodeError, OSError, urllib.error.HTTPError):
            pass

        fallback_summary = self.fallback.summarize(document_type, masked_text, extracted_fields)
        return "NVIDIA NIM was configured but unavailable during this request. " + fallback_summary

    def extract_fields(self, document_type: str, masked_text: str, wanted_fields: list[str]) -> dict[str, str]:
        field_list = "\n".join(f"- {name}: {FIELD_DESCRIPTIONS.get(name, name)}" for name in wanted_fields)
        prompt = (
            f"Document type: {document_type}\n"
            f"Find these fields in the document:\n{field_list}\n\n"
            "Rules: copy each value exactly as it appears in the document. If a field is not present, use null. "
            "Never guess and never return masked placeholders like [EMAIL_MASKED]. "
            "Reply with a single JSON object whose keys are the field names, and nothing else.\n\n"
            f"Document:\n{masked_text}"
        )
        try:
            content = self._chat(
                "You extract fields from business documents and reply with JSON only.", prompt, max_tokens=200, temperature=0
            )
        except (KeyError, IndexError, json.JSONDecodeError, OSError, urllib.error.HTTPError):
            return {}
        data = parse_json_object(content)
        return {key: value for key, value in data.items() if key in wanted_fields}

    def _chat(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=35) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()

    def _build_prompt(self, document_type: str, masked_text: str, extracted_fields: dict[str, str]) -> str:
        field_text = "\n".join(f"- {key}: {value}" for key, value in extracted_fields.items()) or "- None"
        return (
            f"Document type: {document_type}\n"
            f"Extracted fields:\n{field_text}\n\n"
            "Masked document context:\n"
            f"{masked_text}\n\n"
            "Produce a short summary, key operational interpretation, and next-step recommendations."
        )


def get_default_llm_provider() -> LLMProvider:
    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if api_key:
        return NvidiaNimProvider(api_key=api_key)
    return MockLLMProvider()
