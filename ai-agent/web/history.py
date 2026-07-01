"""历史记录浏览 — 项目树形组织。"""

import streamlit as st
from web.db import list_projects, list_sessions, get_session, delete_session
from web.components import report_view


def render(db_path: str):
    user = st.session_state.get("user", {})
    user_id = user.get("id", 0)

    st.title("📋 研究历史")

    projects = list_projects(db_path, user_id)

    # 未分类
    orphans = list_sessions(db_path, user_id, project_id=0)
    if orphans:
        with st.expander(f"📁 未分类 ({len(orphans)})", expanded=True):
            _render_sessions(db_path, orphans)

    # 各项目
    for p in projects:
        sessions = list_sessions(db_path, user_id, project_id=p["id"])
        with st.expander(f"📁 {p['name']} ({len(sessions)})", expanded=False):
            _render_sessions(db_path, sessions)


def _render_sessions(db_path, sessions):
    for s in sessions:
        status_icon = {"completed": "✅", "running": "🔄", "failed": "❌"}.get(s["status"], "❓")
        type_icon = "💬" if s["type"] == "chat" else "🔬"
        created = s["created_at"][:16] if s["created_at"] else ""
        expander_label = f"{status_icon} {type_icon} {created}  {s['query'][:50]}"

        col_exp, col_del = st.columns([20, 1])
        with col_exp:
            with st.expander(expander_label):
                sess = get_session(db_path, s["id"])
                if sess and sess.get("report_md"):
                    report_view.render(sess["report_md"])
                elif sess and sess.get("messages"):
                    # 对话模式显示对话历史
                    for msg in sess["messages"]:
                        role = "🧑" if msg["role"] == "user" else "🤖"
                        st.caption(f"{role} {msg['content'][:200]}")
                else:
                    st.caption("正在生成中...")
        with col_del:
            if st.button("🗑️", key=f"hist_del_{s['id']}", help="删除"):
                delete_session(db_path, s["id"])
                st.rerun()
