from __future__ import annotations

import hashlib
import random
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import get_settings
from core import repository
from core.pdf_store import download_pdf_url, download_pdfs_for_results


CAPTCHA_PATTERNS = [
    "unusual traffic",
    "captcha",
    "not a robot",
    "请输入验证码",
    "人机验证",
    "so busy",
    "系统检测到你的访问有些问题",
    "访问本站请不要频繁刷新页面",
    "严格的访问控制",
    "点击刷新重试",
    "访问有些问题",
    "安全验证",
    "verify_gate",
    "请点击图片中的",
    "完成以下验证",
    "提交验证",
    "è®¿é—®æœ¬ç«™è¯·ä¸è¦é¢‘ç¹åˆ·æ–°é¡µé¢",
    "ä¸¥æ ¼çš„è®¿é—®æŽ§åˆ¶",
]


@dataclass
class ScholarRunResult:
    ok: bool
    count: int = 0
    message: str = ""
    needs_user_action: bool = False


def stable_result_id(task_id: str, role: str, title: str, position: int = 0) -> str:
    raw = f"{task_id}:{role}:{title}:{position}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def parse_year(text: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", text or "")
    return int(match.group(0)) if match else None


def parse_count(text: str) -> int:
    match = re.search(r"(\d+)", text or "")
    return int(match.group(1)) if match else 0


def looks_abnormal(text: str) -> bool:
    lower = text.lower()
    return any(pattern in lower for pattern in CAPTCHA_PATTERNS)


def page_looks_abnormal(page, body_text: str) -> bool:
    return looks_abnormal(body_text) or "verify_gate" in page.url


def wait_for_manual_clear(page, visible: bool, timeout_seconds: int = 300) -> bool:
    if not visible:
        return False
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        body_text = page.locator("body").inner_text(timeout=5000)
        if not page_looks_abnormal(page, body_text):
            return True
        time.sleep(3)
    return False


def abnormal_message(page_url: str) -> str:
    return f"Scholar 镜像进入安全验证/访问控制页面：{page_url}。请在弹出的可见浏览器中完成验证，或换镜像后重新搜索。"


def normalize_mirror(mirror: str) -> str:
    mirror = (mirror or "").strip()
    mirror = re.sub(r"/(scholar|search).*$", "", mirror)
    return mirror.rstrip("/") + "/"


def scholar_search_url(mirror: str, query: str) -> str:
    return urljoin(normalize_mirror(mirror), f"scholar?q={quote_plus(query)}")


def scholar_cites_url(base_url: str, onclick: str | None, href: str | None = None) -> str:
    href = href or ""
    if "cites=" in href:
        return urljoin(base_url, href)
    match = re.search(r"scholar_cites\(['\"]?(\d+)['\"]?\)", onclick or "")
    if match:
        return urljoin(base_url, f"/scholar?cites={match.group(1)}")
    return ""


def is_cited_by_link(text: str, onclick: str | None) -> bool:
    return (
        "scholar_cites" in (onclick or "")
        or "Cited by" in text
        or "被引用" in text
        or "è¢«å¼•ç”¨" in text
    )


def is_usable_pdf_link(href: str, text: str, classes: str | None = None) -> bool:
    href_lower = (href or "").lower()
    text_lower = (text or "").lower()
    class_lower = (classes or "").lower()
    if not href_lower:
        return False
    if "payonline" in href_lower or "sci-hub" in text_lower or "vip_down" in class_lower:
        return False
    return href_lower.endswith(".pdf") or ".pdf" in href_lower or "pdf" in text_lower


def first_text(locator, timeout: int = 2000) -> str:
    if locator.count() == 0:
        return ""
    return locator.first.inner_text(timeout=timeout).strip()


