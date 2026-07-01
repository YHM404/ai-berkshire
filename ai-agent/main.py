#!/usr/bin/env python3
"""ai-berkshire-agent CLI — 独立金融分析助手。

用法:
    python main.py "分析苹果产业链"                        # 交互式分析
    python main.py "分析腾讯" --output report.md            # 输出到文件
    python main.py --list-skills                            # 列出可用 skills
    python main.py --list-tools                             # 列出可用 tools
"""

import argparse
import os
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agent.skills_catalog import build_skills_prompt
from agent.tools_catalog import build_tools_prompt
from agent.runner import build_agent

console = Console()


def load_config(config_path: Path) -> dict:
    """加载 YAML 配置，解析环境变量引用。"""
    raw = config_path.read_text(encoding="utf-8")
    # 替换 ${ENV_VAR} 引用
    import re
    def _replace_env(match):
        var = match.group(1)
        return os.environ.get(var, "")
    raw = re.sub(r'\$\{(\w+)\}', _replace_env, raw)
    return yaml.safe_load(raw)


def main():
    parser = argparse.ArgumentParser(
        description="AI Berkshire Agent — 独立金融分析助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py "分析苹果产业链上游公司"
  python main.py "对腾讯做一次投资研究"
  python main.py --list-skills
  python main.py --list-tools
        """,
    )
    parser.add_argument("query", nargs="?", help="分析问题（中文）")
    parser.add_argument("--output", "-o", help="输出报告到文件")
    parser.add_argument("--list-skills", action="store_true", help="列出所有可用 Skills")
    parser.add_argument("--list-tools", action="store_true", help="列出所有可用 Tools")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--no-verbose", action="store_true", help="隐藏 Agent 中间步骤")
    args = parser.parse_args()

    # 解析路径
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / args.config
    if not config_path.exists():
        console.print(f"[red]配置文件不存在: {config_path}[/red]")
        sys.exit(1)

    config = load_config(config_path)
    project_root = (script_dir / config.get("project_root", "..")).resolve()
    skills_dir = project_root / "skills"
    tools_dir = project_root / "tools"

    if not skills_dir.exists():
        console.print(f"[red]Skills 目录不存在: {skills_dir}[/red]")
        sys.exit(1)
    if not tools_dir.exists():
        console.print(f"[red]Tools 目录不存在: {tools_dir}[/red]")
        sys.exit(1)

    # --list-skills / --list-tools
    if args.list_skills:
        console.print(build_skills_prompt(skills_dir))
        return
    if args.list_tools:
        console.print(build_tools_prompt(tools_dir))
        return

    # 需要查询
    if not args.query:
        parser.print_help()
        sys.exit(1)

    # 检查 API Key
    api_key = config["llm"]["api_key"]
    if not api_key:
        console.print("[red]❌ DEEPSEEK_API_KEY 未设置。请在环境变量或 config.yaml 中配置。[/red]")
        console.print("[dim]注册地址: https://platform.deepseek.com[/dim]")
        sys.exit(1)

    # 创建 Agent
    console.print(Panel.fit(
        "[bold cyan]AI Berkshire Agent[/bold cyan]\n"
        f"模型: {config['llm']['model']} | Skills: {skills_dir} | Tools: {tools_dir}",
        title="启动",
    ))

    agent = build_agent(
        skills_dir=skills_dir,
        tools_dir=tools_dir,
        project_root=project_root,
        model=config["llm"]["model"],
        api_key=api_key,
        base_url=config["llm"].get("base_url", "https://api.deepseek.com/v1"),
        temperature=float(config["llm"].get("temperature", 0.3)),
        max_iterations=int(config["agent"].get("max_iterations", 30)),
        verbose=not args.no_verbose,
    )

    # 执行
    console.print(f"\n[dim]问题: {args.query}[/dim]\n")
    try:
        # 流式执行，展示 Agent 思考过程
        final_output = []
        for chunk in agent.stream(
            {"messages": [{"role": "user", "content": args.query}]},
            stream_mode="updates",
        ):
            for node_name, update in chunk.items():
                if node_name == "model":
                    msg = update.get("messages", [None])[0]
                    if msg and hasattr(msg, "content") and msg.content:
                        # 如果是有 tool_calls 的 AI 消息，只显示工具调用
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                tool_name = tc.get("name", "unknown")
                                tool_args = tc.get("args", {})
                                console.print(f"[yellow]🔧 {tool_name}({tool_args})[/yellow]")
                        else:
                            final_output.append(msg.content)
                elif node_name == "tools":
                    for tool_msg in update.get("messages", []):
                        if hasattr(tool_msg, "content"):
                            preview = str(tool_msg.content)[:200]
                            console.print(f"[dim]   → {preview}...[/dim]" if len(str(tool_msg.content)) > 200 else f"[dim]   → {tool_msg.content}[/dim]")

        # 最终输出
        output = "\n".join(final_output)
        if not output:
            output = "(Agent 未产出文本输出)"

        if args.output:
            output_path = Path(args.output)
            output_path.write_text(output, encoding="utf-8")
            console.print(f"\n[green]报告已保存到: {output_path}[/green]")
        else:
            console.print("\n[bold]分析结果:[/bold]\n")
            console.print(Markdown(output))

    except KeyboardInterrupt:
        console.print("\n[yellow]中断[/yellow]")
    except Exception as e:
        console.print(f"[red]执行错误: {e}[/red]")
        raise


if __name__ == "__main__":
    main()
