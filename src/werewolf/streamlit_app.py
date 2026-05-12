"""三国狼人杀 Streamlit 控制台 —— 支持游戏运行与历史日志回放。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import streamlit as st

from werewolf.config import resolve_config_path
from werewolf.log_formatter import LogFormatter, ROLE_LABELS
from werewolf.main import _run

st.set_page_config(page_title="三国狼人杀 AgentScope", layout="wide")
st.title("🐺 三国狼人杀 · AgentScope 控制台")

# ---- Sidebar: Run new game ----
with st.sidebar:
    st.header("🎮 开始新对局")
    config_path = st.text_input("配置文件", value="config/game.example.yaml")
    mode = st.selectbox("运行模式", options=["simulate", "llm"], index=0,
                        help="simulate=随机决策(测试用), llm=大模型驱动")
    max_days = st.slider("最大天数", min_value=1, max_value=10, value=3)
    seed = st.number_input("随机种子", min_value=1, value=42)

    if st.button("▶️ 开始游戏", type="primary", use_container_width=True):
        try:
            resolved = resolve_config_path(config_path)
            with st.spinner("对局进行中..."):
                result = asyncio.run(
                    _run(str(resolved), mode, max_days, int(seed), "logs")
                )
            st.session_state["last_result"] = result
            st.session_state["last_log"] = result.get("log_path", "")
            st.rerun()
        except Exception as exc:
            st.error(f"运行失败：{exc}")

# ---- Tabs ----
tab_run, tab_history = st.tabs(["📋 最近对局", "📂 历史日志"])

# ---- Tab 1: Recent game ----
with tab_run:
    result = st.session_state.get("last_result")
    log_path = st.session_state.get("last_log", "")

    if not result and not log_path:
        st.info("👈 从左侧边栏开始一局新游戏，或切换到「历史日志」查看过往对局。")
    elif result:
        st.success(f"对局完成！胜者：**{result['winner']}**")
        st.caption(f"模式：{result['mode']} | 日志：{Path(result.get('log_path', '')).name}")

        readable_path = result.get("readable_log", "")
        if readable_path and Path(readable_path).exists():
            st.divider()
            st.subheader("📜 对局回放")
            st.code(Path(readable_path).read_text(encoding="utf-8"), language=None)
    elif log_path and Path(log_path).exists():
        _render_log_file(Path(log_path))

# ---- Tab 2: History ----
with tab_history:
    st.subheader("📂 历史对局日志")
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Prefer readable .txt logs, fall back to .jsonl
    readable_logs = sorted(logs_dir.glob("run_*.txt"), reverse=True)
    json_logs = sorted(logs_dir.glob("run_*.jsonl"), reverse=True)
    old_logs = sorted(logs_dir.glob("run_*.log"), reverse=True)
    all_logs = readable_logs + json_logs + old_logs

    if not all_logs:
        st.info("暂无历史日志")
    else:
        for lf in all_logs[:15]:
            stamp = lf.stem.replace("run_", "")
            is_readable = lf.suffix == ".txt"
            label = f"{'📜' if is_readable else '📋'} {stamp} ({lf.suffix})"
            with st.expander(label, expanded=False):
                if is_readable:
                    st.code(lf.read_text(encoding="utf-8"), language=None)
                else:
                    # Convert JSON log to readable on the fly
                    try:
                        fmt = LogFormatter(log_path=lf)
                        readable = fmt.render_text()
                        st.code(readable, language=None)
                    except Exception:
                        st.code(lf.read_text(encoding="utf-8"), language="json")


def _render_log_file(path: Path) -> None:
    """Render a log file as readable text in Streamlit."""
    try:
        fmt = LogFormatter(log_path=path)
        readable = fmt.render_text()
        st.subheader("📜 对局回放")
        st.code(readable, language=None)
    except Exception:
        st.error("无法渲染日志文件")
