from __future__ import annotations

from core import repository


def build_candidate_c(task_id: str) -> list[dict]:
    citations = repository.list_results(task_id, "citation_b")
    if not citations:
        repository.update_task(task_id, status="candidate_set_empty", message="没有 B，无法生成 C。")
        repository.update_task_settings(task_id, candidate_c_ids=[], candidate_c_reasons={})
        return []

    cutoff = max(1, round(len(citations) * 0.1))
    ranked = sorted(citations, key=lambda item: item.get("cited_by_count") or 0, reverse=True)
    selected = ranked[:cutoff]
    reasons = {
        item["id"]: f"高引用候选：B 内引用量 Top 10%，当前引用量 {item.get('cited_by_count') or 0}。这只表示论文影响力，不代表作者具有 Fellow/院士头衔。"
        for item in selected
    }
    repository.update_task_settings(
        task_id,
        candidate_c_ids=[item["id"] for item in selected],
        candidate_c_reasons=reasons,
    )
    repository.update_task(
        task_id,
        status="candidate_set_built",
        message=f"已生成高引用候选 C：{len(selected)} 篇。C 仅按 B 内 Top 10% 引用量筛选；是否为 Fellow/院士需执行作者联网筛查。",
    )
    return selected


def get_candidate_c(task_id: str) -> list[dict]:
    settings = repository.get_task_settings(task_id)
    selected_ids = set(settings.get("candidate_c_ids") or [])
    if not selected_ids:
        return []
    return [item for item in repository.list_results(task_id, "citation_b") if item["id"] in selected_ids]
