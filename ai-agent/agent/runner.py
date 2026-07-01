"""Agent Runner — 组装 LangChain Agent，注入 skills/tools 目录和 system prompt。"""

import subprocess
from pathlib import Path

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

from .skills_catalog import build_skills_prompt
from .tools_catalog import build_tools_prompt

SYSTEM_PROMPT = """你是一个专业的投资研究分析助手，基于巴菲特、芒格、段永平、李录的价值投资方法论。

你的工作方式：
1. 理解用户的分析需求
2. 从「可用 Skills」中选择合适的分析流程，调用 load_skill(name) 读取完整工作流
3. 严格按照 Skill 步骤执行，需要计算/验证时调用 run_tool(name, cli_args)
4. 需要最新数据时用 web_search 搜索，用 fetch_webpage 抓取网页正文
5. 用 read_file / write_file 读写项目内的研究报告和数据文件
6. 最终输出结构化研究报告

{skills_catalog}
{tools_catalog}

注意：
- 先选 skill 再执行，不要跳过 skill 直接分析
- 每个关键数据调用对应 tool 验证
- 运行不熟悉的工具时，先用 run_tool(name, cli_args="--help") 查看用法
- 报告用中文，标注每个数据的来源和置信度
- 如果用户问的是具体公司名，先确认行业再选 skill
"""


def _make_load_skill(skills_dir: str):
    """生成绑定了 skills_dir 的 load_skill tool。"""

    @tool
    def load_skill(name: str) -> str:
        """读取完整 Skill 工作流。传入 skill 名称（不含 .md），返回完整 markdown 指令。"""
        skill_path = Path(skills_dir) / f"{name}.md"
        if not skill_path.exists():
            all_skills = [f.stem for f in Path(skills_dir).glob("*.md") if f.stem != "CLAUDE"]
            return f"❌ Skill '{name}' 不存在。可用: {', '.join(all_skills)}"
        content = skill_path.read_text(encoding="utf-8")
        if len(content) > 15000:
            content = content[:15000] + "\n\n...(截断，需完整内容请指定章节)"
        return content

    return load_skill


def _make_read_file(project_root: str):
    """生成绑定了 project_root 的 read_file tool。"""

    @tool
    def read_file(path: str) -> str:
        """读取项目内的文件。路径相对于项目根目录。

        示例:
          read_file("reports/apple-research.md")
          read_file("data/market_data.csv")
        """
        full_path = (Path(project_root) / path).resolve()
        # 安全检查：不允许跳出项目目录
        if not str(full_path).startswith(str(Path(project_root).resolve())):
            return f"❌ 安全限制：不允许读取项目目录之外的文件: {path}"
        if not full_path.exists():
            return f"❌ 文件不存在: {path}"
        if full_path.is_dir():
            entries = sorted(full_path.iterdir())
            listing = "\n".join(f"  {'📁' if e.is_dir() else '📄'} {e.name}" for e in entries)
            return f"目录 {path}/:\n{listing}"
        try:
            content = full_path.read_text(encoding="utf-8")
            if len(content) > 20000:
                content = content[:20000] + f"\n\n...(文件过大，已截断，共 {len(content)} 字符)"
            return content
        except Exception as e:
            return f"❌ 读取失败: {e}"

    return read_file


def _make_write_file(project_root: str):
    """生成绑定了 project_root 的 write_file tool。"""

    @tool
    def write_file(path: str, content: str) -> str:
        """写入文件到项目目录。路径相对于项目根目录。会自动创建父目录。

        示例:
          write_file("reports/tencent-2025Q1.md", content="# 腾讯 2025Q1 分析...")
        """
        full_path = (Path(project_root) / path).resolve()
        if not str(full_path).startswith(str(Path(project_root).resolve())):
            return f"❌ 安全限制：不允许写入项目目录之外的文件: {path}"
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            return f"✓ 已写入: {path} ({len(content)} 字符)"
        except Exception as e:
            return f"❌ 写入失败: {e}"

    return write_file