def extract_results(page, task_id: str, role: str, page_number: int = 1) -> list[dict[str, Any]]:
    results = []
    cards = page.locator(".gs_r.gs_or.gs_scl")
    count = cards.count()
    for index in range(count):
        card = cards.nth(index)
        title_node = card.locator("h3.gs_rt")
        title = first_text(title_node)
        if not title:
            continue
        title = re.sub(r"^\[[^\]]+\]\s*", "", title)
        result_url = ""
        link = title_node.locator("a")
        if link.count():
            result_url = link.first.get_attribute("href", timeout=2000) or ""
        meta = first_text(card.locator(".gs_a"))
        snippet = first_text(card.locator(".gs_rs"))
        cited_by_count = 0
        cited_by_url = ""
        links = card.locator(".gs_fl a")
        for j in range(links.count()):
            text = links.nth(j).inner_text(timeout=1000)
            onclick = links.nth(j).get_attribute("onclick", timeout=1000) or ""
            if is_cited_by_link(text, onclick):
                cited_by_count = parse_count(text)
                href = links.nth(j).get_attribute("href", timeout=1000) or ""
                cited_by_url = scholar_cites_url(page.url, onclick, href)
                break
        pdf_url = ""
        side_links = card.locator(".gs_or_ggsm a, .gs_ggs a")
        for j in range(side_links.count()):
            href = side_links.nth(j).get_attribute("href", timeout=1000) or ""
            text = side_links.nth(j).inner_text(timeout=1000).lower()
            classes = side_links.nth(j).get_attribute("class", timeout=1000) or ""
            if is_usable_pdf_link(href, text, classes):
                pdf_url = urljoin(page.url, href)
                break
        item = {
            "id": stable_result_id(task_id, role, title, index),
            "title": title,
            "authors_text": meta,
            "year": parse_year(meta),
            "venue": meta,
            "snippet": snippet,
            "result_url": result_url,
            "pdf_url": pdf_url,
            "cited_by_count": cited_by_count,
            "cited_by_url": cited_by_url,
            "page_number": page_number,
            "position": index + 1,
        }
        results.append(item)
    return results


def demo_candidates(task_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": stable_result_id(task_id, "candidate_a", "CORE: Cooperative Reconstruction for Multi-Agent Perception", 0),
            "title": "CORE: Cooperative Reconstruction for Multi-Agent Perception",
            "authors_text": "Binglu Wang, Lei Zhang, Zhaozhong Wang, Yongqiang Zhao, Tianfei Zhou - ICCV, 2023",
            "year": 2023,
            "venue": "ICCV 2023",
            "snippet": "CORE is a cooperative reconstruction framework for multi-agent perception.",
            "result_url": "https://openaccess.thecvf.com/content/ICCV2023/html/Wang_CORE_Cooperative_Reconstruction_for_Multi-Agent_Perception_ICCV_2023_paper.html",
            "pdf_url": "https://openaccess.thecvf.com/content/ICCV2023/papers/Wang_CORE_Cooperative_Reconstruction_for_Multi-Agent_Perception_ICCV_2023_paper.pdf",
            "cited_by_count": 73,
            "cited_by_url": "demo://core/cited-by",
            "page_number": 1,
            "position": 1,
        }
    ]


def demo_citing_papers(task_id: str) -> list[dict[str, Any]]:
    titles = [
        ("Communication-Efficient Collaborative Perception via Information Filling with Codebook", 2024, 6),
        ("What Makes Good Collaborative Views? Contrastive Mutual Information Maximization for Multi-Agent Perception", 2024, 3),
        ("UMC: A Unified Bandwidth-efficient and Multi-resolution based Collaborative Perception Framework", 2023, 0),
    ]
    return [
        {
            "id": stable_result_id(task_id, "citation_b", title, i),
            "title": title,
            "authors_text": "Scholar fallback authors",
            "year": year,
            "venue": "arXiv",
            "snippet": "Fallback B seed used when Scholar mirror collection is unavailable.",
            "result_url": "",
            "pdf_url": "",
            "cited_by_count": cites,
            "cited_by_url": "",
            "page_number": 1,
            "position": i + 1,
        }
        for i, (title, year, cites) in enumerate(titles)
    ]


def search_candidates(task_id: str, visible: bool = True) -> ScholarRunResult:
    task = repository.get_task(task_id)
    if task["query"].lower().startswith("demo"):
        for item in demo_candidates(task_id):
            repository.upsert_result(task_id, "candidate_a", item)
        repository.update_task(task_id, status="paper_candidates_found", message="Demo 候选已保存")
        return ScholarRunResult(ok=True, count=1, message="Demo candidates saved")

    url = scholar_search_url(task["scholar_mirror"], task["query"])
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not visible)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            body_text = page.locator("body").inner_text(timeout=5000)
            if page_looks_abnormal(page, body_text):
                if wait_for_manual_clear(page, visible):
                    body_text = page.locator("body").inner_text(timeout=5000)
                else:
                    message = abnormal_message(page.url)
                    repository.update_task(task_id, status="needs_user_action", needs_user_action=1, message=message)
                    browser.close()
                    return ScholarRunResult(ok=False, needs_user_action=True, message=message)
            items = extract_results(page, task_id, "candidate_a", 1)
            for item in items:
                repository.upsert_result(task_id, "candidate_a", item)
                if item.get("pdf_url"):
                    download_pdf_url(task_id, item)
            if items:
                repository.update_task(task_id, status="paper_candidates_found", needs_user_action=0, message=f"找到 {len(items)} 个候选")
            else:
                repository.update_task(task_id, status="paper_candidates_empty", message=f"找到 0 个候选。已访问 {page.url}，但没有识别到 Scholar 结果卡片。")
            browser.close()
            return ScholarRunResult(ok=True, count=len(items), message=f"Saved {len(items)} candidates")
    except Exception as exc:
        repository.update_task(task_id, status="search_failed", message=str(exc))
        return ScholarRunResult(ok=False, message=str(exc))


