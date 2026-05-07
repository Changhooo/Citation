from __future__ import annotations

import re
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

from app.config import get_settings
from core import repository


def safe_filename(value: str, max_length: int = 120) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", " ", value or "paper")
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return (name or "paper")[:max_length]


def match_text(value: str) -> str:
    value = Path(value or "").name
    value = re.sub(r"\.pdf$", "", value, flags=re.I)
    value = re.sub(r"__[0-9a-f]{8}$", "", value, flags=re.I)
    value = re.sub(r"[_\-]+", " ", value)
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def pdf_path_for(task_id: str, result_id: str, title: str) -> Path:
    directory = get_settings().data_path / "tasks" / task_id / "pdfs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{safe_filename(title)}__{result_id[:8]}.pdf"


def looks_like_pdf(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 100:
        return False
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def looks_like_pdf_bytes(data: bytes) -> bool:
    return b"%PDF-" in data[:2048]


def title_match_score(filename: str, title: str) -> float:
    left = match_text(filename)
    right = match_text(title)
    if not left or not right:
        return 0.0
    ratio = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    subset = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return max(ratio, 0.55 * overlap + 0.45 * subset)


def best_pdf_match(task_id: str, filename: str) -> tuple[dict | None, float]:
    candidates = repository.list_results(task_id, "citation_b") + repository.list_results(task_id, "candidate_a")
    best: dict | None = None
    best_score = 0.0
    for result in candidates:
        score = title_match_score(filename, result.get("title") or "")
        if score > best_score:
            best = result
            best_score = score
    return best, best_score


def download_pdf_url(task_id: str, result: dict, timeout: int = 45) -> Path | None:
    url = result.get("pdf_url") or ""
    result_id = result["id"]
    if not url:
        repository.upsert_pdf_asset(task_id, result_id, "auto", url, None, "missing")
        return None

    path = pdf_path_for(task_id, result_id, result.get("title") or "paper")
    if looks_like_pdf(path):
        repository.upsert_pdf_asset(task_id, result_id, "auto", url, str(path), "downloaded", 1.0)
        return path

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CitationClaw local research tool",
            "Accept": "application/pdf,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("content-type", "").lower()
            data = response.read()
        if b"%PDF-" not in data[:2048] and "pdf" not in content_type:
            repository.upsert_pdf_asset(task_id, result_id, "auto", url, None, "not_pdf")
            return None
        path.write_bytes(data)
        repository.upsert_pdf_asset(task_id, result_id, "auto", url, str(path), "downloaded", 1.0)
        return path
    except Exception as exc:
        repository.upsert_pdf_asset(task_id, result_id, "auto", url, None, f"failed: {exc}")
        return None


def save_uploaded_pdf(task_id: str, filename: str, data: bytes, threshold: float = 0.72) -> dict:
    if not looks_like_pdf_bytes(data):
        return {"filename": filename, "status": "not_pdf", "score": 0.0, "result_id": ""}

    result, score = best_pdf_match(task_id, filename)
    if result and score >= threshold:
        path = pdf_path_for(task_id, result["id"], result.get("title") or filename)
        path.write_bytes(data)
        repository.upsert_pdf_asset(task_id, result["id"], "upload", "", str(path), "downloaded", score)
        return {
            "filename": filename,
            "status": "matched",
            "score": score,
            "result_id": result["id"],
            "title": result.get("title") or "",
            "path": str(path),
        }

    upload_dir = get_settings().data_path / "tasks" / task_id / "uploads" / "unmatched"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / safe_filename(Path(filename).name, 160)
    if path.suffix.lower() != ".pdf":
        path = path.with_suffix(".pdf")
    path.write_bytes(data)
    return {
        "filename": filename,
        "status": "unmatched",
        "score": score,
        "result_id": result["id"] if result else "",
        "title": result.get("title") if result else "",
        "path": str(path),
    }


def downloaded_pdf_map(task_id: str) -> dict[str, dict]:
    return {asset["result_id"]: asset for asset in repository.list_pdf_assets(task_id) if asset.get("status") == "downloaded"}


def download_pdfs_for_results(task_id: str, results: list[dict], timeout: int = 45) -> dict[str, int]:
    downloaded_map = downloaded_pdf_map(task_id)
    stats = {"total": 0, "already": 0, "downloaded": 0, "failed": 0, "missing": 0}
    for result in results:
        if not result.get("pdf_url"):
            stats["missing"] += 1
            continue
        stats["total"] += 1
        if result["id"] in downloaded_map:
            stats["already"] += 1
            continue
        path = download_pdf_url(task_id, result, timeout=timeout)
        if path:
            stats["downloaded"] += 1
        else:
            stats["failed"] += 1
    return stats
