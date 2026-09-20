"""
Çalışan bir 'uvicorn main:app' sunucusuna bağlanır, senden bir fikir alır,
pipeline'ı başlatır ve her aşamanın raporunu okunabilir şekilde ekrana basar.

Kullanım (sunucu ayrı bir terminalde ÇALIŞIYOR olmalı):
    python run_demo.py
"""
import json
import sys

import httpx

BASE_URL = "http://localhost:8000"


def _print_log(log: dict) -> None:
    print(f"\n{'─' * 60}")
    print(f"[{log['stage'].upper()}] (deneme #{log['revision_round'] + 1}) - {log['agent']}")
    print(f"{'─' * 60}")
    print(log["summary"])
    print()
    print(json.dumps(log["full_output"], ensure_ascii=False, indent=2))


def _latest_log_for_current_stage(client: httpx.Client, pipeline_id: str, stage: str) -> dict:
    logs = client.get(f"{BASE_URL}/pipelines/{pipeline_id}/logs").json()
    stage_logs = [l for l in logs if l["stage"] == stage]
    return stage_logs[-1]


def _handle_waiting_response(client: httpx.Client, pipeline: dict) -> dict:
    messages = client.get(f"{BASE_URL}/pipelines/{pipeline['id']}/messages").json()
    question = next(
        m for m in reversed(messages)
        if m["message_type"] == "question" and m["status"] == "pending"
    )
    print(f"\n🤔 Ajan bir soru soruyor ({question['from_agent']}):")
    print(f"   {question['content']}")
    answer = input("\nCevabın: ").strip()
    resp = client.post(
        f"{BASE_URL}/pipelines/{pipeline['id']}/messages/{question['id']}/answer",
        json={"answer": answer},
    )
    resp.raise_for_status()
    return resp.json()


def _save_report(client: httpx.Client, pipeline_id: str) -> None:
    resp = client.get(f"{BASE_URL}/pipelines/{pipeline_id}/report")
    resp.raise_for_status()
    filename = f"pipeline_{pipeline_id}.md"
    with open(filename, "wb") as f:
        f.write(resp.content)
    print(f"\n📄 Rapor kaydedildi: {filename}")


def main() -> None:
    idea = input("Değerlendirilecek fikri yaz: ").strip()
    if not idea:
        print("Boş fikir girildi, çıkılıyor.")
        sys.exit(1)

    with httpx.Client(timeout=120.0) as client:
        print("\nPipeline başlatılıyor (research_agent çalışıyor, biraz sürebilir)...")
        try:
            resp = client.post(f"{BASE_URL}/pipelines", json={"idea_text": idea})
            resp.raise_for_status()
        except httpx.ConnectError:
            print(f"\n❌ {BASE_URL} adresine bağlanılamadı. Sunucu (uvicorn main:app) çalışıyor mu?")
            sys.exit(1)
        except httpx.HTTPStatusError as e:
            print(f"\n❌ Hata: {e.response.status_code} - {e.response.text}")
            sys.exit(1)

        pipeline = resp.json()

        while pipeline["status"] not in ("completed", "failed"):
            status = pipeline["status"]
            stage = pipeline["current_stage"]

            if status == "waiting_response":
                pipeline = _handle_waiting_response(client, pipeline)
                continue

            log = _latest_log_for_current_stage(client, pipeline["id"], stage)
            _print_log(log)

            if status == "escalated":
                print(f"\n⚠️  '{stage}' aşaması revizyon limitine ulaştı (eskale oldu).")
                choice = input("Yine de onaylayıp ilerlet mi (e/h)? ").strip().lower()
                if choice != "e":
                    _save_report(client, pipeline["id"])
                    print("Duraklatıldı. Pipeline ID:", pipeline["id"])
                    sys.exit(0)
            else:
                input(f"\n[{stage}] aşamasını onaylamak için Enter'a bas...")

            resp = client.post(f"{BASE_URL}/pipelines/{pipeline['id']}/approve")
            resp.raise_for_status()
            pipeline = resp.json()

        print(f"\n✅ Pipeline tamamlandı! Durum: {pipeline['status']}")
        print(f"Pipeline ID: {pipeline['id']}")
        _save_report(client, pipeline["id"])


if __name__ == "__main__":
    main()
