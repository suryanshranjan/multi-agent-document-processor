from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentTrace(BaseModel):
    agent: str
    status: str
    message: str
    duration_ms: float = 0
    details: dict[str, Any] = Field(default_factory=dict)


class PIIFinding(BaseModel):
    type: str
    masked_value: str
    count: int


class AnalysisResponse(BaseModel):
    request_id: str
    cache_key: str
    cache_hit: bool
    document_type: str
    summary: str
    sanitized_preview: str
    masked_text_preview: str
    extracted_fields: dict[str, str] = Field(default_factory=dict)
    field_sources: dict[str, str] = Field(default_factory=dict)
    pii_findings: list[PIIFinding] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    trace: list[AgentTrace] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    token_tree: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    service: str
    cache_backend: str

