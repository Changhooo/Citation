from __future__ import annotations

import uuid
from typing import Any

from app.db import dumps, loads, now_iso, row_to_dict, tx


def create_task(query: str, scholar_mirror: str, name: str | None = None) -> dict[str, Any]:
    task_id = uuid.uuid4().hex
    now = now_iso()
    with tx() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id,name,query,scholar_mirror,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (task_id, name or query[:80], query, scholar_mirror, "created", now, now),
        )
    return get_task(task_id)


def get_task(task_id: str) -> dict[str, Any]:
    with tx() as conn:
        task = row_to_dict(conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
    if not task:
        raise KeyError(task_id)
    return task


def list_tasks() -> list[dict[str, Any]]:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def update_task(task_id: str, **fields: Any) -> dict[str, Any]:
    if not fields:
        return get_task(task_id)
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [task_id]
    with tx() as conn:
        conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", values)
    return get_task(task_id)


def get_task_settings(task_id: str) -> dict[str, Any]:
    return loads(get_task(task_id).get("settings_json"), {})


def update_task_settings(task_id: str, **fields: Any) -> dict[str, Any]:
    settings = get_task_settings(task_id)
    settings.update(fields)
    update_task(task_id, settings_json=dumps(settings))
    return settings


def upsert_result(task_id: str, role: str, item: dict[str, Any]) -> str:
    now = now_iso()
    result_id = item.get("id") or uuid.uuid4().hex
    with tx() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO scholar_results
            (id,task_id,role,title,authors_text,year,venue,snippet,result_url,pdf_url,cited_by_count,
             cited_by_url,page_number,position,raw_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                result_id,
                task_id,
                role,
                item.get("title") or "Untitled",
                item.get("authors_text") or "",
                item.get("year"),
                item.get("venue") or "",
                item.get("snippet") or "",
                item.get("result_url") or "",
                item.get("pdf_url") or "",
                item.get("cited_by_count") or 0,
                item.get("cited_by_url") or "",
                item.get("page_number") or 0,
                item.get("position") or 0,
                dumps(item),
                now,
                now,
            ),
        )
    return result_id


def get_result(task_id: str, result_id: str) -> dict[str, Any]:
    with tx() as conn:
        result = row_to_dict(conn.execute("SELECT * FROM scholar_results WHERE id=? AND task_id=?", (result_id, task_id)).fetchone())
    if not result:
        raise KeyError(result_id)
    return result


def list_results(task_id: str, role: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM scholar_results WHERE task_id=?"
    params: list[Any] = [task_id]
    if role:
        sql += " AND role=?"
        params.append(role)
    sql += " ORDER BY page_number ASC, position ASC, cited_by_count DESC"
    with tx() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def upsert_pdf_asset(
    task_id: str,
    result_id: str,
    source: str,
    url: str | None,
    path: str | None,
    status: str,
    match_confidence: float | None = None,
) -> str:
    now = now_iso()
    asset_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{task_id}:{result_id}:{source}").hex
    with tx() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO pdf_assets
            (id,task_id,result_id,source,url,path,status,match_confidence,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (asset_id, task_id, result_id, source, url or "", path or "", status, match_confidence, now, now),
        )
    return asset_id


def get_pdf_asset(task_id: str, result_id: str) -> dict[str, Any] | None:
    with tx() as conn:
        row = conn.execute(
            """
            SELECT * FROM pdf_assets
            WHERE task_id=? AND result_id=? AND status='downloaded'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (task_id, result_id),
        ).fetchone()
    return dict(row) if row else None


def list_pdf_assets(task_id: str) -> list[dict[str, Any]]:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM pdf_assets WHERE task_id=? ORDER BY updated_at DESC", (task_id,)).fetchall()
    return [dict(r) for r in rows]


def upsert_context(task_id: str, result_id: str, item: dict[str, Any]) -> str:
    now = now_iso()
    context_id = item.get("id") or uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{task_id}:{result_id}:{item.get('page')}:{item.get('hit_sentence')}",
    ).hex
    with tx() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO citation_contexts
            (id,task_id,result_id,page,marker,before_sentence,hit_sentence,after_sentence,
             sentiment,confidence,reason_zh,material_zh,review_status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                context_id,
                task_id,
                result_id,
                item.get("page"),
                item.get("marker") or "",
                item.get("before_sentence") or "",
                item.get("hit_sentence") or "",
                item.get("after_sentence") or "",
                item.get("sentiment") or "neutral",
                item.get("confidence") or 0,
                item.get("reason_zh") or "",
                item.get("material_zh") or "",
                item.get("review_status") or "pending",
                now,
                now,
            ),
        )
    return context_id


def list_contexts(task_id: str, result_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM citation_contexts WHERE task_id=?"
    params: list[Any] = [task_id]
    if result_id:
        sql += " AND result_id=?"
        params.append(result_id)
    sql += " ORDER BY result_id, page, created_at"
    with tx() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def clear_contexts(task_id: str, result_id: str | None = None) -> None:
    with tx() as conn:
        if result_id:
            conn.execute("DELETE FROM citation_contexts WHERE task_id=? AND result_id=?", (task_id, result_id))
        else:
            conn.execute("DELETE FROM citation_contexts WHERE task_id=?", (task_id,))


def list_author_evidence(task_id: str) -> list[dict[str, Any]]:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM author_evidence WHERE task_id=? ORDER BY confidence DESC", (task_id,)).fetchall()
    return [dict(r) for r in rows]


def upsert_author_evidence(task_id: str, result_id: str, item: dict[str, Any]) -> str:
    now = now_iso()
    evidence_id = item.get("id") or uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{task_id}:{result_id}:{item.get('author_name')}:{item.get('title_type')}:{item.get('evidence_url')}",
    ).hex
    with tx() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO author_evidence
            (id,task_id,result_id,author_name,title_type,evidence_url,evidence_snippet,
             confidence,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                evidence_id,
                task_id,
                result_id,
                item.get("author_name") or "",
                item.get("title_type") or "",
                item.get("evidence_url") or "",
                item.get("evidence_snippet") or "",
                item.get("confidence") or 0,
                item.get("status") or "candidate",
                now,
                now,
            ),
        )
    return evidence_id


def confirm_target(task_id: str, result_id: str) -> dict[str, Any]:
    result = None
    with tx() as conn:
        result = row_to_dict(conn.execute("SELECT * FROM scholar_results WHERE id=? AND task_id=?", (result_id, task_id)).fetchone())
    if not result:
        raise KeyError(result_id)
    return update_task(
        task_id,
        target_result_id=result_id,
        cited_by_count=result.get("cited_by_count") or 0,
        cited_by_url=result.get("cited_by_url") or "",
        status="paper_confirmed",
        message="已确认论文 A",
    )
