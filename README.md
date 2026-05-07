# CitationClaw

CitationClaw 是一个本地半自动引用立场分析工具。它以用户配置的 Google Scholar 镜像站为唯一入口，搜索目标论文 A，采集其 cited-by 论文群 B，筛选高影响/大佬作者论文 C，下载公开 PDF 或等待人工上传，然后定位 PDF 中引用 A 的上下文并判断正面、负面或中性。

## 项目结构

```text
citationclaw/
├── app/                 # FastAPI app, routes, config, task lifecycle
├── core/                # scholar/search/pdf/author/export engines
├── skills/              # five phase skills and runtime notes
├── static/              # CSS/JS/assets
├── templates/           # Jinja2 pages
├── data/                # SQLite, task files, PDFs, exports, cache
├── docs/                # docs and demos
├── tests/               # tests
├── scripts/             # startup and smoke scripts
├── pyproject.toml
├── README.md
└── .env.example
```

## 工作流

1. 配置 Scholar 镜像站，输入论文题目 A。
2. 可见 Playwright 浏览器打开镜像站并搜索，系统展示候选。
3. 用户确认论文 A。
4. 系统进入 cited-by 页面分页采集 B。若引用数大于 100，需用户确认。
5. 每抓一页保存一次，支持断点续跑。验证码/异常页面会暂停等待人工处理。
6. 只下载结果右侧直接显示的 PDF；缺失 PDF 可人工上传。
7. 按 Fellow/院士证据和 B 自身引用量 Top 10% 生成 C。
8. 解析 C 的 PDF，定位引用 A 的上下文，判断正/负/中。
9. 导出 HTML、CSV、JSON、完整 ZIP。

## 启动

```powershell
cd citationclaw
D:\anaconda3\python.exe -m pip install -r requirements.txt
D:\anaconda3\python.exe scripts\run_dev.py
```

打开：

```text
http://127.0.0.1:8010
```

## 说明

- 不绕过验证码、访问限制、付费墙或反爬机制。
- Playwright 使用可见浏览器运行，异常时用户可接手处理。
- PDF 只下载 Scholar 镜像结果右侧直接显示的公开 PDF 链接。

