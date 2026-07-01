"""执行步骤实时展示组件。"""

import streamlit as st
from datetime import datetime


def init():
    """初始化 session state 中的执行日志。"""
    if "execution_steps" not in st.session_state:
        st.session_state.execution_steps = []


def add_step(step_type: str, detail: str, status: str = "info"):
    """添加一条执行步骤。
    
    step_type: "tool_call", "tool_result", "ai_message"
    status: "info", "success", "error", "warning"
    """
    st.session_state.execution_steps.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "type": step_type,
        "detail": detail,
        "status": status,
    })


def clear():
    st.session_state.execution_steps = []


def render():
    """渲染执行步骤日志。"""
    steps = st.session_state.get("execution_steps", [])
    if not steps:
        st.info("等待开始分析...")
        return

    emoji = {"tool_call": "🔧", "tool_result": "   ↳", "ai_message": "🤖", "error": "❌"}

    for step in steps:
        icon = emoji.get(step["type"], "•")
        if step["status"] == "error":
            st.error(f"{step['time']} {icon} {step['detail']}")
        elif step["status"] == "warning":
            st.warning(f"{step['time']} {icon} {step['detail']}")
        else:
            # 折叠工具结果，只显示预览
            detail = step["detail"]
            if step["type"] == "tool_result" and len(detail) > 200:
                with st.expander(f"{step['time']} {icon} {detail[:100]}..."):
                    st.text(detail)
            else:
                st.caption(f"{step['time']} {icon} {detail}")
