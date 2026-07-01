"""研究输入栏组件。"""

import streamlit as st


def render() -> tuple[str, bool]:
    """渲染顶部输入栏，返回 (query, submitted)。"""
    col1, col2 = st.columns([5, 1])
    with col1:
        query = st.text_input(
            "研究问题",
            placeholder="例如：分析苹果产业链上游公司、对腾讯做一次投资研究...",
            label_visibility="collapsed",
            key="query_input",
        )
    with col2:
        submitted = st.button("开始分析", type="primary", use_container_width=True)
    return query, submitted
