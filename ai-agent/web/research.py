"""Dashboard 页面 — 侧边栏异步调研 + 主区域对话/查看。"""

import time

import streamlit as st
import streamlit_antd_components as sac

from web.db import (
    create_project, list_projects, get_project, delete_project,
    create_session, update_session, delete_session, list_sessions, get_session, get_db,
)
from web.components import report_view


_CANCELLED_RESEARCH_IDS: set[int] = set()


def render(db_path: str, agent_config: dict):
    user_id = st.session_state.get("user", {}).get("id", 1)

    # ── 顶部条 ──
    st.title("🏦 AI Berkshire Agent")
    _inject_sidebar_css()

    # ── 初始化 ──
    _init_state()

    # ── 侧边栏：项目树 + 调研入口 ──
    _render_sidebar(db_path, user_id, agent_config)

    # ── 主区域：始终对话窗口 ──
    project_id = _current_project_id()
    _render_main_chat(db_path, user_id, project_id, agent_config)

    # ── 弹窗：查看调研结果 ──
    if st.session_state.get("current_view_session"):
        _show_session_dialog(db_path)
    if st.session_state.get("view_url"):
        _show_url_dialog()
    if st.session_state.get("view_note"):
        _show_note_dialog(db_path)

    # 自动刷新（有后台调研时）
    if _has_active_research(db_path, user_id):
        time.sleep(2)
        st.rerun()


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _init_state():
    defaults = {
        "current_project_id": None,
        "expanded_project_id": None,
        "current_view_session": None,
        "view_url": None,
        "view_note": None,
        "active_source_key": None,
        "action_project_id": None,
        "chat_sources": set(),
        "chat_url_sources": set(),
        "chat_note_sources": set(),
        "chat_messages": [],
        "chat_session_id": None,
        "show_new_project": False,
        "research_session_id": None,
        "sidebar_nonce": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v



def _current_project_id() -> int | None:
    pid = st.session_state.current_project_id
    return int(pid) if pid else None


def _select_project(project_id: int):
    """切换当前项目；跨项目时清空临时聊天上下文和勾选的数据源。"""
    if _current_project_id() != project_id:
        st.session_state.chat_sources = set()
        st.session_state.chat_url_sources = set()
        st.session_state.chat_note_sources = set()
        st.session_state.chat_messages = []
        st.session_state.chat_session_id = None
        st.session_state.active_source_key = None
    st.session_state.current_project_id = project_id


def _selected_source_keys() -> set[str]:
    keys = {f"research:{sid}" for sid in st.session_state.get("chat_sources", set())}
    keys.update(st.session_state.get("chat_url_sources", set()))
    keys.update(st.session_state.get("chat_note_sources", set()))
    return keys


def _apply_selected_source_keys(keys: set[str]):
    st.session_state.chat_sources = {
        int(k.split(":", 1)[1]) for k in keys if k.startswith("research:")
    }
    st.session_state.chat_url_sources = {k for k in keys if k.startswith("url_")}
    st.session_state.chat_note_sources = {k for k in keys if k.startswith("note_")}


def _view_source(source: dict):
    if source["kind"] == "research":
        st.session_state.current_view_session = source["id"]
    elif source["kind"] == "url":
        st.session_state.view_url = source["id"]
    elif source["kind"] == "note":
        st.session_state.view_note = source["id"]


def _bump_sidebar_nonce():
    st.session_state.sidebar_nonce += 1


def _delete_source(db_path: str, project_id: int, source: dict):
    if source["kind"] == "research":
        delete_session(db_path, source["id"])
        st.session_state.chat_sources.discard(source["id"])
    elif source["kind"] == "url":
        from web.db import remove_project_url
        remove_project_url(db_path, project_id, source["id"])
        st.session_state.chat_url_sources.discard(f"url_{source['id']}")
    elif source["kind"] == "note":
        get_db(db_path).execute("DELETE FROM project_notes WHERE id = ?", (source["id"],)).connection.commit()
        st.session_state.chat_note_sources.discard(f"note_{source['id']}")


def _inject_sidebar_css():
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] hr,
        section[data-testid="stSidebar"] [data-testid="stDivider"],
        section[data-testid="stSidebar"] [role="separator"],
        section[data-testid="stSidebar"] div:has(> hr) {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
        }

        section[data-testid="stSidebar"] div:not([data-testid="stButton"]):not([data-testid="stPopover"]):not([data-testid="stExpander"]) {
            border-top: 0 !important;
            border-bottom: 0 !important;
        }

        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.35rem;
        }
        section[data-testid="stSidebar"] button {
            min-height: 2.15rem;
            border-radius: 0.55rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            margin-top: 0.15rem;
            color: rgba(250, 250, 250, 0.58);
        }
        section[data-testid="stSidebar"] iframe {
            border-radius: 0.65rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════
# 侧边栏
# ═══════════════════════════════════════════════════════════════════

def _render_sidebar(db_path: str, user_id: int, agent_config: dict):
    with st.sidebar:
        # ── 项目树 ──
        st.subheader("📁 项目")
        if sac.buttons(
            [sac.ButtonsItem(label="新建项目", icon="plus-circle")],
            key=f"quick_new_project_{st.session_state.sidebar_nonce}",
            index=None,
            variant="filled" if st.session_state.get("show_new_project") else "outline",
            color="blue",
            size="sm",
            use_container_width=True,
        ):
            _bump_sidebar_nonce()
            st.session_state.show_new_project = not st.session_state.get("show_new_project", False)
            st.session_state.action_project_id = None

        if st.session_state.get("show_new_project"):
            with st.container(border=True):
                name = st.text_input("项目名", key="new_proj_input", label_visibility="collapsed", placeholder="新项目名称")
                action = sac.buttons(
                    [
                        sac.ButtonsItem(label="创建", icon="check-circle"),
                        sac.ButtonsItem(label="取消", icon="x-circle", color="gray"),
                    ],
                    key=f"new_project_actions_{st.session_state.sidebar_nonce}",
                    index=None,
                    variant="filled",
                    color="blue",
                    size="xs",
                    use_container_width=True,
                )
                if action == "创建" and name.strip():
                    _bump_sidebar_nonce()
                    pid = create_project(db_path, user_id, name.strip())
                    _select_project(pid)
                    st.session_state.expanded_project_id = pid
                    st.session_state.show_new_project = False
                    st.rerun()
                elif action == "取消":
                    _bump_sidebar_nonce()
                    st.session_state.show_new_project = False
                    st.rerun()

        projects = list_projects(db_path, user_id)

        for p in projects:
            sessions = list_sessions(db_path, user_id, project_id=p["id"])
            is_current = _current_project_id() == p["id"]
            is_expanded = st.session_state.expanded_project_id == p["id"]

            with st.container():
                col_name, col_action = st.columns([5, 1], gap="small")
                with col_name:
                    label = p["name"]
                    clicked = sac.buttons(
                        [sac.ButtonsItem(
                            label=label,
                            icon="folder2-open" if is_expanded else "folder2",
                        )],
                        key=f"proj_{p['id']}_{st.session_state.sidebar_nonce}",
                        index=None,
                        variant="filled" if is_expanded else "outline",
                        color="blue" if is_current else "gray",
                        size="sm",
                        use_container_width=True,
                    )
                    if clicked:
                        _bump_sidebar_nonce()
                        _select_project(p["id"])
                        st.session_state.expanded_project_id = None if is_expanded else p["id"]
                        st.session_state.action_project_id = None
                        st.rerun()
                with col_action:
                    action_clicked = sac.buttons(
                        [sac.ButtonsItem(label="操作", icon="three-dots")],
                        key=f"proj_action_{p['id']}_{st.session_state.sidebar_nonce}",
                        index=None,
                        variant="filled" if st.session_state.get("action_project_id") == p["id"] else "outline",
                        color="blue",
                        size="sm",
                        use_container_width=True,
                    )
                    if action_clicked:
                        _bump_sidebar_nonce()
                        st.session_state.action_project_id = None if st.session_state.get("action_project_id") == p["id"] else p["id"]
                        st.session_state.show_new_project = False
                        st.session_state.expanded_project_id = p["id"]
                        _select_project(p["id"])
                        st.rerun()

            if st.session_state.get("action_project_id") == p["id"]:
                _render_popover_content(db_path, user_id, p, agent_config)

            if st.session_state.expanded_project_id == p["id"]:
                _render_project_sessions(db_path, user_id, p, sessions)


def _render_project_sessions(db_path, user_id, project, sessions):
    """渲染项目下的数据源和对话历史。"""
    pid = project["id"]
    pdata = get_project(db_path, pid)
    urls = pdata.get("saved_urls", []) if pdata else []
    from web.db import get_project_notes
    notes = get_project_notes(db_path, pid)
    research_sessions = [s for s in sessions if s["type"] == "research"]
    chat_sessions = [s for s in sessions if s["type"] == "chat"]

    running = [s for s in research_sessions if s["status"] in {"running", "cancelling"}]
    completed = [s for s in research_sessions if s["status"] == "completed"]
    inactive = [s for s in research_sessions if s["status"] in {"failed", "cancelled"}]

    for s in running:
        status = "取消中" if s["status"] == "cancelling" else "运行中"
        sac.alert(
            label=f"调研{status}",
            description=s["query"][:60],
            color="warning" if s["status"] == "cancelling" else "info",
            variant="light",
            size="sm",
            icon=True,
        )
        if s["status"] == "running":
            if sac.buttons(
                [sac.ButtonsItem(label="取消调研", icon="x-circle")],
                key=f"cancel_btn_{s['id']}",
                variant="outline",
                color="red",
                size="xs",
                use_container_width=True,
            ):
                _request_cancel_research(db_path, s["id"])
                st.rerun()

    source_entries = []
    for s in completed:
        source_entries.append({
            "key": f"research:{s['id']}",
            "label": f"{s['query'][:34]}",
            "icon": "journal-text",
            "tag": sac.Tag("调研", color="blue"),
            "kind": "research",
            "id": s["id"],
        })
    for url in urls:
        source_entries.append({
            "key": f"url_{url}",
            "label": url[:42],
            "icon": "link-45deg",
            "tag": sac.Tag("网页", color="cyan"),
            "kind": "url",
            "id": url,
        })
    for n in notes:
        source_entries.append({
            "key": f"note_{n['id']}",
            "label": n["title"][:36],
            "icon": "file-earmark-text",
            "tag": sac.Tag("文本", color="green"),
            "kind": "note",
            "id": n["id"],
        })

    if source_entries:
        st.caption("数据源")
        selected_keys = _selected_source_keys()
        selected_indices = [i for i, e in enumerate(source_entries) if e["key"] in selected_keys]
        tree_items = [
            sac.TreeItem(label=e["label"], icon=e["icon"], tag=e["tag"])
            for e in source_entries
        ]
        chosen_indices = sac.tree(
            tree_items,
            index=selected_indices,
            checkbox=True,
            checkbox_strict=True,
            show_line=False,
            return_index=True,
            size="sm",
            color="blue",
            key=f"source_tree_{pid}",
        ) or []
        new_keys = {source_entries[i]["key"] for i in chosen_indices if 0 <= i < len(source_entries)}
        changed = new_keys.symmetric_difference(selected_keys)
        if changed:
            st.session_state.active_source_key = next(iter(changed))
        _apply_selected_source_keys(new_keys)

        active_key = st.session_state.get("active_source_key")
        active = next((e for e in source_entries if e["key"] == active_key), None)
        if active:
            action = sac.buttons(
                [
                    sac.ButtonsItem(label="查看", icon="eye"),
                    sac.ButtonsItem(label="删除", icon="trash", color="red"),
                ],
                key=f"source_actions_{pid}_{active_key}",
                index=None,
                variant="text",
                size="xs",
                align="end",
            )
            if action == "查看":
                _view_source(active)
                st.rerun()
            elif action == "删除":
                _delete_source(db_path, pid, active)
                st.session_state.active_source_key = None
                st.rerun()
    elif not running:
        st.caption("暂无数据源，点右侧 ⋯ 添加调研/网页/文本")

    if inactive:
        st.caption("历史状态")
        for s in inactive:
            label = "已取消" if s["status"] == "cancelled" else "失败"
            color = "gray" if s["status"] == "cancelled" else "red"
            sac.alert(label=label, description=s["query"][:60], color=color, variant="quote-light", size="xs")

    if chat_sessions:
        st.caption("对话")
        for s in chat_sessions:
            action = sac.buttons(
                [
                    sac.ButtonsItem(label=f"{s['query'][:25]}", icon="chat-left-text"),
                    sac.ButtonsItem(label="删", icon="trash", color="red"),
                ],
                key=f"chat_row_{s['id']}",
                index=None,
                variant="outline",
                color="gray",
                size="xs",
                use_container_width=True,
            )
            if action == f"{s['query'][:25]}":
                st.session_state.current_view_session = s["id"]
                st.rerun()
            elif action == "删":
                delete_session(db_path, s["id"])
                if st.session_state.get("chat_session_id") == s["id"]:
                    st.session_state.chat_session_id = None
                    st.session_state.chat_messages = []
                if st.session_state.get("current_view_session") == s["id"]:
                    st.session_state.current_view_session = None
                st.rerun()


def _render_popover_content(db_path: str, user_id: int, project: dict, agent_config: dict):
    """项目内联操作面板。"""
    pid = project["id"]
    with st.container(border=True):
        sac.alert(
            label=project["name"],
            description="选择要添加到该项目的数据源类型",
            icon="folder2-open",
            color="blue",
            variant="quote-light",
            size="xs",
        )
        labels = ["新建调研", "添加网页", "添加文本", "删除项目"]
        action_idx = sac.buttons(
            [
                sac.ButtonsItem(label="调研", icon="search"),
                sac.ButtonsItem(label="网页", icon="link-45deg"),
                sac.ButtonsItem(label="文本", icon="file-earmark-text"),
                sac.ButtonsItem(label="删除", icon="trash", color="red"),
            ],
            key=f"pop_action_{pid}",
            index=0,
            return_index=True,
            variant="outline",
            color="blue",
            size="xs",
            use_container_width=True,
        )
        action = labels[action_idx or 0]

        if action == "新建调研":
            active = any(
                s["type"] == "research" and s["status"] in {"running", "cancelling"}
                for s in list_sessions(db_path, user_id, project_id=pid)
            )
            if active:
                sac.alert(label="已有调研在运行", description="可在项目数据源区域取消。", color="warning", variant="light", size="xs", icon=True)

            query = st.text_area("研究问题", placeholder="分析苹果产业链上游公司...",
                                 key=f"pop_q_{pid}", height=80)
            run_clicked = sac.buttons(
                [sac.ButtonsItem(label="开始调研", icon="play-circle", disabled=active or not query.strip())],
                key=f"pop_run_{pid}",
                index=None,
                variant="filled",
                color="blue",
                size="sm",
                use_container_width=True,
            )
            if run_clicked and query.strip():
                from web.db import create_session
                _select_project(pid)
                st.session_state.expanded_project_id = pid
                sid = create_session(db_path, user_id, query.strip(), project_id=pid, session_type="research")
                st.session_state.research_session_id = sid
                _start_bg_thread(db_path, sid, agent_config, query.strip())
                st.session_state.action_project_id = None
                st.rerun()

        elif action == "添加网页":
            url = st.text_input("网页地址", placeholder="https://...", key=f"pop_url_{pid}")
            add_clicked = sac.buttons(
                [sac.ButtonsItem(label="添加网页", icon="plus-circle", disabled=not url.strip())],
                key=f"pop_addurl_{pid}",
                index=None,
                variant="filled",
                color="blue",
                size="sm",
                use_container_width=True,
            )
            if add_clicked and url.strip():
                from web.db import add_project_url
                add_project_url(db_path, pid, url.strip())
                st.session_state.action_project_id = None
                st.rerun()

        elif action == "添加文本":
            title = st.text_input("标题", placeholder="关于这家公司的笔记...", key=f"pop_ntitle_{pid}")
            note = st.text_area("内容", placeholder="输入参考文本...", key=f"pop_note_{pid}", height=100)
            save_clicked = sac.buttons(
                [sac.ButtonsItem(label="保存文本", icon="check-circle", disabled=not (title.strip() and note.strip()))],
                key=f"pop_savenote_{pid}",
                index=None,
                variant="filled",
                color="blue",
                size="sm",
                use_container_width=True,
            )
            if save_clicked and title.strip() and note.strip():
                from web.db import add_project_note
                add_project_note(db_path, pid, title.strip(), note.strip())
                st.session_state.action_project_id = None
                st.rerun()

        elif action == "删除项目":
            sac.alert(
                label="危险操作",
                description=f"删除「{project['name']}」及其所有研究记录，无法恢复。",
                color="error",
                variant="light",
                size="sm",
                icon=True,
            )
            confirm = sac.buttons(
                [sac.ButtonsItem(label="确认删除项目", icon="trash")],
                key=f"pop_del_{pid}",
                index=None,
                variant="filled",
                color="red",
                size="sm",
                use_container_width=True,
            )
            if confirm:
                delete_project(db_path, pid)
                if st.session_state.current_project_id == pid:
                    st.session_state.current_project_id = None
                if st.session_state.expanded_project_id == pid:
                    st.session_state.expanded_project_id = None
                if st.session_state.action_project_id == pid:
                    st.session_state.action_project_id = None
                st.rerun()


def _has_active_research(db_path: str, user_id: int) -> bool:
    sessions = list_sessions(db_path, user_id, limit=500)
    return any(s["type"] == "research" and s["status"] in {"running", "cancelling"} for s in sessions)


def _request_cancel_research(db_path: str, session_id: int):
    """请求取消调研；后台线程会在下一个输出 chunk 停止。"""
    _CANCELLED_RESEARCH_IDS.add(session_id)
    update_session(db_path, session_id, status="cancelling")


def _start_bg_thread(db_path: str, session_id: int, agent_config: dict, query: str):
    """启动后台调研线程。"""
    import threading, time
    from pathlib import Path
    from agent.runner import build_agent
    from web.db import update_session

    def run():
        try:
            agent = build_agent(
                skills_dir=Path(agent_config["project_root"]) / "skills",
                tools_dir=Path(agent_config["project_root"]) / "tools",
                project_root=Path(agent_config["project_root"]),
                model=agent_config["llm"]["model"],
                api_key=agent_config["llm"]["api_key"],
                base_url=agent_config["llm"].get("base_url", "https://api.deepseek.com/v1"),
                temperature=float(agent_config["llm"].get("temperature", 0.3)),
            )
            acc = []
            steps = []

            for chunk in agent.stream({"messages": [{"role": "user", "content": query}]}, stream_mode="updates"):
                if session_id in _CANCELLED_RESEARCH_IDS:
                    update_session(db_path, session_id, status="cancelled", report_md="".join(acc))
                    _CANCELLED_RESEARCH_IDS.discard(session_id)
                    return

                for node_name, update in chunk.items():
                    if node_name == "model":
                        for msg in update.get("messages", []):
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    steps.append({"time": time.strftime("%H:%M:%S"), "detail": tc.get("name", "?")})
                            if hasattr(msg, "content") and msg.content and isinstance(msg.content, str) and msg.content.strip():
                                acc.append(msg.content.strip())
                    elif node_name == "tools":
                        for tm in update.get("messages", []):
                            steps.append({"time": time.strftime("%H:%M:%S"), "detail": str(tm.content)[:100] if hasattr(tm, "content") else ""})

            if session_id in _CANCELLED_RESEARCH_IDS:
                update_session(db_path, session_id, status="cancelled", report_md="".join(acc))
                _CANCELLED_RESEARCH_IDS.discard(session_id)
            else:
                update_session(db_path, session_id, status="completed", report_md="".join(acc))
        except Exception as e:
            update_session(db_path, session_id, status="failed", report_md=f"❌ {e}")

    threading.Thread(target=run, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# 后台调研执行
# ═══════════════════════════════════════════════════════════════════
# 弹窗 — 查看结果
# ═══════════════════════════════════════════════════════════════════

@st.dialog("调研结果", width="large")
def _show_session_dialog(db_path):
    sid = st.session_state.current_view_session
    sess = get_session(db_path, sid)
    if not sess:
        st.warning("会话不存在")
        if st.button("关闭"):
            st.session_state.current_view_session = None
            st.rerun()
        return

    st.caption(f"📄 {sess['query']}")
    if sess["type"] == "chat":
        for msg in sess.get("messages", []):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"][:500])
    else:
        report_view.render(sess.get("report_md", ""))


@st.dialog("网页内容", width="large")
def _show_url_dialog():
    url = st.session_state.view_url
    from agent.chat_agent import _make_fetch_webpage
    fetch = _make_fetch_webpage()
    with st.spinner("加载中..."):
        content = fetch.invoke({"url": url})
    st.markdown(content if content else "_(无法加载)_")
    if st.button("关闭"):
        st.session_state.view_url = None
        st.rerun()


@st.dialog("笔记内容", width="large")
def _show_note_dialog(db_path):
    from web.db import get_db
    nid = st.session_state.view_note
    row = get_db(db_path).execute("SELECT * FROM project_notes WHERE id = ?", (nid,)).fetchone()
    if row:
        st.subheader(row["title"])
        st.markdown(row["content"])
    if st.button("关闭"):
        st.session_state.view_note = None
        st.rerun()


# ═══════════════════════════════════════════════════════════════════
# 主区域 — 对话
# ═══════════════════════════════════════════════════════════════════

def _render_main_chat(db_path, user_id, project_id, agent_config):
    if project_id is None:
        st.info("👈 请先在左侧选择一个项目，或点击「🆕 新建项目」创建一个")
        return

    # 对话历史
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 输入
    q = st.chat_input("基于左侧勾选的数据源提问...")
    if q:
        st.session_state.chat_messages.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)

        context = _build_context(db_path)
        if not context.strip():
            with st.chat_message("assistant"):
                st.warning("请在左侧边栏勾选至少一个数据源")
            st.stop()

        if st.session_state.chat_session_id is None:
            st.session_state.chat_session_id = create_session(
                db_path, user_id, q, project_id=project_id, session_type="chat")
            update_session(db_path, st.session_state.chat_session_id,
                           data_sources=list(st.session_state.chat_sources))

        from agent.chat_agent import build_chat_agent
        chat_agent = build_chat_agent(
            data_context=context,
            model=agent_config["llm"]["model"],
            api_key=agent_config["llm"]["api_key"],
            base_url=agent_config["llm"].get("base_url", "https://api.deepseek.com/v1"),
        )

        full_msgs = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_messages]
        with st.chat_message("assistant"):
            placeholder = st.empty()
            acc = []
            try:
                for chunk in chat_agent.stream({"messages": full_msgs}, stream_mode="updates"):
                    for _, update in chunk.items():
                        for msg in update.get("messages", []):
                            if hasattr(msg, "content") and msg.content and isinstance(msg.content, str) and msg.content.strip():
                                acc.append(msg.content.strip())
                                placeholder.markdown("".join(acc))
                final = "".join(acc)
                st.session_state.chat_messages.append({"role": "assistant", "content": final or "_(无)_"})
                update_session(db_path, st.session_state.chat_session_id,
                               messages=st.session_state.chat_messages, status="completed")
            except Exception as e:
                st.session_state.chat_messages.append({"role": "assistant", "content": f"❌ {e}"})
                placeholder.markdown(f"❌ {e}")


def _build_context(db_path):
    parts = []

    # 调研结果
    for sid in st.session_state.get("chat_sources", set()):
        sess = get_session(db_path, sid)
        if sess and sess.get("report_md"):
            parts.append(f"### 来源: {sess['query']}\n\n{sess['report_md'][:5000]}")

    # URL
    from agent.chat_agent import _make_fetch_webpage
    fetch = _make_fetch_webpage()
    for url_key in st.session_state.get("chat_url_sources", set()):
        url = url_key.replace("url_", "", 1)
        result = fetch.invoke({"url": url})
        parts.append(f"### 来源: {url}\n\n{result[:5000]}")

    # 笔记
    from web.db import get_db
    for note_key in st.session_state.get("chat_note_sources", set()):
        note_id = int(note_key.replace("note_", "", 1))
        row = get_db(db_path).execute("SELECT * FROM project_notes WHERE id = ?", (note_id,)).fetchone()
        if row:
            parts.append(f"### 笔记: {row['title']}\n\n{row['content'][:5000]}")

    return "\n\n---\n\n".join(parts)
