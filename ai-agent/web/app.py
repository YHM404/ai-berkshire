"""AI Berkshire Agent — Web 入口。"""

import os
import sys
from pathlib import Path

# 确保项目根在 path 中
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

import streamlit as st
import yaml

from web.db import init_db, create_user, get_user_count, verify_user
from web import research, history

# ── 页面配置 ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Berkshire Agent",
    page_icon="🏦",
    layout="wide",
)

# ── 配置加载 ──────────────────────────────────────────────────────
def load_config() -> dict:
    config_path = _project_root / "config.yaml"
    raw = config_path.read_text(encoding="utf-8")
    import re
    raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ""), raw)
    return yaml.safe_load(raw)

config = load_config()
project_root = str((_project_root / config.get("project_root", "..")).resolve())

# 环境变量检查
if not config["llm"]["api_key"]:
    st.error("❌ DEEPSEEK_API_KEY 未设置。请在环境变量或 config.yaml 中配置。")
    st.stop()

# Agent 配置（传递给页面）
agent_config = {
    "llm": config["llm"],
    "project_root": project_root,
}

# ── 数据库初始化 ──────────────────────────────────────────────────
db_path = str(_project_root / "data" / "app.db")
init_db(db_path)

# 开发模式：首次启动自动创建 admin/admin
if get_user_count(db_path) == 0:
    create_user(db_path, "admin", "admin")

# ── 自动登录 admin ──────────────────────────────────────────────
result = verify_user(db_path, "admin", "admin")
st.session_state.user = result["user"] if result["ok"] else None

# ── 路由 ──────────────────────────────────────────────────────────
research.render(db_path, agent_config)
