from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from models import MessageSeverity, MessageType, PipelineStatus, StageName


class PipelineCreate(BaseModel):
    idea_text: str


class PipelineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    idea_text: str
    current_stage: StageName
    status: PipelineStatus
    created_at: datetime


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    stage: StageName
    agent: str
    summary: str
    full_output: Any | None = None
    model: str | None = None
    revision_round: int
    created_at: datetime


class MessageCreate(BaseModel):
    from_agent: str
    to_agent: str
    message_type: MessageType
    severity: MessageSeverity = MessageSeverity.blocking
    content: str
    payload: dict | None = None
    stage_reference: StageName
    target_log_id: str | None = None
    parent_message_id: str | None = None
    requires_response: bool = False


class MessageOut(MessageCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    resolved_log_id: str | None = None
    created_at: datetime


class AnswerCreate(BaseModel):
    answer: str


class StageConfigUpdate(BaseModel):
    stage: StageName
    requires_approval: bool
    max_revision_rounds: int = 3
    model: str | None = None
    enabled: bool = True
