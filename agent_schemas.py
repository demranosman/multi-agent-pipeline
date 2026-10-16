"""Ajan LLM çıktıları için Pydantic sözleşmeleri.

Modeller kasıtlı olarak gevşek ve varsayılanlıdır: LLM'ler ara sıra alan atlar
veya fazladan alan ekler. Amaç tip güvenliği — eksik alan çökmeye değil,
varsayılana düşmeli; yanlış tip ise sessizce geçmemeli (bkz. agents.py).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _AgentOutput(BaseModel):
    # Şemada olmayan ek alanları koru; alt ajanlar bunları prompt'ta görebilsin.
    model_config = ConfigDict(extra="allow")


class ResearchOutput(_AgentOutput):
    feasibility_score: int | None = None
    market_need: str | None = None
    difficulty: str | None = None
    target_customer: str | None = None
    competitors: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    reasoning: str | None = None


class PlanningOutput(_AgentOutput):
    stack: list[str] = Field(default_factory=list)
    architecture_notes: str | None = None
    milestones: list[str] = Field(default_factory=list)
    key_integrations: list[str] = Field(default_factory=list)
    estimated_weeks: int | None = None
    risks: list[str] = Field(default_factory=list)
    # Coding aşamasında izin verilen dosya/dizin desenleri ("app/*", "tests/*").
    # Boşsa kapsam denetimi atlanır. Onaylandığında contract'a girer.
    scope_patterns: list[str] = Field(default_factory=list)
    reasoning: str | None = None


class CodeFile(BaseModel):
    path: str = ""
    content: str = ""


class CodingOutput(_AgentOutput):
    files: list[CodeFile] = Field(default_factory=list)
    diff_summary: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    reasoning: str | None = None


class Finding(BaseModel):
    severity: str = "minor"
    description: str = ""
    file: str = ""


class TestingOutput(_AgentOutput):
    findings: list[Finding] = Field(default_factory=list)
    generated_tests: list[CodeFile] = Field(default_factory=list)
    recommended_action: str = "approve"
    reasoning: str | None = None


class MarketingOutput(_AgentOutput):
    positioning: str | None = None
    target_messaging: str | None = None
    channels: list[str] = Field(default_factory=list)
    campaign_ideas: list[str] = Field(default_factory=list)
    content_calendar_suggestion: str | None = None
    reasoning: str | None = None
