"""报告渲染组件。"""

import streamlit as st


def render(markdown: str):
    """渲染 Markdown 报告。"""
    if not markdown:
        st.info("暂无报告")
        return
    st.markdown(markdown, unsafe_allow_html=False)


def render_streaming(message: str, container, accumulated: list):
    """追加流式 AI 文本到容器。"""
    accumulated.append(message)
    container.markdown("".join(accumulated))
