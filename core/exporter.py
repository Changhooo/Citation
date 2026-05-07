from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from app.config import get_settings
from core import repository
from core.selection import get_candidate_c


def snapshot(task_id: str) -> dict:
    return {
        "task": repository.get_task(task_id),
        "candidates": repository.list_results(task_id, "candidate_a"),
        "citations": repository.list_results(task_id, "citation_b"),
        "candidate_c": get_candidate_c(task_id),
        "candidate_c_reasons": repository.get_task_settings(task_id).get("candidate_c_reasons", {}),
        "pdf_assets": repository.list_pdf_assets(task_id),
        "contexts": repository.list_contexts(task_id),
        "author_evidence": repository.list_author_evidence(task_id),
    }


def export_json(task_id: str) -> str:
    return json.dumps(snapshot(task_id), ensure_ascii=False, indent=2)


def export_csv(task_id: str) -> str:
    data = snapshot(task_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["role", "title", "authors_text", "year", "cited_by_count", "pdf_url", "result_url"])
    for role in ["candidates", "citations", "candidate_c"]:
        for item in data[role]:
            writer.writerow([item["role"], item["title"], item["authors_text"], item["year"], item["cited_by_count"], item["pdf_url"], item["result_url"]])
    writer.writerow([])
    writer.writerow(["author_name", "title_type", "confidence", "status", "evidence_url", "evidence_snippet"])
    for ev in data["author_evidence"]:
        writer.writerow([ev["author_name"], ev["title_type"], ev["confidence"], ev["status"], ev["evidence_url"], ev["evidence_snippet"]])
    writer.writerow([])
    writer.writerow(["context_result_id", "page", "sentiment", "confidence", "evidence", "reason_zh", "material_zh"])
    for ctx in data["contexts"]:
        evidence = " ".join([ctx.get("before_sentence") or "", ctx.get("hit_sentence") or "", ctx.get("after_sentence") or ""]).strip()
        writer.writerow([ctx["result_id"], ctx["page"], ctx["sentiment"], ctx["confidence"], evidence, ctx["reason_zh"], ctx["material_zh"]])
    return out.getvalue()


def export_zip(task_id: str) -> Path:
    settings = get_settings()
    export_dir = settings.data_path / "tasks" / task_id / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"{task_id}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("snapshot.json", export_json(task_id))
        zf.writestr("papers.csv", export_csv(task_id))
        for asset in repository.list_pdf_assets(task_id):
            path = Path(asset.get("path") or "")
            if asset.get("status") == "downloaded" and path.exists():
                zf.write(path, f"pdfs/{path.name}")
    return path
