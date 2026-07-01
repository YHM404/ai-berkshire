#!/usr/bin/env python3
"""Regression check: research report persistence must keep only the final AI answer."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from server.app import _final_ai_answer_from_messages

messages = [
    HumanMessage(content="分析某公司"),
    AIMessage(content="我会先搜索资料", tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "call_1"}]),
    ToolMessage(content="这是很长的中间搜索结果，不应保存到 report_md", tool_call_id="call_1"),
    AIMessage(content="# 最终报告\n\n| 项目 | 结论 |\n| --- | --- |\n| moat | strong |"),
]

result = _final_ai_answer_from_messages(messages)
assert result.startswith("# 最终报告"), result
assert "中间搜索结果" not in result, result
assert "tool" not in result.lower(), result
print("final report extraction check passed")
