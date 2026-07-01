#!/usr/bin/env python3
"""Regression check: backend research persistence should use the final-report tool payload."""

from server.app import _capture_research_report

captured: dict[str, str] = {}
tool = _capture_research_report(captured)
result = tool.invoke({"report_markdown": "# 最终报告\n\n| 项目 | 结论 |\n| --- | --- |\n| moat | strong |"})

assert "已接收最终调研报告" in result
assert captured["report_markdown"].startswith("# 最终报告")
assert "moat" in captured["report_markdown"]
print("research report tool capture check passed")
