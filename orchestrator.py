"""
Orchestrator akışı:

  run_next_stage(pipeline)
      -> context'i önceki loglardan topla (pipeline_id dahil)
      -> ilgili ajanı çağır
      -> coding aşamasıysa üretilen dosyaları workspace'e yaz
      -> PipelineLog yaz (HER ZAMAN - onaydan bağımsız)
      -> bu aşamaya yönelik bekleyen (pending) AgentMessage var mı bak
           - varsa: revizyon turu say, limit aşılmadıysa ajanı
             revision_note ile tekrar çalıştır
           - limit aşıldıysa: pipeline.status = escalated, kullanıcıya bırak
      -> stage_config.requires_approval ise: pipeline.status = waiting_approval
      -> değilse: bir sonraki aşamaya geç
"""

from typing import Any

from sqlalchemy.orm import Session

from agents import AGENT_MAP
from gates import content_hash, out_of_scope_files, scan_placeholders
from models import (
    AgentMessage,
    MessageSeverity,
    MessageStatus,
    MessageType,
    Pipeline,
    PipelineContract,
    PipelineLog,
    PipelineStatus,
    StageConfig,
    StageName,
)
from workspace import write_files_to_workspace

STAGE_ORDER = [
    StageName.research,
    StageName.planning,
    StageName.coding,
    StageName.testing,
    StageName.marketing,
]

# Çoklu sağlayıcı varsayılanları (kullanıcı veya config ile değiştirilebilir)
DEFAULT_MODELS = {
    StageName.research: "claude-sonnet-5-5",          # veya gemini-3.8-flash / gpt-6-luna
    StageName.planning: "claude-opus-5-5",            # veya gpt-6.1-sol / gemini-3.1-pro-preview
    StageName.coding: "deepseek-v4-pro",              # zor akıl yürütme; veya claude-sonnet-5-5
    StageName.testing: "claude-haiku-4-5-20251001",   # hızlı/ekonomik; veya gpt-6-luna
    StageName.marketing: "claude-sonnet-5-5",         # veya gpt-6-astra / gemini-3.8-flash
}


def _resolve_model(cfg: StageConfig, stage: StageName) -> str:
    return cfg.model or DEFAULT_MODELS[stage]


def _next_stage(stage: StageName) -> StageName | None:
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
    """Önceki aşamaların en son çıktılarını topla, pipeline_id'yi ekle."""
    context: dict[str, Any] = {"idea_text": pipeline.idea_text, "pipeline_id": pipeline.id}
    logs = (
        db.query(PipelineLog)
        .filter(PipelineLog.pipeline_id == pipeline.id)
        .order_by(PipelineLog.created_at.asc())
        .all()
    )
    latest_by_stage = {}
    for log in logs:
        latest_by_stage[log.stage] = log
    for stage, log in latest_by_stage.items():
        context[f"{stage.value}_report"] = log.full_output
    return context


def _pending_message_for_stage(db: Session, pipeline_id: str, stage: StageName):
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


def _latest_log(db: Session, pipeline_id: str, stage: StageName) -> PipelineLog | None:
    """Bir aşamanın en son üretilen log'u (contract karşılaştırması için)."""
    return (
        db.query(PipelineLog)
        .filter(PipelineLog.pipeline_id == pipeline_id, PipelineLog.stage == stage)
        .order_by(PipelineLog.created_at.desc(), PipelineLog.revision_round.desc())
        .first()
    )


def _contract_violations(db: Session, pipeline: Pipeline) -> list[str]:
    """Onaylanmış aşamaların çıktısı sonradan değişmiş mi? (mevcut aşama hariç)

    Onaylı bir aşamayı bilerek rerun etmek serbesttir; ama rerun sonrası o aşama
    upstream'e dönüşünce hash tutmaz ve yeniden onay ister.
    """
    violations: list[str] = []
    contracts = (
        db.query(PipelineContract)
        .filter(PipelineContract.pipeline_id == pipeline.id)
        .all()
    )
    for contract in contracts:
        if contract.stage == pipeline.current_stage:
            continue
        latest = _latest_log(db, pipeline.id, contract.stage)
        if latest is None:
            violations.append(f"{contract.stage.value}: onaylı çıktı kaydı bulunamadı")
        elif content_hash(latest.full_output) != contract.content_hash:
            violations.append(
                f"{contract.stage.value}: onaylanan çıktı değişmiş — yeniden onay gerekli"
            )
    return violations


def _snapshot_contract(db: Session, pipeline: Pipeline, stage: StageName) -> None:
    """Onaylanan aşamanın en son çıktısını contract olarak kaydeder/günceller."""
    latest = _latest_log(db, pipeline.id, stage)
    if latest is None:
        return
    contract = (
        db.query(PipelineContract)
        .filter(PipelineContract.pipeline_id == pipeline.id, PipelineContract.stage == stage)
        .first()
    )
    if contract is None:
        contract = PipelineContract(pipeline_id=pipeline.id, stage=stage)
        db.add(contract)
    contract.source_log_id = latest.id
    contract.content_hash = content_hash(latest.full_output)
    contract.content = latest.full_output


