# Architecture

CitationClaw uses FastAPI + Jinja2 + SQLite. Playwright runs in visible mode for Scholar mirror interaction. Each task stores state in SQLite and task files under `data/tasks/{task_id}`.

