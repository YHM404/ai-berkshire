"""对话模式 Agent — 基于研究资料 + 外部数据源进行问答，不做完整 skill 流程。"""

from pathlib import Path

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

CHAT_SYSTEM_PROMPT = """你是一个专业的投资研究分析师，只基于用户在左侧勾选的数据源回答问题。

你的工作方式：
- 只能使用下面提供的资料上下文作答
- 不要搜索网页，不要调用工具，不要提及或使用任何 skill/workflow
- 如果资料不足以回答，直接说明“当前选中的数据源不足以回答”，并指出缺少什么信息
- 引用资料时标注来源（调研标题、URL 或笔记标题）
- 给出清晰的分析结论，用中文

## 已选数据源上下文

{data_context}
"""


def build_chat_agent(
    data_context: str,
    model: str = "deepseek-chat",
    api_key: str = "",
    base_url: str = "https://api.deepseek.com/v1",
    temperature: float = 0.3,
):
    """构建对话模式 Agent。data_context 是拼接好的研究资料文本。"""

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )

    # 对话模式不暴露任何工具给模型，避免它主动 web_search / fetch_webpage / skill 调用。
    system_prompt = CHAT_SYSTEM_PROMPT.format(data_context=data_context)

    return create_agent(model=llm, tools=[], system_prompt=system_prompt)


# ── 内联工具（同 runner.py，避免循环导入）───────────────────────

def _make_web_search():
    import json, os, urllib.request

    @tool
    def web_search(query: str) -> str:
        """联网搜索最新信息。"""
        api_key = os.environ.get("search_apikey", "")
        if not api_key:
            return "❌ 未配置 search_apikey"
        body = json.dumps({"query": query, "topic": "news", "search_depth": "advanced", "max_results": 5}).encode()
        req = urllib.request.Request("https://search.ligong.cyou/api/search", data=body,
                                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            parts = []
            if data.get("answer"):
                parts.append(f"### 摘要\n{data['answer']}")
            for i, r in enumerate(data.get("results", [])[:5], 1):
                parts.append(f"{i}. **{r.get('title','')}**\n   {r.get('url','')}\n   {(r.get('content','') or '')[:300]}")
            return "\n\n".join(parts) if parts else "无结果"
        except Exception as e:
            return f"❌ {e}"

    return web_search


def _make_fetch_webpage():
    import json, os, urllib.request

    @tool
    def fetch_webpage(url: str) -> str:
        """抓取网页正文。"""
        api_key = os.environ.get("search_apikey", "")
        if not api_key:
            return "❌ 未配置 search_apikey"
        body = json.dumps({"urls": [url]}).encode()
        req = urllib.request.Request("https://search.ligong.cyou/api/extract", data=body,
                                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            results = data.get("results", [])
            if not results:
                return "❌ 网页内容为空"
            content = results[0].get("raw_content", "") or results[0].get("content", "")
            return content[:12000] + ("\n...(截断)" if len(content) > 12000 else "")
        except Exception as e:
            return f"❌ {e}"

    return fetch_webpage
