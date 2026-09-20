"""
Orchestrator akışı:

  run_next_stage(pipeline)
      -> context'i önceki loglardan topla
      -> ilgili ajanı çağır
      -> PipelineLog yaz (HER ZAMAN - onaydan bağımsız)
      -> bu aşamaya yönelik bekleyen (pending) AgentMessage var mı bak
           - varsa: revizyon turu say, limit aşılmadıysa ajanı
             revision_note ile tekrar çalıştır (yeni bir log daha yazılır)
           - limit aşıldıysa: pipeline.status = escalated, kullanıcıya bırak
      -> stage_config.requires_approval ise: pipeline.status = waiting_approval,
         current_stage aynı kalır (approve_stage çağrılana kadar ilerlemez)
      -> değilse: bir sonraki aşamaya geç, (otomatik) tekrar çağrılabilir

  approve_stage(pipeline)  -> kullanıcı onayladı, bir sonraki aşamaya geç
  submit_message(...)      -> ajanlar arası / kullanıcıdan gelen düzeltme talebi
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import (
    Pipeline, PipelineLog, AgentMessage, StageConfig,
    StageName, PipelineStatus, MessageStatus, MessageSeverity, MessageType,
)
from agents import AGENT_MAP

STAGE_ORDER = [
    StageName.research,
    StageName.planning,
    StageName.coding,
    StageName.testing,
    StageName.marketing,
]

# stage_configs'te model belirtilmemişse (veya hiç config yoksa) kullanılacak
# görev-karmaşıklığına göre eşleştirilmiş varsayılanlar.
DEFAULT_MODELS = {
    StageName.research: "claude-sonnet-5",
    StageName.planning: "claude-opus-5",
    StageName.coding: "claude-sonnet-5",
    StageName.testing: "claude-haiku-4-5-20251001",
    StageName.marketing: "claude-sonnet-5",
}


def _resolve_model(cfg: StageConfig, stage: StageName) -> str:
    return cfg.model or DEFAULT_MODELS[stage]


def _next_stage(stage: StageName) -> Optional[StageName]:
    idx = STAGE_ORDER.index(stage)
    if idx + 1 < len(STAGE_ORDER):
        return STAGE_ORDER[idx + 1]
    return None


def _get_stage_config(db: Session, pipeline_id: str, stage: StageName) -> StageConfig:
    # önce pipeline'a özel override var mı bak, yoksa global varsayılana düş
    cfg = (
        db.query(StageConfig)
        .filter(StageConfig.pipeline_id == pipeline_id, StageConfig.stage == stage)
        .first()
    )
    if cfg:
        return cfg
    cfg = (
        db.query(StageConfig)
        .filter(StageConfig.pipeline_id.is_(None), StageConfig.stage == stage)
        .first()
    )
    if cfg:
        return cfg
    # hiç config yoksa güvenli varsayılan: onay gerektirsin, aşama etkin olsun
    return StageConfig(stage=stage, requires_approval=True, max_revision_rounds=3, enabled=True)


def _build_context(db: Session, pipeline: Pipeline) -> dict:
    """Önceki aşamaların en son (en yüksek revision_round) çıktılarını topla."""
    context = {"idea_text": pipeline.idea_text}
    logs = (
        db.query(PipelineLog)
        .filter(PipelineLog.pipeline_id == pipeline.id)
        .order_by(PipelineLog.created_at.asc())
        .all()
    )
    latest_by_stage = {}
    for log in logs:
        latest_by_stage[log.stage] = log  # sondaki kazanır
    for stage, log in latest_by_stage.items():
        context[f"{stage.value}_report"] = log.full_output
    return context


def _pending_message_for_stage(db: Session, pipeline_id: str, stage: StageName):
    """
    Sadece severity=blocking olan mesajlar otomatik revizyon tetikler.
    important/minor mesajlar kaydedilir ve görünür kalır ama pipeline'ı
    durdurmaz - ajan isterse ileride bunları da context'e dahil edebilirsin.
    """
    return (
        db.query(AgentMessage)
        .filter(
            AgentMessage.pipeline_id == pipeline_id,
            AgentMessage.stage_reference == stage,
            AgentMessage.status == MessageStatus.pending,
            AgentMessage.severity == MessageSeverity.blocking,
        )
        .order_by(AgentMessage.created_at.asc())
        .first()
    )


def run_stage(db: Session, pipeline: Pipeline) -> Pipeline:
    stage = pipeline.current_stage
    cfg = _get_stage_config(db, pipeline.id, stage)

    if not cfg.enabled:
        # Ajanı hiç çağırma - config üzerinden kapatılmış, doğrudan bir sonraki
        # aşamaya geç. Yine de /logs ve /report'ta görünsün diye bir not bırak.
        skip_log = PipelineLog(
            pipeline_id=pipeline.id,
            stage=stage,
            agent=f"{stage.value}_agent",
            summary="Bu aşama config üzerinden devre dışı bırakıldığı için atlandı.",
            full_output={"skipped": True},
            revision_round=0,
        )
        db.add(skip_log)
        db.commit()
        return _advance(db, pipeline)

    agent_fn = AGENT_MAP[stage.value]
    context = _build_context(db, pipeline)
    model = _resolve_model(cfg, stage)

    # bu aşama için daha önce kaç revizyon yapılmış say
    prior_rounds = (
        db.query(PipelineLog)
        .filter(PipelineLog.pipeline_id == pipeline.id, PipelineLog.stage == stage)
        .count()
    )

    pending = _pending_message_for_stage(db, pipeline.id, stage)
    revision_note = pending.content if pending else None

    result = agent_fn(context, revision_note=revision_note, model=model)

    log = PipelineLog(
        pipeline_id=pipeline.id,
        stage=stage,
        agent=f"{stage.value}_agent",
        summary=result["summary"],
        full_output=result["full_output"],
        model=model,
        revision_round=prior_rounds,  # 0 = ilk deneme
    )
    db.add(log)
    db.flush()  # log.id'yi commit etmeden alabilmek için

    if pending:
        pending.status = MessageStatus.processed
        pending.resolved_log_id = log.id
        db.add(pending)

        if prior_rounds + 1 >= cfg.max_revision_rounds:
            # limit aşıldı -> otomatik ilerlemeyi durdur, kullanıcıya bırak
            pipeline.status = PipelineStatus.escalated
            db.add(pipeline)
            db.commit()
            db.refresh(pipeline)
            return pipeline

    question_text = result.get("question")
    if question_text:
        # ajan ilerlemeden önce bir açıklamaya ihtiyaç duyuyor - onay/advance
        # akışına hiç girmeden kullanıcıya sor ve pipeline'ı durdur.
        q = AgentMessage(
            pipeline_id=pipeline.id,
            from_agent=f"{stage.value}_agent",
            to_agent="user",
            message_type=MessageType.question,
            severity=MessageSeverity.blocking,
            content=question_text,
            stage_reference=stage,
            target_log_id=log.id,
            requires_response=True,
        )
        db.add(q)
        pipeline.status = PipelineStatus.waiting_response
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)
        return pipeline

    if cfg.requires_approval:
        pipeline.status = PipelineStatus.waiting_approval
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)
        return pipeline

    # onay gerekmiyor -> otomatik ilerle
    return _advance(db, pipeline)


def _advance(db: Session, pipeline: Pipeline) -> Pipeline:
    nxt = _next_stage(pipeline.current_stage)
    if nxt is None:
        pipeline.status = PipelineStatus.completed
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)
        return pipeline

    pipeline.current_stage = nxt
    pipeline.status = PipelineStatus.running
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return run_stage(db, pipeline)


def approve_stage(db: Session, pipeline: Pipeline) -> Pipeline:
    """Kullanıcı mevcut aşamayı onayladı -> bir sonraki aşamaya geç ve çalıştır."""
    if pipeline.status not in (PipelineStatus.waiting_approval, PipelineStatus.escalated):
        raise ValueError("Pipeline onay bekleyen durumda değil.")
    return _advance(db, pipeline)


def submit_message(db: Session, pipeline_id: str, payload) -> AgentMessage:
    """Ajanlar arası veya kullanıcıdan gelen düzeltme/öneri talebi kaydet."""
    msg = AgentMessage(
        pipeline_id=pipeline_id,
        from_agent=payload.from_agent,
        to_agent=payload.to_agent,
        message_type=payload.message_type,
        content=payload.content,
        stage_reference=payload.stage_reference,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def rerun_current_stage(db: Session, pipeline: Pipeline) -> Pipeline:
    """
    Bekleyen bir mesaj (düzeltme talebi) işlendikten sonra aynı aşamayı
    tekrar çalıştırmak için. escalated durumdaki bir pipeline'da kullanıcı
    yeni bir mesaj bıraktıktan sonra manuel tetiklenebilir.
    """
    pipeline.status = PipelineStatus.running
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return run_stage(db, pipeline)


def answer_question(db: Session, pipeline: Pipeline, question_id: str, answer_text: str) -> Pipeline:
    """
    Kullanıcı (veya başka bir ajan) bekleyen bir 'question' mesajını cevaplar.
    Cevap, sorulan ajana yönelik yeni bir blocking mesaj olarak kaydedilir;
    bu da _pending_message_for_stage tarafından yakalanıp aynı aşama tekrar
    çalıştırıldığında otomatik olarak revision_note'a dönüşür - yani soran
    ajan, sorduğu sorunun cevabını normal revizyon akışıyla alır.
    """
    question = db.get(AgentMessage, question_id)
    if not question or question.pipeline_id != pipeline.id:
        raise ValueError("Soru bulunamadı.")
    if question.message_type != MessageType.question or question.status != MessageStatus.pending:
        raise ValueError("Bu mesaj yanıt bekleyen açık bir soru değil.")
    if pipeline.status != PipelineStatus.waiting_response:
        raise ValueError("Pipeline şu anda bir yanıt beklemiyor.")

    reply = AgentMessage(
        pipeline_id=pipeline.id,
        from_agent="user",
        to_agent=question.from_agent,
        message_type=MessageType.answer,
        severity=MessageSeverity.blocking,
        content=answer_text,
        stage_reference=question.stage_reference,
        parent_message_id=question.id,
        requires_response=False,
    )
    db.add(reply)

    question.status = MessageStatus.processed
    db.add(question)

    pipeline.current_stage = question.stage_reference
    db.commit()

    return rerun_current_stage(db, pipeline)
