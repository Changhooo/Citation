from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import ROOT, get_settings
from app.db import init_db
from core import repository
from core.author_intel import screen_authors_for_task
from core.citation_extract import extract_contexts_for_task
from core.exporter import export_csv, export_json, export_zip
from core.pdf_store import download_pdf_url, downloaded_pdf_map, save_uploaded_pdf
from core.selection import build_candidate_c, get_candidate_c
from core.scholar import collect_citing_papers, normalize_mirror, search_candidates


app = FastAPI(title="CitationClaw")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tasks": repository.list_tasks(),
            "default_mirror": settings.default_scholar_mirror,
        },
    )


@app.post("/tasks")
def create_task(query: str = Form(...), scholar_mirror: str = Form(...)) -> RedirectResponse:
    task = repository.create_task(query=query, scholar_mirror=normalize_mirror(scholar_mirror))
    return RedirectResponse(f"/tasks/{task['id']}", status_code=303)


@app.post("/tasks/{task_id}/mirror")
def update_mirror(task_id: str, scholar_mirror: str = Form(...)) -> RedirectResponse:
    mirror = normalize_mirror(scholar_mirror)
    repository.update_task(
        task_id,
        scholar_mirror=mirror,
        target_result_id="",
        cited_by_count=0,
        cited_by_url="",
        current_page=0,
        status="created",
        needs_user_action=0,
        message="已切换镜像。cited-by ID 会随镜像变化，请重新搜索并确认论文 A。",
    )
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: str) -> HTMLResponse:
    try:
        task = repository.get_task(task_id)
    except KeyError:
        raise HTTPException(404, "Task not found")
    return templates.TemplateResponse(
        "task.html",
        {
            "request": request,
            "task": task,
            "candidates": repository.list_results(task_id, "candidate_a"),
            "citations": repository.list_results(task_id, "citation_b"),
            "candidate_c": get_candidate_c(task_id),
            "candidate_c_reasons": repository.get_task_settings(task_id).get("candidate_c_reasons", {}),
            "author_evidence": repository.list_author_evidence(task_id),
            "contexts": repository.list_contexts(task_id),
            "pdf_assets": downloaded_pdf_map(task_id),
        },
    )


@app.post("/tasks/{task_id}/search")
def run_search(task_id: str) -> RedirectResponse:
    search_candidates(task_id, visible=True)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/confirm")
def confirm(task_id: str, result_id: str = Form(...)) -> RedirectResponse:
    repository.confirm_target(task_id, result_id)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/override-cites")
def override_cites(task_id: str, cites_id: str = Form(...), cited_by_count: int = Form(default=0)) -> RedirectResponse:
    task = repository.get_task(task_id)
    mirror = normalize_mirror(task["scholar_mirror"]).rstrip("/")
    cited_by_url = f"{mirror}/scholar?cites={cites_id.strip()}"
    repository.update_task(
        task_id,
        cited_by_url=cited_by_url,
        cited_by_count=cited_by_count,
        current_page=0,
        status="paper_confirmed",
        needs_user_action=0,
        message=f"已手动修正 cited-by: {cited_by_count} / {cites_id.strip()}",
    )
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/collect-b")
def collect_b(task_id: str, confirm_large: str = Form(default="")) -> RedirectResponse:
    collect_citing_papers(task_id, confirm_large=confirm_large == "yes", visible=True)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.get("/tasks/{task_id}/pdf/{result_id}")
def view_pdf(task_id: str, result_id: str) -> Response:
    try:
        result = repository.get_result(task_id, result_id)
    except KeyError:
        raise HTTPException(404, "Result not found")
    asset = repository.get_pdf_asset(task_id, result_id)
    path = Path(asset["path"]) if asset and asset.get("path") else None
    if not path or not path.exists():
        path = download_pdf_url(task_id, result)
    if path and path.exists():
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=path.name,
            headers={"Content-Disposition": f'inline; filename="{path.name}"'},
        )
    if result.get("pdf_url"):
        return RedirectResponse(result["pdf_url"], status_code=302)
    raise HTTPException(404, "PDF not found")


@app.post("/tasks/{task_id}/upload-pdfs")
async def upload_pdfs(task_id: str, files: List[UploadFile] = File(...)) -> RedirectResponse:
    matched = 0
    unmatched = 0
    not_pdf = 0
    examples = []
    for upload in files:
        data = await upload.read()
        result = save_uploaded_pdf(task_id, upload.filename or "uploaded.pdf", data)
        if result["status"] == "matched":
            matched += 1
            if len(examples) < 3:
                examples.append(f"{result['filename']} -> {result.get('title', '')} ({result['score']:.2f})")
        elif result["status"] == "unmatched":
            unmatched += 1
        else:
            not_pdf += 1
    detail = "；".join(examples)
    repository.update_task(
        task_id,
        message=f"PDF 上传完成：自动匹配 {matched} 个，待人工确认 {unmatched} 个，非 PDF/无效 {not_pdf} 个。{detail}",
    )
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/build-c")
def build_c(task_id: str) -> RedirectResponse:
    build_candidate_c(task_id)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/screen-authors")
def screen_authors(task_id: str) -> RedirectResponse:
    screen_authors_for_task(task_id)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/extract-contexts")
def extract_contexts(task_id: str) -> RedirectResponse:
    extract_contexts_for_task(task_id)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.get("/tasks/{task_id}/export/json")
def export_json_route(task_id: str) -> Response:
    return Response(export_json(task_id), media_type="application/json")


@app.get("/tasks/{task_id}/export/csv")
def export_csv_route(task_id: str) -> PlainTextResponse:
    return PlainTextResponse(export_csv(task_id), media_type="text/csv")


@app.get("/tasks/{task_id}/export/zip")
def export_zip_route(task_id: str) -> FileResponse:
    path = export_zip(task_id)
    return FileResponse(path, filename=path.name, media_type="application/zip")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
