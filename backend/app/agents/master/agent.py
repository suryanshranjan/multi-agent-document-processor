from __future__ import annotations

import uuid
from typing import Any

from backend.app.agents.application.agent import ApplicationAgent
from backend.app.agents.guardrails.agent import GuardrailsAgent
from backend.app.agents.monitoring.agent import MonitoringAgent
from backend.app.agents.sanitation.agent import SanitationAgent
from backend.app.agents.security.agent import SecurityAgent
from backend.app.core.cache import CacheStore
from backend.app.core.document_loader import DocumentLoader
from backend.app.core.llm_provider import LLMProvider, get_default_llm_provider
from backend.app.schemas import AgentTrace, AnalysisResponse


class MasterAgent:
    TOKEN_TREE = """Input
+- Hash normalized content
   +- Cache hit -> return saved result
   +- Cache miss
      +- Extract text
      +- Sanitize
      +- Mask PII
      +- Classify document
      +- Route reduced masked text to LLM provider
      +- Validate with guardrails
      +- Save result to cache"""

    def __init__(self, cache: CacheStore | None = None, llm_provider: LLMProvider | None = None) -> None:
        self.cache = cache or CacheStore()
        self.loader = DocumentLoader()
        self.sanitation = SanitationAgent()
        self.security = SecurityAgent()
        self.application = ApplicationAgent()
        self.guardrails = GuardrailsAgent()
        self.llm_provider = llm_provider or get_default_llm_provider()

    def analyze(
        self,
        text: str = "",
        file_bytes: bytes | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> AnalysisResponse:
        monitor = MonitoringAgent()
        request_id = str(uuid.uuid4())

        loaded = monitor.run_step(
            "DocumentLoader",
            "Loaded document input.",
            lambda: self.loader.load(text=text, file_bytes=file_bytes, filename=filename, content_type=content_type),
        )
        for warning in loaded.warnings:
            monitor.warn(warning)

        self.guardrails.validate_input(loaded.text)
        cache_key = self.cache.make_key(loaded.text)
        cached = self.cache.get(cache_key)
        if cached is not None:
            response = AnalysisResponse(**cached)
            response.request_id = request_id
            response.cache_hit = True
            response.trace = [
                AgentTrace(
                    agent="Cache",
                    status="hit",
                    message="Returned stored analysis without repeating agent execution.",
                    details={"cache_key": cache_key[:12]},
                )
            ] + response.trace
            return response

        monitor.record("Cache", "miss", "No stored analysis found; executing agent workflow.", {"cache_key": cache_key[:12]})

        sanitized = monitor.run_step(
            "SanitationAgent",
            "Cleaned and standardized document text.",
            lambda: self.sanitation.clean(loaded.text),
        )
        security = monitor.run_step(
            "SecurityAgent",
            "Detected and masked sensitive information.",
            lambda: self.security.mask(sanitized.cleaned_text),
        )
        application = monitor.run_step(
            "ApplicationAgent",
            "Classified document and extracted application fields.",
            lambda: self.application.analyze(security.masked_text),
        )
        reduced_text = self._reduce_for_llm(security.masked_text, application.extracted_fields)
        provider_name = getattr(self.llm_provider, "name", self.llm_provider.__class__.__name__)
        summary = monitor.run_step(
            provider_name,
            "Generated pluggable-LLM summary from reduced masked context.",
            lambda: self.llm_provider.summarize(application.document_type, reduced_text, application.extracted_fields),
        )
        output_warnings = monitor.run_step(
            "GuardrailsAgent",
            "Validated final response safety.",
            lambda: self.guardrails.validate_output(summary),
        )
        for warning in output_warnings:
            monitor.warn(warning)

        response = AnalysisResponse(
            request_id=request_id,
            cache_key=cache_key[:12],
            cache_hit=False,
            document_type=application.document_type,
            summary=summary,
            sanitized_preview=self._preview(sanitized.cleaned_text),
            masked_text_preview=self._preview(security.masked_text),
            extracted_fields=application.extracted_fields,
            pii_findings=security.findings,
            recommendations=self._recommendations(application.document_type, bool(security.findings)),
            trace=monitor.trace,
            warnings=monitor.warnings,
            token_tree=self.TOKEN_TREE,
            metrics={
                "source_type": loaded.source_type,
                "filename": loaded.filename,
                "original_chars": len(loaded.text),
                "sanitized_chars": sanitized.cleaned_chars,
                "reduced_chars_for_llm": len(reduced_text),
                "estimated_original_tokens": self._estimate_tokens(loaded.text),
                "estimated_reduced_tokens": self._estimate_tokens(reduced_text),
                "classification_confidence": application.confidence,
                "removed_duplicate_lines": sanitized.removed_duplicate_lines,
                "llm_provider": provider_name,
            },
        )
        self.cache.set(cache_key, self._model_to_dict(response))
        return response

    def _reduce_for_llm(self, text: str, fields: dict[str, str]) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        important_terms = ("invoice", "total", "amount", "vendor", "supplier", "purchase", "order", "material", "erp", "sap")
        selected = [line for line in lines if any(term in line.lower() for term in important_terms)]
        if fields:
            selected.insert(0, "Extracted fields: " + ", ".join(f"{key}={value}" for key, value in fields.items()))
        if not selected:
            selected = lines[:12]
        return "\n".join(selected)[:3_500]

    def _recommendations(self, document_type: str, has_pii: bool) -> list[str]:
        recommendations = [
            "Keep the mock LLM behind a provider interface so a private/internal model can be added without changing agents.",
            "Use cache-first routing for repeated enterprise documents to reduce latency and token usage.",
        ]
        if document_type == "Invoice":
            recommendations.append("Route invoice outputs to finance validation with extracted amount, date, vendor, and invoice number.")
        elif document_type == "ERP":
            recommendations.append("Route ERP outputs to transaction validation using purchase order, material, and vendor fields.")
        else:
            recommendations.append("Route general documents to summary and metadata extraction until a domain-specific agent is added.")
        if has_pii:
            recommendations.append("Require human approval or stricter policy checks before exporting documents with detected PII.")
        return recommendations

    def _preview(self, text: str, limit: int = 900) -> str:
        compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        return compact[:limit] + ("..." if len(compact) > limit else "")

    def _estimate_tokens(self, text: str) -> int:
        return max(1, round(len(text) / 4))

    def _model_to_dict(self, response: AnalysisResponse) -> dict[str, Any]:
        if hasattr(response, "model_dump"):
            return response.model_dump()
        return response.dict()