def collect_citing_papers(task_id: str, confirm_large: bool = False, visible: bool = True) -> ScholarRunResult:
    task = repository.get_task(task_id)
    if not task.get("target_result_id"):
        return ScholarRunResult(ok=False, message="请先确认论文 A")
    cited_by_count = task.get("cited_by_count") or 0
    if cited_by_count > 100 and not confirm_large:
        repository.update_task(task_id, status="needs_large_collection_confirm", needs_user_action=1, message=f"被引用次数为 {cited_by_count}，超过 100。请确认后继续。")
        return ScholarRunResult(ok=False, needs_user_action=True, message="Need large collection confirmation")
    if (task.get("cited_by_url") or "").startswith("demo://"):
        items = demo_citing_papers(task_id)
        for item in items:
            repository.upsert_result(task_id, "citation_b", item)
        repository.update_task(task_id, status="citations_fetched", current_page=1, message=f"Demo B 已保存 {len(items)} 篇")
        return ScholarRunResult(ok=True, count=len(items), message="Demo B saved")

    cited_url = task.get("cited_by_url")
    if not cited_url:
        return ScholarRunResult(ok=False, message="目标论文没有 cited-by URL")
    settings = get_settings()
    total = 0
    page_number = max(1, (task.get("current_page") or 0) + 1)
    next_url = cited_url
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not visible)
            page = browser.new_page()
            while next_url:
                page.goto(next_url, wait_until="domcontentloaded", timeout=45000)
                body_text = page.locator("body").inner_text(timeout=5000)
                if page_looks_abnormal(page, body_text):
                    if wait_for_manual_clear(page, visible):
                        body_text = page.locator("body").inner_text(timeout=5000)
                    else:
                        message = abnormal_message(page.url)
                        repository.update_task(task_id, status="needs_user_action", needs_user_action=1, current_page=page_number - 1, message=message)
                        browser.close()
                        return ScholarRunResult(ok=False, count=total, needs_user_action=True, message=message)
                items = extract_results(page, task_id, "citation_b", page_number)
                if not items and looks_abnormal(body_text[:4000]):
                    repository.update_task(task_id, status="needs_user_action", needs_user_action=1, current_page=page_number - 1, message="Scholar 镜像没有返回论文结果，疑似访问控制页面。请人工处理、等待恢复或更换镜像后继续。")
                    browser.close()
                    return ScholarRunResult(ok=False, count=total, needs_user_action=True, message="Needs user action")
                for item in items:
                    repository.upsert_result(task_id, "citation_b", item)
                    if item.get("pdf_url"):
                        download_pdf_url(task_id, item)
                total += len(items)
                repository.update_task(task_id, status="collecting_b", current_page=page_number, message=f"已保存第 {page_number} 页，累计 {total} 篇")
                next_link = page.locator("a[aria-label='Next'], a:has-text('下一页'), a:has-text('Next')")
                if next_link.count() == 0:
                    break
                next_href = next_link.first.get_attribute("href", timeout=2000)
                if not next_href:
                    break
                next_url = urljoin(page.url, next_href)
                page_number += 1
                time.sleep(random.uniform(settings.page_wait_min_seconds, settings.page_wait_max_seconds))
            browser.close()
        all_citations = repository.list_results(task_id, "citation_b")
        pdf_stats = download_pdfs_for_results(task_id, all_citations)
        repository.update_task(
            task_id,
            status="citations_fetched",
            message=(
                f"B 采集完成，新增/更新 {total} 篇；"
                f"PDF：可下载 {pdf_stats['total']}，新增下载 {pdf_stats['downloaded']}，"
                f"已存在 {pdf_stats['already']}，失败 {pdf_stats['failed']}，无直链 {pdf_stats['missing']}"
            ),
        )
        return ScholarRunResult(ok=True, count=total, message="B collection done")
    except Exception as exc:
        repository.update_task(task_id, status="collect_b_failed", message=str(exc))
        return ScholarRunResult(ok=False, count=total, message=str(exc))
