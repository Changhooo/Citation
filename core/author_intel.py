from __future__ import annotations

import re
import time
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from core import repository
from core.selection import get_candidate_c


TITLE_PATTERNS = [
    ("IEEE Fellow", re.compile(r"\bIEEE\s+Fellow\b|\bFellow\s+of\s+(the\s+)?IEEE\b", re.I)),
    ("ACM Fellow", re.compile(r"\bACM\s+Fellow\b|\bFellow\s+of\s+(the\s+)?ACM\b", re.I)),
    ("AAAI Fellow", re.compile(r"\bAAAI\s+Fellow\b|\bFellow\s+of\s+(the\s+)?AAAI\b|\bFellow\s+of\s+(the\s+)?American\s+Association\s+of\s+Artificial\s+Intelligence\b", re.I)),
    ("IAPR Fellow", re.compile(r"\bIAPR\s+Fellow\b|\bFellow\s+of\s+(the\s+)?IAPR\b", re.I)),
    ("Royal Society Fellow", re.compile(r"\bFellow\s+of\s+the\s+Royal\s+Society\b|\bFRS\b", re.I)),
    ("Academician", re.compile(r"\bAcademician\b|\bMember\s+of\s+the\s+National\s+Academy\b|\bNational\s+Academy\s+of\s+(Engineering|Sciences)\b|\bChinese\s+Academy\s+of\s+Sciences\b|\bChinese\s+Academy\s+of\s+Engineering\b", re.I)),
]
OFFICIAL_HINTS = [
    "ieee.org",
    "acm.org",
    "aaai.org",
    "iapr.org",
    "royalsociety.org",
    "nae.edu",
    "nasonline.org",
    "cas.cn",
    "cae.cn",
    ".edu",
]


def parse_authors(authors_text: str, max_authors: int = 8) -> list[str]:
    head = (authors_text or "").split(" - ")[0]
    head = re.sub(r"\bet\s+al\.?", "", head, flags=re.I)
    head = head.replace("…", "").replace("...", "")
    names = []
    for part in re.split(r",| and ", head):
        name = re.sub(r"\s+", " ", part).strip()
        if len(name) >= 3 and re.search(r"[A-Za-z]", name):
            names.append(name)
    return list(dict.fromkeys(names))[:max_authors]


def search_web(query: str, timeout: int = 20) -> list[dict]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": "Mozilla/5.0 CitationClaw local research tool"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for node in soup.select(".result")[:8]:
        link = node.select_one(".result__a")
        snippet_node = node.select_one(".result__snippet")
        if not link:
            continue
        href = link.get("href", "")
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc or href.startswith("//duckduckgo.com"):
            qs = parse_qs(parsed.query)
            if qs.get("uddg"):
                href = unquote(qs["uddg"][0])
        results.append(
            {
                "title": link.get_text(" ", strip=True),
                "url": href,
                "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
            }
        )
    return results


def evidence_confidence(author: str, title_type: str, result: dict) -> float:
    url_host = urlparse(result.get("url") or "").netloc.lower()
    text = f"{result.get('title','')} {result.get('snippet','')}"
    confidence = 0.55
    if any(hint in url_host for hint in OFFICIAL_HINTS):
        confidence += 0.25
    if author.lower() in text.lower():
        confidence += 0.1
    if title_type.lower() in text.lower():
        confidence += 0.1
    return min(confidence, 0.95)


def classify_evidence(author: str, result: dict) -> list[dict]:
    text = f"{result.get('title','')} {result.get('snippet','')}"
    hits = []
    for title_type, pattern in TITLE_PATTERNS:
        if pattern.search(text):
            confidence = evidence_confidence(author, title_type, result)
            hits.append(
                {
                    "author_name": author,
                    "title_type": title_type,
                    "evidence_url": result.get("url") or "",
                    "evidence_snippet": text[:700],
                    "confidence": confidence,
                    "status": "confirmed" if confidence >= 0.82 else "candidate",
                }
            )
    return hits


def screen_authors_for_task(task_id: str) -> dict[str, int]:
    c_items = get_candidate_c(task_id)
    stats = {"papers": len(c_items), "authors": 0, "evidence": 0, "errors": 0}
    for paper in c_items:
        authors = parse_authors(paper.get("authors_text") or "")
        stats["authors"] += len(authors)
        for author in authors:
            queries = [
                f'"{author}" IEEE Fellow OR ACM Fellow OR AAAI Fellow',
                f'"{author}" academician OR "National Academy" OR "Fellow"',
            ]
            seen_urls = set()
            for query in queries:
                try:
                    results = search_web(query)
                except Exception:
                    stats["errors"] += 1
                    continue
                for result in results:
                    url = result.get("url") or ""
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    for evidence in classify_evidence(author, result):
                        repository.upsert_author_evidence(task_id, paper["id"], evidence)
                        stats["evidence"] += 1
                time.sleep(0.6)
    repository.update_task(
        task_id,
        status="author_screened",
        message=f"作者联网筛查完成：高引用候选论文 {stats['papers']} 篇，检索作者 {stats['authors']} 人，发现 Fellow/院士证据 {stats['evidence']} 条，搜索错误 {stats['errors']} 次。",
    )
    return stats
