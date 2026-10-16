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
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    return datetime.now(UTC)


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    idea_text: Mapped[str] = mapped_column(Text, nullable=False)
    current_stage: Mapped[StageName] = mapped_column(SAEnum(StageName), default=StageName.research)
    status: Mapped[PipelineStatus] = mapped_column(SAEnum(PipelineStatus), default=PipelineStatus.running)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    logs: Mapped[list["PipelineLog"]] = relationship(back_populates="pipeline")
    messages: Mapped[list["AgentMessage"]] = relationship(back_populates="pipeline")


class PipelineLog(Base):
    """Her aşamanın raporu. requires_approval'dan bağımsız, her zaman yazılır."""
    __tablename__ = "pipeline_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    pipeline_id: Mapped[str] = mapped_column(String, ForeignKey("pipelines.id"), nullable=False)
    stage: Mapped[StageName] = mapped_column(SAEnum(StageName), nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)          # kısa, insan-okur özet
    full_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # yapılandırılmış tam çıktı
    model: Mapped[str | None] = mapped_column(String, nullable=True)   # bu log'u üreten ajanın modeli
    revision_round: Mapped[int] = mapped_column(Integer, default=0)      # 0 = ilk deneme, 1+ = revizyon
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="logs")


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

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    pipeline_id: Mapped[str] = mapped_column(String, ForeignKey("pipelines.id"), nullable=False)
    from_agent: Mapped[str] = mapped_column(String, nullable=False)       # "test_agent", "user", vb.
    to_agent: Mapped[str] = mapped_column(String, nullable=False)         # "coding_agent" vb. ya da "user"
    message_type: Mapped[MessageType] = mapped_column(SAEnum(MessageType), nullable=False)
    severity: Mapped[MessageSeverity] = mapped_column(SAEnum(MessageSeverity), default=MessageSeverity.blocking)
    content: Mapped[str] = mapped_column(Text, nullable=False)             # insan-okur açıklama
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)      # makine-işlenebilir detay
    stage_reference: Mapped[StageName] = mapped_column(SAEnum(StageName), nullable=False)
    target_log_id: Mapped[str | None] = mapped_column(String, ForeignKey("pipeline_logs.id"), nullable=True)
    parent_message_id: Mapped[str | None] = mapped_column(String, ForeignKey("agent_messages.id"), nullable=True)
    requires_response: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_log_id: Mapped[str | None] = mapped_column(String, ForeignKey("pipeline_logs.id"), nullable=True)
    status: Mapped[MessageStatus] = mapped_column(SAEnum(MessageStatus), default=MessageStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="messages")


class StageConfig(Base):
    """
    pipeline_id NULL ise global varsayılan; belirli bir pipeline_id
    verilirse o koşu için override eder (kullanıcı isterse aşama
    bazında onay ayarını değiştirebilsin diye).
    """
    __tablename__ = "stage_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    pipeline_id: Mapped[str | None] = mapped_column(String, ForeignKey("pipelines.id"), nullable=True)
    stage: Mapped[StageName] = mapped_column(SAEnum(StageName), nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    max_revision_rounds: Mapped[int] = mapped_column(Integer, default=3)
    model: Mapped[str | None] = mapped_column(String, nullable=True)  # boşsa orchestrator varsayılanı
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # False ise bu aşama tamamen atlanır


class PipelineContract(Base):
    """Onaylanan bir aşamanın değişmez (immutable) çıktı kaydı.

    Onay anında ilgili PipelineLog.full_output hash'lenip saklanır; aşama
    sonradan yeniden çalıştırılıp çıktı değişirse ileri aşamalar bloklanır
    (bkz. orchestrator._contract_violations).
    """
    __tablename__ = "pipeline_contracts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    pipeline_id: Mapped[str] = mapped_column(
        String, ForeignKey("pipelines.id"), nullable=False, index=True
    )
    stage: Mapped[StageName] = mapped_column(SAEnum(StageName), nullable=False)
    source_log_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("pipeline_logs.id"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
