from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st

from werewolf.main import _run

st.set_page_config(page_title="三国狼人杀 AgentScope", layout="wide")
st.title("三国狼人杀 AgentScope 控制台")

config_path = st.text_input("配置文件路径", value="config/game.example.yaml")
mode = st.selectbox("运行模式", options=["simulate", "llm"], index=0)
max_days = st.slider("最大天数", min_value=1, max_value=10, value=3)
seed = st.number_input("随机种子", min_value=1, value=42)

if st.button("开始游戏"):
    try:
        result = asyncio.run(_run(config_path, mode, max_days, int(seed), "logs"))
        st.success(f"对局完成，胜者：{result['winner']}")
        st.json(result)
    except Exception as exc:
        st.error(f"运行失败：{exc}")

logs_dir = Path("logs")
logs_dir.mkdir(parents=True, exist_ok=True)
log_files = sorted(logs_dir.glob("run_*.log"), reverse=True)
st.subheader("历史日志")
for lf in log_files[:10]:
    with st.expander(lf.name, expanded=False):
        st.code(lf.read_text(encoding="utf-8"), language="json")
