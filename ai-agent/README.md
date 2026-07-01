# AI Berkshire Agent

独立金融分析 Agent，复用 [ai-berkshire](..) 项目的 Skills 和 Tools，
以 **DeepSeek + LangChain** 驱动，纯 CLI 交互。

## 架构

```
User 输入 "分析苹果产业链"
  ↓
System Prompt: 你是金融分析助手
  + 18 个 Skills 列表（名称 + 描述）
  + 9 个 Tools 列表（名称 + 用法）
  ↓
Agent 选择 Skill → load_skill("industry-funnel")
  ↓
Agent 按流程执行 → run_tool("financial_rigor.py", "verify-market-cap ...")
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
2. 设置环境变量:
```bash
export DEEPSEEK_API_KEY="sk-..."
```
或直接编辑 `config.yaml`

## 使用

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
├── main.py              # CLI 入口
├── config.yaml           # DeepSeek API + Agent 配置
├── pyproject.toml        # uv 依赖
└── agent/
    ├── skills_catalog.py  # 扫描 skills/*.md → system prompt
    ├── tools_catalog.py   # 扫描 tools/*.py → system prompt
    ├── runner.py          # 组装 LangChain Agent
    ├── skill_loader.py    # load_skill() tool（备用）
    └── tool_runner.py     # run_tool() tool（备用）
```
