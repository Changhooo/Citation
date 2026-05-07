from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import init_db
from core import repository
from core.scholar import collect_citing_papers, search_candidates


def main() -> None:
    init_db()
    task = repository.create_task("demo CORE", "https://scholar.lanfanshu.cn/", "demo CORE")
    search = search_candidates(task["id"], visible=False)
    candidates = repository.list_results(task["id"], "candidate_a")
    repository.confirm_target(task["id"], candidates[0]["id"])
    collect = collect_citing_papers(task["id"], visible=False)
    citations = repository.list_results(task["id"], "citation_b")
    print({"task": task["id"], "search": search.count, "collect": collect.count, "b": len(citations)})


if __name__ == "__main__":
    main()

