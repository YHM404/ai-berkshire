"""FastAPI backend for the React AI Berkshire UI."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.tools import tool
from pydantic import BaseModel

from agent.chat_agent import _make_fetch_webpage, build_chat_agent
from agent.runner import build_agent
from web.db import (
    add_project_note,
    add_project_url,
    create_project,
    create_session,
    create_user,
    delete_project,
    delete_session,
    get_db,
    get_project,
    get_project_notes,
    get_session,
    get_user_count,
    init_db,
    list_projects,
    list_sessions,
    remove_project_url,
    update_session,
    verify_user,
)

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(ROOT / "data" / "app.db")
_CANCELLED: set[int] = set()


def load_config() -> dict[str, Any]:
    raw = (ROOT / "config.yaml").read_text(encoding="utf-8")
    raw = re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), raw)
    cfg = yaml.safe_load(raw)
    cfg["project_root"] = str((ROOT / cfg.get("project_root", "..")).resolve())
    return cfg


CONFIG = load_config()


def _message_text(message: Any) -> str:
    """Return plain text content from a LangChain message."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts).strip()
    return ""


def _final_ai_answer_from_messages(messages: list[Any]) -> str:
    """Extract the latest final AI answer, excluding tool calls and tool outputs."""
    final_answer = ""
    for message in messages:
        if getattr(message, "type", "") != "ai":
            continue
        if getattr(message, "tool_calls", None):
            continue
        text = _message_text(message)
        if text:
            final_answer = text
    return final_answer


def _capture_research_report(captured: dict[str, str]):
    """Create a tool that captures the final research report for persistence."""

    @tool
    def submit_research_report(report_markdown: str) -> str:
        """提交最终调研报告。调研完成后必须调用一次，参数是完整 Markdown 最终报告，不要包含中间过程。"""
        captured["report_markdown"] = report_markdown.strip()
        return "已接收最终调研报告，后端会保存该报告。"

    return submit_research_report


init_db(DB_PATH)
# 清理上次运行残留（服务器重启后没有线程在执行的 session，直接删除）
get_db(DB_PATH).execute(
    "DELETE FROM research_sessions WHERE status IN ('running', 'cancelling')"
).connection.commit()
if get_user_count(DB_PATH) == 0:
    create_user(DB_PATH, "admin", "admin")
ADMIN = verify_user(DB_PATH, "admin", "admin")["user"]
USER_ID = ADMIN["id"]

