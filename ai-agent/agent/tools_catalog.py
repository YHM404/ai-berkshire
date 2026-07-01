"""扫描 tools/*.py 生成工具目录列表，注入 system prompt。"""

import re
from pathlib import Path


def scan_tools(tools_dir: Path) -> list[dict[str, str]]:
    """扫描 tools 目录，返回 (name, description, usages) 列表。"""
    tools = []
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        name = f.name
        desc = _extract_docstring_desc(f)
        usages = _extract_usages(f)
        tools.append({"name": name, "description": desc, "usages": usages})
    return tools


def _extract_docstring_desc(filepath: Path) -> str:
    """从 Python 文件提取模块级 docstring 的第一行有效描述。"""
    content = filepath.read_text(encoding="utf-8")
    match = re.search(r'"""(.*?)"""', content, re.DOTALL)
    if not match:
        return "(无描述)"
    doc = match.group(1).strip()
    for line in doc.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("===") and not stripped.startswith("---"):
            return stripped
    return "(无描述)"


def _extract_usages(filepath: Path) -> list[str]:
    """提取文件中 python3 tools/... 使用示例。"""
    content = filepath.read_text(encoding="utf-8")
    matches = re.findall(r"python3 tools/\S+", content)
    return list(dict.fromkeys(matches))[:3]  # 去重取前3


def build_tools_prompt(tools_dir: Path) -> str:
    """生成注入 system prompt 的 tools 列表文本。"""
    tools = scan_tools(tools_dir)
    lines = ["\n## 可用 Tools (使用 run_tool(name, args) 执行)\n"]
    for t in tools:
        lines.append(f"- **{t['name']}**: {t['description']}")
        for u in t["usages"]:
            lines.append(f"    `{u}`")
    return "\n".join(lines)
