"""扫描 skills/*.md 生成 skill 目录列表，注入 system prompt。"""

import re
from pathlib import Path


def scan_skills(skills_dir: Path) -> list[dict[str, str]]:
    """扫描 skills 目录，返回 (name, description) 列表。"""
    skills = []
    for f in sorted(skills_dir.glob("*.md")):
        if f.name == "CLAUDE.md":
            continue
        name = f.stem
        desc = _extract_description(f)
        skills.append({"name": name, "description": desc})
    return skills


def _extract_description(filepath: Path) -> str:
    """从 skill markdown 提取描述：优先 YAML frontmatter description，否则取第一段正文。"""
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")
    in_frontmatter = False

    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        # YAML frontmatter 中的 description
        if in_frontmatter and stripped.startswith("description:"):
            return stripped.split(":", 1)[1].strip()

    # 回退：取第一段有效正文
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---") or stripped.startswith(">") or stripped.startswith("!"):
            continue
        if stripped.startswith("**"):
            return stripped.strip("* ").strip()
        return stripped
    return "(无描述)"


def build_skills_prompt(skills_dir: Path) -> str:
    """生成注入 system prompt 的 skills 列表文本。"""
    skills = scan_skills(skills_dir)
    lines = ["## 可用 Skills (使用 load_skill(name) 读取完整工作流)\n"]
    for s in skills:
        lines.append(f"- **{s['name']}**: {s['description']}")
    return "\n".join(lines)