app = FastAPI(title="AI Berkshire Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectCreate(BaseModel):
    name: str


class UrlCreate(BaseModel):
    url: str


class NoteCreate(BaseModel):
    title: str
    content: str


class ResearchCreate(BaseModel):
    query: str


class ChatRequest(BaseModel):
    project_id: int
    message: str
    source_keys: list[str]
    messages: list[dict[str, str]] = []


class SourceDelete(BaseModel):
    kind: Literal["research", "url", "note"]
    id: int | str


def source_key(kind: str, value: int | str) -> str:
    if kind == "research":
        return f"research:{value}"
    if kind == "url":
        return f"url:{value}"
    if kind == "note":
        return f"note:{value}"
    raise ValueError(kind)


def serialize_session(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": s["id"],
        "project_id": s.get("project_id"),
        "type": s["type"],
        "query": s["query"],
        "status": s["status"],
        "created_at": s["created_at"],
    }


def get_project_payload(project_id: int) -> dict[str, Any]:
    project = get_project(DB_PATH, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    sessions = list_sessions(DB_PATH, USER_ID, project_id=project_id, limit=500)
    research = [serialize_session(s) for s in sessions if s["type"] == "research"]
    chats = [serialize_session(s) for s in sessions if s["type"] == "chat"]
    notes = get_project_notes(DB_PATH, project_id)
    sources: list[dict[str, Any]] = []
    for s in research:
        sources.append({
            "key": source_key("research", s["id"]),
            "kind": "research",
            "id": s["id"],
            "title": s["query"],
            "status": s["status"],
            "created_at": s["created_at"],
        })
    for url in project.get("saved_urls", []):
        sources.append({"key": source_key("url", url), "kind": "url", "id": url, "title": url, "status": "ready"})
    for n in notes:
        sources.append({
            "key": source_key("note", n["id"]),
            "kind": "note",
            "id": n["id"],
            "title": n["title"],
            "status": "ready",
            "created_at": n["created_at"],
        })
    return {
        "id": project["id"],
        "name": project["name"],
        "created_at": project["created_at"],
        "session_count": len(sessions),
        "sources": sources,
        "chats": chats,
    }


def build_context(source_keys: list[str]) -> str:
    parts: list[str] = []
    fetch = _make_fetch_webpage()
    for key in source_keys:
        if key.startswith("research:"):
            sid = int(key.split(":", 1)[1])
            sess = get_session(DB_PATH, sid)
            if sess and sess.get("report_md"):
                parts.append(f"### 调研: {sess['query']}\n\n{sess['report_md'][:5000]}")
        elif key.startswith("url:"):
            url = key.split(":", 1)[1]
            result = fetch.invoke({"url": url})
            parts.append(f"### 网页: {url}\n\n{result[:5000]}")
        elif key.startswith("note:"):
            note_id = int(key.split(":", 1)[1])
            row = get_db(DB_PATH).execute("SELECT * FROM project_notes WHERE id = ?", (note_id,)).fetchone()
            if row:
                parts.append(f"### 笔记: {row['title']}\n\n{row['content'][:5000]}")
    return "\n\n---\n\n".join(parts)


def run_research(session_id: int, query: str):
    """Run research with streaming (for cancellation) and persist report via final-report tool."""
    captured: dict[str, str] = {}
    final_report = ""
    print(f"[research:{session_id}] start: {query[:80]}")
    try:
        final_report_tool = _capture_research_report(captured)
        agent = build_agent(
            skills_dir=Path(CONFIG["project_root"]) / "skills",
            tools_dir=Path(CONFIG["project_root"]) / "tools",
            project_root=Path(CONFIG["project_root"]),
            model=CONFIG["llm"]["model"],
            api_key=CONFIG["llm"]["api_key"],
            base_url=CONFIG["llm"].get("base_url", "https://api.deepseek.com/v1"),
            temperature=float(CONFIG["llm"].get("temperature", 0.3)),
            extra_tools=[final_report_tool],
            extra_system_instructions="""
后端调研保存规则：
- 你完成所有调研、搜索、验证、计算后，必须调用 submit_research_report(report_markdown=...)。
- report_markdown 必须是完整最终 Markdown 调研报告，只包含最终结论、依据、数据来源、风险与置信度，不要包含工具调用日志、搜索原文堆叠或中间推理过程。
- 调用 submit_research_report 后，你可以用一句话说明报告已提交，不要再次输出完整报告。
""",
        )
        chunk_count = 0
        for chunk in agent.stream({"messages": [{"role": "user", "content": query}]}, stream_mode="updates"):
            chunk_count += 1
            if session_id in _CANCELLED:
                print(f"[research:{session_id}] cancelled at chunk {chunk_count}")
                _CANCELLED.discard(session_id)
                return
            for _, update in chunk.items():
                candidate = _final_ai_answer_from_messages(update.get("messages", []))
                if candidate:
                    final_report = candidate

        print(f"[research:{session_id}] stream done, chunks={chunk_count}, tool_report={'yes' if captured.get('report_markdown') else 'no'}, fallback={'yes' if final_report else 'no'}")

        # 用户可能在最后一批 chunk 后点了取消，不再覆盖 DB
        if session_id in _CANCELLED:
            _CANCELLED.discard(session_id)
            return

        report = captured.get("report_markdown") or final_report
        if not report.strip():
            raise RuntimeError("Agent 未返回最终调研报告")
        update_session(DB_PATH, session_id, status="completed", report_md=report)
        print(f"[research:{session_id}] completed, report_len={len(report)}")
    except Exception as exc:
        print(f"[research:{session_id}] failed: {exc}")
        if session_id not in _CANCELLED:
            update_session(DB_PATH, session_id, status="failed", report_md=f"❌ {exc}")


@app.get("/api/health")
def health():
    return {"ok": True, "user": ADMIN["username"]}


@app.get("/api/projects")
def api_projects():
    projects = list_projects(DB_PATH, USER_ID)
    return [get_project_payload(p["id"]) for p in projects]


@app.post("/api/projects")
def api_create_project(body: ProjectCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Project name required")
    pid = create_project(DB_PATH, USER_ID, name)
    return get_project_payload(pid)


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: int):
    delete_project(DB_PATH, project_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}")
def api_project(project_id: int):
    return get_project_payload(project_id)


@app.post("/api/projects/{project_id}/urls")
def api_add_url(project_id: int, body: UrlCreate):
    if not body.url.strip():
        raise HTTPException(400, "URL required")
    add_project_url(DB_PATH, project_id, body.url.strip())
    return get_project_payload(project_id)


@app.post("/api/projects/{project_id}/notes")
def api_add_note(project_id: int, body: NoteCreate):
    if not body.title.strip() or not body.content.strip():
        raise HTTPException(400, "Title and content required")
    add_project_note(DB_PATH, project_id, body.title.strip(), body.content.strip())
    return get_project_payload(project_id)


@app.post("/api/projects/{project_id}/research")
def api_start_research(project_id: int, body: ResearchCreate):
    query = body.query.strip()
    if not query:
        raise HTTPException(400, "Query required")
    active = [s for s in list_sessions(DB_PATH, USER_ID, project_id=project_id) if s["type"] == "research" and s["status"] == "running"]
    if active:
        raise HTTPException(409, "Research already running")
    sid = create_session(DB_PATH, USER_ID, query, project_id=project_id, session_type="research")
    threading.Thread(target=run_research, args=(sid, query), daemon=True).start()
    return {"session_id": sid, "project": get_project_payload(project_id)}


@app.post("/api/sessions/{session_id}/cancel")
def api_cancel_research(session_id: int):
    _CANCELLED.add(session_id)
    delete_session(DB_PATH, session_id)
    return {"ok": True}


@app.get("/api/sessions/{session_id}")
def api_session(session_id: int):
    sess = get_session(DB_PATH, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    return sess


@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: int):
    delete_session(DB_PATH, session_id)
    return {"ok": True}


@app.delete("/api/projects/{project_id}/sources")
def api_delete_source(project_id: int, body: SourceDelete):
    if body.kind == "research":
        delete_session(DB_PATH, int(body.id))
    elif body.kind == "url":
        remove_project_url(DB_PATH, project_id, str(body.id))
    elif body.kind == "note":
        get_db(DB_PATH).execute("DELETE FROM project_notes WHERE id = ?", (int(body.id),)).connection.commit()
    return get_project_payload(project_id)


@app.get("/api/projects/{project_id}/sources/{kind}/{source_id}")
def api_source_detail(project_id: int, kind: str, source_id: str):
    if kind == "research":
        return get_session(DB_PATH, int(source_id))
    if kind == "url":
        project = get_project(DB_PATH, project_id)
        if not project or source_id not in project.get("saved_urls", []):
            raise HTTPException(404, "URL not found")
        content = _make_fetch_webpage().invoke({"url": source_id})
        return {"kind": "url", "title": source_id, "content": content}
    if kind == "note":
        row = get_db(DB_PATH).execute("SELECT * FROM project_notes WHERE id = ?", (int(source_id),)).fetchone()
        if not row:
            raise HTTPException(404, "Note not found")
        return dict(row)
    raise HTTPException(400, "Invalid kind")


@app.post("/api/chat")
def api_chat(body: ChatRequest):
    if not body.message.strip():
        raise HTTPException(400, "Message required")
    context = build_context(body.source_keys)
    if not context.strip():
        raise HTTPException(400, "No selected data sources")
    agent = build_chat_agent(
        data_context=context,
        model=CONFIG["llm"]["model"],
        api_key=CONFIG["llm"]["api_key"],
        base_url=CONFIG["llm"].get("base_url", "https://api.deepseek.com/v1"),
    )
    full_msgs = body.messages + [{"role": "user", "content": body.message}]
    answer = ""
    for chunk in agent.stream({"messages": full_msgs}, stream_mode="updates"):
        for _, update in chunk.items():
            candidate = _final_ai_answer_from_messages(update.get("messages", []))
            if candidate:
                answer = candidate
    answer = answer or "_(无)_"
    sid = create_session(DB_PATH, USER_ID, body.message, project_id=body.project_id, session_type="chat")
    update_session(DB_PATH, sid, status="completed", messages=full_msgs + [{"role": "assistant", "content": answer}], data_sources=body.source_keys)
    return {"answer": answer, "session_id": sid, "project": get_project_payload(body.project_id)}