def _planning_scope_patterns(db: Session, pipeline: Pipeline) -> list[str]:
    """Onaylı plan contract'ından coding kapsam desenlerini okur."""
    contract = (
        db.query(PipelineContract)
        .filter(
            PipelineContract.pipeline_id == pipeline.id,
            PipelineContract.stage == StageName.planning,
        )
        .first()
    )
    if contract and isinstance(contract.content, dict):
        patterns = contract.content.get("scope_patterns", [])
        if isinstance(patterns, list):
            return [str(p) for p in patterns]
    return []


def _coding_gate_violations(db: Session, pipeline: Pipeline, files: list) -> list[str]:
    """Coding çıktısı için placeholder + kapsam ihlallerini döner."""
    violations = scan_placeholders(files)
    paths = [str(f.get("path", "")) for f in files if isinstance(f, dict)]
    violations += [
        f"kapsam dışı dosya: {path}"
        for path in out_of_scope_files(paths, _planning_scope_patterns(db, pipeline))
    ]
    return violations


def _block(db: Session, pipeline: Pipeline, stage: StageName, violations: list[str]) -> Pipeline:
    """Kapı ihlali: ajanı ilerletme, blocking mesaj aç, pipeline'ı durdur.

    Durum `escalated` yapılır; kullanıcı `approve` ile bilinçli olarak override
    edebilir (insan son karar mercisi) veya rerun ile düzeltir.
    """
    db.add(AgentMessage(
        pipeline_id=pipeline.id,
        from_agent="gate",
        to_agent=f"{stage.value}_agent",
        message_type=MessageType.correction_request,
        severity=MessageSeverity.blocking,
        content="KAPI İHLALİ:\n" + "\n".join(f"- {v}" for v in violations),
        stage_reference=stage,
    ))
    pipeline.status = PipelineStatus.escalated
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return pipeline


def run_stage(db: Session, pipeline: Pipeline) -> Pipeline:
    stage = pipeline.current_stage

    contract_violations = _contract_violations(db, pipeline)
    if contract_violations:
        return _block(db, pipeline, stage, contract_violations)

    cfg = _get_stage_config(db, pipeline.id, stage)

    if not cfg.enabled:
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

    prior_rounds = (
        db.query(PipelineLog)
        .filter(PipelineLog.pipeline_id == pipeline.id, PipelineLog.stage == stage)
        .count()
    )

    pending = _pending_message_for_stage(db, pipeline.id, stage)
    revision_note = pending.content if pending else None

    result = agent_fn(context, revision_note=revision_note, model=model)

    # Kodlama: kapılar (placeholder + kapsam) geçmeden dosyalar diske yazılmaz.
    gate_violations: list[str] = []
    if stage == StageName.coding and isinstance(result.get("full_output"), dict):
        files = result["full_output"].get("files", []) or []
        if files:
            gate_violations = _coding_gate_violations(db, pipeline, files)
            if gate_violations:
                result["summary"] += f" (KAPI: {len(gate_violations)} ihlal — dosyalar yazılmadı)"
            else:
                try:
                    write_files_to_workspace(pipeline.id, files)
                except Exception as e:
                    result["summary"] += f" (Uyarı: Dosyalar diske yazılamadı: {e})"

    log = PipelineLog(
        pipeline_id=pipeline.id,
        stage=stage,
        agent=f"{stage.value}_agent",
        summary=result["summary"],
        full_output=result["full_output"],
        model=result.get("model_used") or model,
        revision_round=prior_rounds,
    )
    db.add(log)
    db.flush()

    if pending:
        pending.status = MessageStatus.processed
        pending.resolved_log_id = log.id
        db.add(pending)

        if prior_rounds + 1 >= cfg.max_revision_rounds:
            pipeline.status = PipelineStatus.escalated
            db.add(pipeline)
            db.commit()
            db.refresh(pipeline)
            return pipeline

    question_text = result.get("question")
    if question_text:
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

    if gate_violations:
        return _block(db, pipeline, stage, gate_violations)

    if cfg.requires_approval:
        pipeline.status = PipelineStatus.waiting_approval
        db.add(pipeline)
        db.commit()
        db.refresh(pipeline)
        return pipeline

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
    """Kullanıcı mevcut aşamayı onayladı -> contract snapshot -> sıradaki aşamaya geç."""
    if pipeline.status not in (PipelineStatus.waiting_approval, PipelineStatus.escalated):
        raise ValueError("Pipeline onay bekleyen durumda değil.")
    _snapshot_contract(db, pipeline, pipeline.current_stage)
    db.commit()
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
    """Mevcut aşamayı tekrar çalıştır."""
    pipeline.status = PipelineStatus.running
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return run_stage(db, pipeline)


def answer_question(db: Session, pipeline: Pipeline, question_id: str, answer_text: str) -> Pipeline:
    """Bekleyen bir soruyu yanıtla."""
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
