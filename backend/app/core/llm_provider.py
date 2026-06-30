from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol


class LLMProvider(Protocol):
    name: str

    def summarize(self, document_type: str, masked_text: str, extracted_fields: dict[str, str]) -> str:
        ...


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
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an enterprise document analysis assistant. "
                        "Return concise, manager-ready analysis. Do not reveal or reconstruct masked PII."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 450,
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

        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            if content:
                return content
        except (KeyError, IndexError, json.JSONDecodeError, OSError, urllib.error.HTTPError):
            pass

        fallback_summary = self.fallback.summarize(document_type, masked_text, extracted_fields)
        return "NVIDIA NIM was configured but unavailable during this request. " + fallback_summary

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
