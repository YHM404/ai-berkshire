"""登录 / 注册页面。"""

import streamlit as st
from web.db import create_user, verify_user, get_user_count


def render(db_path: str) -> int | None:
    """渲染登录页，返回 user_id（成功）或 None。"""
    st.markdown("<h1 style='text-align:center'>🏦 AI Berkshire Agent</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:gray'>巴菲特-芒格-段永平-李录 价值投资研究助手</p>", unsafe_allow_html=True)
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["登录", "注册"]) if get_user_count(db_path) > 0 else (None, None)

        if get_user_count(db_path) == 0:
            # 首次使用 → 直接注册管理员
            st.info("首次使用，请创建管理员账号")
            username = st.text_input("用户名", key="reg_first_user")
            password = st.text_input("密码", type="password", key="reg_first_pw")
            if st.button("创建账号", type="primary", use_container_width=True):
                if not username or not password:
                    st.error("用户名和密码不能为空")
                else:
                    result = create_user(db_path, username, password)
                    if result["ok"]:
                        st.success("账号创建成功，请登录")
                        st.rerun()
                    else:
                        st.error(result["error"])
        else:
            with tab1:
                _render_login(db_path)
            with tab2:
                _render_register(db_path)

    return None


def _render_login(db_path: str):
    username = st.text_input("用户名", key="login_user")
    password = st.text_input("密码", type="password", key="login_pw")
    if st.button("登录", type="primary", use_container_width=True):
        result = verify_user(db_path, username, password)
        if result["ok"]:
            st.session_state.user = result["user"]
            st.session_state.page = "research"
            st.rerun()
        else:
            st.error(result["error"])


def _render_register(db_path: str):
    username = st.text_input("用户名", key="reg_user")
    password = st.text_input("密码", type="password", key="reg_pw")
    if st.button("注册", type="primary", use_container_width=True):
        if not username or not password:
            st.error("用户名和密码不能为空")
        elif len(password) < 4:
            st.error("密码至少 4 位")
        else:
            result = create_user(db_path, username, password)
            if result["ok"]:
                st.success("注册成功！请切换到登录页")
            else:
                st.error(result["error"])
