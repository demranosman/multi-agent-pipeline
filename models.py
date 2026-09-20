"""
Dört tablo:

- Pipeline: her "fikirden pazarlamaya" koşusunun ana kaydı, o an hangi
  aşamada olduğunu ve genel durumunu tutar.
- PipelineLog: her aşamanın ürettiği rapor. Append-only, onaydan
  bağımsız olarak HER aşamada yazılır.
- AgentMessage: ajanlar arası (veya kullanıcıdan gelen) hedefli
  geri bildirim / düzeltme talepleri.
- StageConfig: hangi aşamanın kullanıcı onayı gerektirdiği,
  kaç revizyon turuna izin verildiği.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, Integer,
    ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship

from database import Base


class StageName(str, enum.Enum):
    research = "research"
    planning = "planning"
    coding = "coding"
    testing = "testing"
    marketing = "marketing"


class PipelineStatus(str, enum.Enum):
    running = "running"
    waiting_approval = "waiting_approval"
    waiting_response = "waiting_response"  # bir ajan soru sordu, kullanıcı/başka ajan cevap bekleniyor
    escalated = "escalated"          # revizyon limiti aşıldı, kullanıcı karar vermeli
    completed = "completed"
    failed = "failed"


def gen_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """SQLAlchemy Column default'u için: datetime.utcnow() deprecated,
    timezone-aware bir eşdeğeri gerekiyor."""
    return datetime.now(timezone.utc)


class Pipeline(Base):
    __tablename__ = "pipelines"

    id = Column(String, primary_key=True, default=gen_id)
    idea_text = Column(Text, nullable=False)
    current_stage = Column(SAEnum(StageName), default=StageName.research)
    status = Column(SAEnum(PipelineStatus), default=PipelineStatus.running)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    logs = relationship("PipelineLog", back_populates="pipeline")
    messages = relationship("AgentMessage", back_populates="pipeline")


class PipelineLog(Base):
    """Her aşamanın raporu. requires_approval'dan bağımsız, her zaman yazılır."""
    __tablename__ = "pipeline_logs"

    id = Column(String, primary_key=True, default=gen_id)
    pipeline_id = Column(String, ForeignKey("pipelines.id"), nullable=False)
    stage = Column(SAEnum(StageName), nullable=False)
    agent = Column(String, nullable=False)
    summary = Column(Text, nullable=False)          # kısa, insan-okur özet
    full_output = Column(JSON, nullable=True)        # yapılandırılmış tam çıktı
    model = Column(String, nullable=True)             # bu log'u üreten ajanın kullandığı model
    revision_round = Column(Integer, default=0)      # 0 = ilk deneme, 1+ = revizyon
    created_at = Column(DateTime, default=utcnow)

    pipeline = relationship("Pipeline", back_populates="logs")


class MessageType(str, enum.Enum):
    correction_request = "correction_request"   # bir hatayı/sorunu düzeltme talebi
    suggestion = "suggestion"                    # bağlayıcı olmayan iyileştirme önerisi
    question = "question"                        # yanıt bekleyen soru (requires_response genelde true)
    answer = "answer"                             # bir question mesajına verilen doğrudan cevap
    user_feedback = "user_feedback"               # kullanıcıdan gelen serbest geri bildirim
    escalation_notice = "escalation_notice"       # revizyon limiti aşıldığında sistemin ürettiği bildirim


class MessageSeverity(str, enum.Enum):
    blocking = "blocking"      # çözülmeden pipeline bir sonraki aşamaya geçemez
    important = "important"    # onay ekranında kullanıcıya vurgulanır ama otomatik ilerlemeyi engellemez
    minor = "minor"            # sadece bilgi amaçlı, log'da görünür


class MessageStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"      # hedef ajan tarafından işlendi, yeni bir log üretildi
    acknowledged = "acknowledged"  # görüldü ama uygulanmadı (örn. minor bir öneri reddedildi)


class AgentMessage(Base):
    """Ajanlar arası ya da kullanıcıdan gelen hedefli geri bildirim."""
    __tablename__ = "agent_messages"

    id = Column(String, primary_key=True, default=gen_id)
    pipeline_id = Column(String, ForeignKey("pipelines.id"), nullable=False)
    from_agent = Column(String, nullable=False)       # "test_agent", "user", vb.
    to_agent = Column(String, nullable=False)         # "coding_agent" vb. ya da "user"
    message_type = Column(SAEnum(MessageType), nullable=False)
    severity = Column(SAEnum(MessageSeverity), default=MessageSeverity.blocking)
    content = Column(Text, nullable=False)             # insan-okur açıklama
    payload = Column(JSON, nullable=True)              # makine-işlenebilir detay (opsiyonel)
    stage_reference = Column(SAEnum(StageName), nullable=False)
    target_log_id = Column(String, ForeignKey("pipeline_logs.id"), nullable=True)
    parent_message_id = Column(String, ForeignKey("agent_messages.id"), nullable=True)
    requires_response = Column(Boolean, default=False)
    resolved_log_id = Column(String, ForeignKey("pipeline_logs.id"), nullable=True)
    status = Column(SAEnum(MessageStatus), default=MessageStatus.pending)
    created_at = Column(DateTime, default=utcnow)

    pipeline = relationship("Pipeline", back_populates="messages")


class StageConfig(Base):
    """
    pipeline_id NULL ise global varsayılan; belirli bir pipeline_id
    verilirse o koşu için override eder (kullanıcı isterse aşama
    bazında onay ayarını değiştirebilsin diye).
    """
    __tablename__ = "stage_configs"

    id = Column(String, primary_key=True, default=gen_id)
    pipeline_id = Column(String, ForeignKey("pipelines.id"), nullable=True)
    stage = Column(SAEnum(StageName), nullable=False)
    requires_approval = Column(Boolean, default=False)
    max_revision_rounds = Column(Integer, default=3)
    model = Column(String, nullable=True)  # örn. "claude-opus-5" - boşsa orchestrator'daki varsayılan kullanılır
    enabled = Column(Boolean, default=True)  # False ise bu aşama tamamen atlanır (ajan hiç çağrılmaz)
