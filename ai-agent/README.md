# AI Berkshire Agent

独立金融分析 Agent，复用 [ai-berkshire](..) 项目的 Skills 和 Tools，
以 **DeepSeek + LangChain** 驱动，支持 CLI 和 React Web UI 两种交互方式。

## 架构

```
User 输入 "分析苹果产业链"
  ↓
System Prompt: 你是金融分析助手
  + 18 个 Skills 列表（名称 + 描述）
  + 8 个 Tools 列表（名称 + 用法）
  ↓
Agent 选择 Skill → load_skill("industry-funnel")
  ↓
Agent 按流程执行 → web_search / run_tool / read_file ...
  ↓
输出结构化研究报告（Markdown）
```

## 安装

```bash
cd ai-agent
uv sync
```

## 配置

1. 申请 DeepSeek API Key: https://platform.deepseek.com
2. 申请搜索 API Key: https://search.ligong.cyou
3. 设置环境变量:
```bash
export DEEPSEEK_API_KEY="sk-..."
export search_apikey="tvly-..."
```
或直接编辑 `config.yaml`

## 使用

### Web UI（推荐，React + Ant Design）

启动后端：

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

启动前端：

```bash
cd frontend
npm install
npm run dev
# 打开 http://localhost:5173
```

当前开发模式默认使用单用户 `admin`，不需要登录。旧 Streamlit UI 已不再推荐。

### CLI

```bash
# 列出可用 Skills
uv run main.py --list-skills

# 列出可用 Tools
uv run main.py --list-tools

# 交互式分析
uv run main.py "分析苹果产业链上游公司"

# 输出到文件
uv run main.py "对腾讯做一次投资研究" -o tencent-report.md
```

## 项目结构

```
ai-agent/
├── main.py                # CLI 入口
├── config.yaml             # DeepSeek API + Agent 配置
├── pyproject.toml          # uv 依赖管理
├── agent/
│   ├── skills_catalog.py   # 扫描 skills/*.md → system prompt
│   ├── tools_catalog.py    # 扫描 tools/*.py → system prompt
│   └── runner.py           # 组装 LangChain Agent（6 个 tool）
├── server/
│   └── app.py              # FastAPI 后端，复用 DB + Agent
├── frontend/
│   ├── src/App.tsx         # React + Ant Design 主界面
│   ├── src/api.ts          # API client
│   └── package.json        # Vite 前端依赖
├── web/
│   ├── db.py               # SQLite 用户 + 项目 + 研究会话存储
│   └── ...                 # 旧 Streamlit UI（不推荐）
└── data/
    └── app.db              # SQLite 数据库（自动创建）
```

## 内置 Tool

| Tool | 用途 |
|------|------|
| `load_skill(name)` | 读取完整研究流程 |
| `web_search(query)` | 联网搜索最新信息 |
| `fetch_webpage(url)` | 抓取网页正文 |
| `run_tool(name, cli_args)` | 执行 Python 分析工具 |
| `read_file(path)` | 读取项目内文件 |
| `write_file(path, content)` | 写入报告/数据 |
