from dotenv import load_dotenv
load_dotenv()  # .env dosyasını yükler - database/agents'taki os.environ okumalarından ÖNCE çalışmalı

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Pipeline, PipelineLog, AgentMessage, StageConfig
from schemas import (
    PipelineCreate, PipelineOut, LogOut, MessageCreate, MessageOut,
    AnswerCreate, StageConfigUpdate,
)
import orchestrator
from reporting import render_markdown

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fikirden Pazarlamaya Ajan Hattı")


@app.post("/pipelines", response_model=PipelineOut)
def create_pipeline(payload: PipelineCreate, db: Session = Depends(get_db)):
    """Yeni bir fikirle pipeline başlat ve ilk aşamayı (research) hemen çalıştır."""
    pipeline = Pipeline(idea_text=payload.idea_text)
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    pipeline = orchestrator.run_stage(db, pipeline)
    return pipeline


@app.get("/pipelines/{pipeline_id}", response_model=PipelineOut)
def get_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline bulunamadı")
    return pipeline


@app.get("/pipelines/{pipeline_id}/logs", response_model=list[LogOut])
def get_logs(pipeline_id: str, db: Session = Depends(get_db)):
    """Her aşamanın raporu - onay durumundan bağımsız, her zaman erişilebilir."""
    return (
        db.query(PipelineLog)
        .filter(PipelineLog.pipeline_id == pipeline_id)
        .order_by(PipelineLog.created_at.asc())
        .all()
    )


@app.get("/pipelines/{pipeline_id}/report")
def get_report(pipeline_id: str, db: Session = Depends(get_db)):
    """Tüm aşama raporlarını tek bir okunaklı Markdown dokümanı olarak döndürür."""
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline bulunamadı")
    logs = (
        db.query(PipelineLog)
        .filter(PipelineLog.pipeline_id == pipeline_id)
        .order_by(PipelineLog.created_at.asc())
        .all()
    )
    md = render_markdown(PipelineOut.model_validate(pipeline), [LogOut.model_validate(l) for l in logs])
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="pipeline_{pipeline_id}.md"'},
    )


@app.post("/pipelines/{pipeline_id}/approve", response_model=PipelineOut)
def approve(pipeline_id: str, db: Session = Depends(get_db)):
    """Kullanıcı mevcut aşamayı onaylar -> sıradaki aşama otomatik çalışır."""
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline bulunamadı")
    try:
        return orchestrator.approve_stage(db, pipeline)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/pipelines/{pipeline_id}/messages", response_model=MessageOut)
def send_message(pipeline_id: str, payload: MessageCreate, db: Session = Depends(get_db)):
    """
    Bir ajandan (veya kullanıcıdan) başka bir ajana düzeltme/öneri gönder.
    Not: bu sadece mesajı kaydeder. Hedeflenen aşamayı gerçekten tekrar
    çalıştırmak için /rerun endpoint'ini çağırman gerekir (otomatik akışta
    bu, o aşama tekrar tetiklendiğinde zaten kontrol edilir).
    """
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline bulunamadı")
    return orchestrator.submit_message(db, pipeline_id, payload)


@app.get("/pipelines/{pipeline_id}/messages", response_model=list[MessageOut])
def list_messages(pipeline_id: str, db: Session = Depends(get_db)):
    """Tüm ajanlar arası/kullanıcı mesajları - bekleyen sorular dahil."""
    return (
        db.query(AgentMessage)
        .filter(AgentMessage.pipeline_id == pipeline_id)
        .order_by(AgentMessage.created_at.asc())
        .all()
    )


@app.post("/pipelines/{pipeline_id}/messages/{message_id}/answer", response_model=PipelineOut)
def answer_question(
    pipeline_id: str, message_id: str, payload: AnswerCreate, db: Session = Depends(get_db)
):
    """
    Bir ajanın (status=waiting_response iken) sorduğu soruyu cevapla.
    Cevap otomatik olarak ilgili aşamanın revizyon akışına girer ve
    aşama kaldığı yerden devam eder.
    """
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline bulunamadı")
    try:
        return orchestrator.answer_question(db, pipeline, message_id, payload.answer)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/pipelines/{pipeline_id}/rerun", response_model=PipelineOut)
def rerun(pipeline_id: str, db: Session = Depends(get_db)):
    """Mevcut aşamayı (bekleyen düzeltme mesajlarını dikkate alarak) tekrar çalıştır."""
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline bulunamadı")
    return orchestrator.rerun_current_stage(db, pipeline)


@app.put("/stage-config")
def set_stage_config(payload: StageConfigUpdate, db: Session = Depends(get_db)):
    """Global varsayılan: hangi aşama onay gerektirsin, kaç revizyon hakkı olsun."""
    cfg = (
        db.query(StageConfig)
        .filter(StageConfig.pipeline_id.is_(None), StageConfig.stage == payload.stage)
        .first()
    )
    if not cfg:
        cfg = StageConfig(pipeline_id=None, stage=payload.stage)
    cfg.requires_approval = payload.requires_approval
    cfg.max_revision_rounds = payload.max_revision_rounds
    cfg.model = payload.model
    cfg.enabled = payload.enabled
    db.add(cfg)
    db.commit()
    return {"ok": True}
