from __future__ import annotations

import re
import uuid
from pathlib import Path

from PyPDF2 import PdfReader

from core import repository
from core.pdf_store import downloaded_pdf_map
from core.selection import get_candidate_c


POSITIVE_WORDS = [
    "outperform",
    "effective",
    "efficient",
    "improve",
    "superior",
    "robust",
    "state-of-the-art",
    "promising",
    "benefit",
    "advantage",
]
NEGATIVE_WORDS = [
    "limitation",
    "limited",
    "fail",
    "failure",
    "problem",
    "challenge",
    "weakness",
    "however",
    "but",
    "expensive",
    "inefficient",
]


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def loose_text(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"(\w)-\s+(\w)", r"\1\2", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return normalize(value)


def title_keywords(target_title: str) -> list[str]:
    words = [word for word in re.findall(r"[a-z0-9]+", target_title.lower()) if len(word) >= 4]
    return list(dict.fromkeys(words))


def title_entry_score(entry_text: str, keywords: list[str]) -> int:
    body = loose_text(entry_text[:1600])
    return sum(1 for word in keywords if word in body)


def is_target_reference_entry(entry_text: str, keywords: list[str]) -> bool:
    if not keywords:
        return False
    body = loose_text(entry_text[:1600])
    score = title_entry_score(entry_text, keywords)
    required = max(4, min(len(keywords) - 1, 7))
    phrase_hits = [
        "multiple instance graph learning" in body,
        "weakly supervised remote sensing object detection" in body,
        "multiple instance" in body and "remote sensing object detection" in body,
    ]
    return score >= required or any(phrase_hits)


def extract_pdf_pages(path: str) -> list[str]:
    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        try:
            pages.append(normalize(page.extract_text() or ""))
        except Exception:
            pages.append("")
    return pages


def split_sentences(text: str) -> list[str]:
    text = normalize(text)
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])", text) if part.strip()]


def reference_start_page(pages: list[str]) -> int | None:
    for index, page_text in enumerate(pages, start=1):
        if re.search(r"\bReferences\b|\bREFERENCES\b", page_text):
            return index
    return None


def find_reference_markers(full_text: str, target_title: str) -> list[str]:
    keywords = title_keywords(target_title)
    markers: list[str] = []
    if not keywords:
        return markers

    bracket_entries = re.finditer(r"\[(\d{1,3})\](.*?)(?=\[\d{1,3}\]|$)", full_text, flags=re.S)
    for entry in bracket_entries:
        if is_target_reference_entry(entry.group(2), keywords):
            markers.append(f"[{entry.group(1)}]")

    numbered_entries = re.finditer(r"(?:^|\s)(\d{1,3})\.?\s+([A-Z][^[]*?)(?=(?:\s\d{1,3}\.?\s+[A-Z])|$)", full_text, flags=re.S)
    for entry in numbered_entries:
        if is_target_reference_entry(entry.group(2), keywords):
            markers.append(f"[{entry.group(1)}]")
    return list(dict.fromkeys(markers))


def classify_stance(sentence: str, before: str, after: str) -> tuple[str, float, str]:
    context = f"{before} {sentence} {after}".lower()
    pos = sum(1 for word in POSITIVE_WORDS if word in context)
    neg = sum(1 for word in NEGATIVE_WORDS if word in context)
    if pos > neg:
        return "positive", min(0.85, 0.55 + 0.1 * pos), "上下文出现改进、有效、优于等正向评价词，规则初判为正面引用。"
    if neg > pos:
        return "negative", min(0.85, 0.55 + 0.1 * neg), "上下文出现限制、失败、问题、however/but 等转折或负向评价词，规则初判为负面引用。"
    return "neutral", 0.45, "上下文没有明显正负评价词，按规则归为中性引用。"


def context_to_material(title: str, context: dict) -> str:
    sentiment_zh = {"positive": "正面", "negative": "负面", "neutral": "中性"}.get(context["sentiment"], "中性")
    evidence = normalize(" ".join([context.get("before_sentence") or "", context["hit_sentence"], context.get("after_sentence") or ""]))
    return f"论文《{title}》在第 {context.get('page') or '?'} 页以{sentiment_zh}方式引用目标论文。证据原文：\"{evidence}\" 理由：{context.get('reason_zh') or ''}"


def extract_contexts_for_task(task_id: str, max_contexts_per_pdf: int = 8) -> dict[str, int]:
    task = repository.get_task(task_id)
    c_items = get_candidate_c(task_id)
    assets = downloaded_pdf_map(task_id)
    stats = {"c_total": len(c_items), "with_pdf": 0, "contexts": 0, "missing_pdf": 0}
    repository.clear_contexts(task_id)

    for item in c_items:
        asset = assets.get(item["id"])
        if not asset or not Path(asset.get("path") or "").exists():
            stats["missing_pdf"] += 1
            continue
        stats["with_pdf"] += 1
        pages = extract_pdf_pages(asset["path"])
        full_text = "\n".join(pages)
        refs_from = reference_start_page(pages)
        markers = find_reference_markers(full_text, task["query"])
        if not markers:
            markers = [task["query"][:40]]

        found = 0
        for page_number, page_text in enumerate(pages, start=1):
            if refs_from and page_number >= refs_from:
                continue
            sentences = split_sentences(page_text)
            for index, sentence in enumerate(sentences):
                if not any(marker in sentence for marker in markers):
                    continue
                if re.fullmatch(r"\[\d{1,3}\]\s+[A-Z]\.?.*", sentence.strip()):
                    continue
                if task["query"].lower() in sentence.lower() and page_number > max(1, len(pages) - 4):
                    continue
                before = sentences[index - 1] if index > 0 else ""
                after = sentences[index + 1] if index + 1 < len(sentences) else ""
                sentiment, confidence, reason = classify_stance(sentence, before, after)
                context = {
                    "id": uuid.uuid5(uuid.NAMESPACE_URL, f"{task_id}:{item['id']}:{page_number}:{sentence[:100]}").hex,
                    "page": page_number,
                    "marker": ", ".join(markers),
                    "before_sentence": before,
                    "hit_sentence": sentence,
                    "after_sentence": after,
                    "sentiment": sentiment,
                    "confidence": confidence,
                    "reason_zh": reason,
                    "review_status": "auto",
                }
                context["material_zh"] = context_to_material(item["title"], context)
                repository.upsert_context(task_id, item["id"], context)
                stats["contexts"] += 1
                found += 1
                if found >= max_contexts_per_pdf:
                    break
            if found >= max_contexts_per_pdf:
                break

    repository.update_task(
        task_id,
        status="contexts_extracted",
        message=f"引用上下文抽取完成：C 共 {stats['c_total']} 篇，本地 PDF {stats['with_pdf']} 篇，抽到上下文 {stats['contexts']} 条，缺 PDF {stats['missing_pdf']} 篇。",
    )
    return stats
