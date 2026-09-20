from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, ConfigDict

from models import StageName, PipelineStatus, MessageType, MessageSeverity


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
    full_output: Optional[Any]
    revision_round: int
    created_at: datetime


class MessageCreate(BaseModel):
    from_agent: str
    to_agent: str
    message_type: MessageType
    severity: MessageSeverity = MessageSeverity.blocking
    content: str
    payload: Optional[dict] = None
    stage_reference: StageName
    target_log_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    requires_response: bool = False


class MessageOut(MessageCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    resolved_log_id: Optional[str] = None
    created_at: datetime


class AnswerCreate(BaseModel):
    answer: str


class StageConfigUpdate(BaseModel):
    stage: StageName
    requires_approval: bool
    max_revision_rounds: int = 3
    model: Optional[str] = None  # örn. "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"
    enabled: bool = True  # False -> bu aşama tamamen atlanır
