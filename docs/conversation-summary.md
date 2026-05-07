# CitationClaw 项目纪要

生成日期：2026-05-07

## 项目目标

CitationClaw 是一个本地单机研究工具，用于围绕一篇目标论文 A 构建引用立场分析工作流：

1. 在用户指定的 Scholar 镜像中搜索论文 A。
2. 用户确认目标论文 A。
3. 点击/解析镜像中的 `scholar_cites(...)`，采集引用 A 的论文群 B。
4. 对 B 按高引用规则生成候选论文群 C。
5. 对 C 的作者联网搜索 Fellow/院士证据，证据必须有 URL，不能由引用量直接推断。
6. 下载或上传 C/B 的 PDF。
7. 从 PDF 中找出引用 A 的上下文。
8. 对引用上下文进行正面、负面、中性初判。
9. 生成中文材料段落，并支持 JSON/CSV/ZIP 导出。

## 关键需求决策

- 工具定位：本地单机版研究工具。
- 前端形态：FastAPI + Jinja2 页面，目前不是 React/Vite 版本。
- 镜像入口：支持用户配置 Scholar 镜像，例如 `https://sc.panda985.com/`。
- cited-by ID：随镜像变化，不能跨镜像复用；换镜像后必须重新搜索并确认论文 A。
- B 采集：按 Scholar 镜像引用页逐页采集，保存页码和所有有用字段。
- 大于 100 篇时需要用户确认；当前实现已支持确认入口。
- PDF 下载：只处理 Scholar 右侧直接出现的 PDF 直链；失败或无直链时支持人工上传。
- PDF 上传：支持多 PDF 上传，也支持浏览器支持的文件夹上传；用文件名与论文标题模糊匹配。
- C 定义：C 只表示高引用候选论文，当前按 B 内引用量 Top 10% 生成。
- 大佬判断：不能用引用量直接判断，必须联网搜索作者的 Fellow/院士 URL 证据。
- 作者证据：保存作者名、头衔类型、证据 URL、证据片段、置信度、状态。
- 引用上下文：默认前一句 + 命中句 + 后一句，并标出命中句。
- 情感标签：正面、负面、中性；不确定归中性。
- 证据原文保留英文，理由和材料段落使用中文。

## 当前项目结构

```text
citationclaw/
├── app/                 # FastAPI app、配置、数据库初始化
├── core/                # Scholar 采集、PDF 存储、C 选择、作者筛查、上下文抽取、导出
├── skills/              # 阶段技能说明
├── static/              # CSS
├── templates/           # Jinja2 页面
├── data/                # 默认数据目录
├── dev_data/            # 当前开发数据目录，已加入 gitignore
├── docs/                # 文档
├── scripts/             # 启动/调试脚本
└── tests/               # 测试目录
```

## 已完成能力

- 创建任务。
- 配置 Scholar 镜像。
- 搜索候选论文 A。
- 用户确认目标论文 A。
- 手动修正当前镜像的 cited-by ID。
- 采集引用论文 B。
- 识别 Scholar 镜像安全验证/访问控制页。
- 支持 panda985 镜像 `verify_gate` 异常识别。
- 支持 C = B 内 Top 10% 高引用候选。
- 在 B 采集过程中自动下载可用 PDF。
- 对已采集 B 执行批量 PDF 补下载。
- 点击 PDF 时优先打开本地 PDF，未下载则尝试下载。
- 支持多 PDF 上传和文件夹上传。
- 上传 PDF 按文件名与论文标题自动模糊匹配。
- 支持 C 作者联网搜索 Fellow/院士证据。
- 支持 PDF 引用上下文抽取。
- 支持规则式正面/负面/中性初判。
- 支持材料段落生成。
- 支持 JSON/CSV/ZIP 导出，ZIP 包含本地 PDF。

## 重要调试记录

- `https://scholar.lanfanshu.cn/` 对某些请求返回 `So busy`，已加入异常识别。
- `https://sc.panda985.com/` 会跳转到 `/verify_gate` 安全验证页，已加入异常识别。
- Playwright strict mode 曾因 `.gs_a` 匹配多个节点报错，已改为取第一个有效节点。
- 右侧 PDF 中需要过滤镜像付费/加速链接，例如 `/pay/payonline` 和 `[PDF] sci-hub`。
- PDF 本地打开最初使用 `target="_blank"`，内置浏览器不明显，已改成当前页路由打开。
- CORE 任务中参考文献识别曾有硬编码，已开始改成基于当前论文标题关键词的通用匹配。

## 当前待办

- 完善通用引用标记识别，覆盖更多参考文献格式：
  - 数字型 `[12]`
  - 作者年份型 `(Smith et al., 2020)`
  - 上标引用
  - 脚注引用
  - 多引用 `[12, 15, 18]`
  - 范围引用 `[12-15]`
- 对 Remote Sensing 新任务验证上下文抽取，确保不再受 CORE 特定规则影响。
- 接入 DeepSeek/OpenAI/Anthropic，对规则初判结果做 LLM 复核。
- Fellow/院士作者消歧需要更严格策略：
  - 作者姓名
  - 论文主题
  - 机构
  - 官方 URL 优先
  - 低置信度必须人工确认
- 添加未匹配上传 PDF 的人工确认表。
- 添加任务进度日志和断点续跑可视化。
- 添加单元测试和端到端 smoke test。

## 运行方式

当前通过 conda/Anaconda Python 运行：

```powershell
D:\anaconda3\python.exe scripts\run_dev.py
```

本地服务：

```text
http://127.0.0.1:8010/
```

健康检查：

```text
http://127.0.0.1:8010/api/health
```

## Git 上传建议

建议提交代码和文档，但不要提交本地运行数据：

- 不提交 `dev_data/`
- 不提交 `data/*.sqlite3`
- 不提交下载的 PDF
- 不提交缓存和 Python 编译产物
- 提交 `docs/conversation-summary.md` 作为当前需求与实现记录