def _make_web_search():
    """生成 web_search tool。"""
    import json, os, urllib.request

    PROXY_URL = "https://search.ligong.cyou/api/search"

    @tool
    def web_search(query: str) -> str:
        """联网搜索最新信息。用于获取实时数据、新闻、公司动态、行业趋势等。

        示例:
          web_search("Apple Q3 2025 earnings revenue")
          web_search("苹果供应链 最新动态 2025")
        """
        api_key = os.environ.get("search_apikey", "")
        if not api_key:
            return "❌ 未配置 search_apikey 环境变量，无法联网搜索。"
        body = json.dumps({
            "query": query,
            "topic": "news",
            "search_depth": "advanced",
            "max_results": 5,
        }).encode("utf-8")
        req = urllib.request.Request(
            PROXY_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # 提取回答 + 结果
            parts = []
            if data.get("answer"):
                parts.append(f"### 摘要\n{data['answer']}")
            results = data.get("results", [])
            if results:
                lines = ["### 搜索结果"]
                for i, r in enumerate(results[:5], 1):
                    title = r.get("title", "(无标题)")
                    url = r.get("url", "")
                    content = (r.get("content", "") or "")[:300]
                    lines.append(f"{i}. **{title}**\n   {url}\n   {content}")
                parts.append("\n".join(lines))
            return "\n\n".join(parts) if parts else "搜索无结果"
        except Exception as e:
            return f"❌ 搜索失败: {e}"

    return web_search


def _make_fetch_webpage():
    """生成 fetch_webpage tool。"""
    import json, os, urllib.request

    PROXY_URL = "https://search.ligong.cyou/api/extract"

    @tool
    def fetch_webpage(url: str) -> str:
        """抓取并提取网页正文内容。用于读取具体文章的完整内容。

        示例:
          fetch_webpage("https://www.macrotrends.net/stocks/charts/AAPL/apple/revenue")
        """
        api_key = os.environ.get("search_apikey", "")
        if not api_key:
            return "❌ 未配置 search_apikey 环境变量，无法抓取网页。"
        body = json.dumps({"urls": [url]}).encode("utf-8")
        req = urllib.request.Request(
            PROXY_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            if not results:
                return "❌ 网页内容为空"
            content = results[0].get("raw_content", "") or results[0].get("content", "")
            if len(content) > 12000:
                content = content[:12000] + "\n\n...(截断)"
            return content if content else "❌ 未能提取到正文"
        except Exception as e:
            return f"❌ 抓取失败: {e}"

    return fetch_webpage


def _make_run_tool(tools_dir: str, project_root: str):
    """生成绑定了路径的 run_tool tool。"""

    @tool
    def run_tool(name: str, cli_args: str = "") -> str:
        """执行 Python 分析工具。传入工具文件名和命令行参数。

        示例:
          run_tool("financial_rigor.py", cli_args="verify-market-cap --price 510 --shares 9.11e9 --reported 4.65e12 --currency HKD")
          run_tool("stock_screener.py", cli_args="--help")
        """
        tool_path = Path(tools_dir) / name
        if not tool_path.exists():
            all_tools = [f.name for f in Path(tools_dir).glob("*.py") if not f.name.startswith("_")]
            return f"❌ Tool '{name}' 不存在。可用: {', '.join(all_tools)}"

        cmd = ["python3", str(tool_path)] + (cli_args.split() if cli_args else [])
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, cwd=project_root,
            )
            output = result.stdout.strip()
            if result.stderr.strip():
                output += "\n[stderr]\n" + result.stderr.strip()[:1000]
            if result.returncode != 0:
                output = f"⚠️ 退出码 {result.returncode}:\n{output}"
            return output if output else "(无输出)"
        except subprocess.TimeoutExpired:
            return "⏰ 执行超时 (120s)"
        except Exception as e:
            return f"❌ 执行异常: {e}"

    return run_tool


def build_agent(
    skills_dir: Path,
    tools_dir: Path,
    project_root: Path,
    model: str = "deepseek-chat",
    api_key: str = "",
    base_url: str = "https://api.deepseek.com/v1",
    temperature: float = 0.3,
    max_iterations: int = 30,
    verbose: bool = True,
):
    """创建 LangChain Agent（返回 CompiledStateGraph）。"""

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )

    tools = [
        _make_load_skill(str(skills_dir)),
        _make_web_search(),
        _make_fetch_webpage(),
        _make_run_tool(str(tools_dir), str(project_root)),
        _make_read_file(str(project_root)),
        _make_write_file(str(project_root)),
    ]

    system_prompt = SYSTEM_PROMPT.format(
        skills_catalog=build_skills_prompt(skills_dir),
        tools_catalog=build_tools_prompt(tools_dir),
    )

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )

    return agent
