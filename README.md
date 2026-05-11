# 三国狼人杀（AgentScope）

一个基于 **AgentScope** 的完整“第 6 章风格”多智能体项目，主题为“三国人物+狼人杀”。项目包含可配置角色、结构化输出、完整日志、Docker 运行和 Streamlit 可视化界面。

## 1. 项目架构

```text
werewolf/
├─ config/
│  └─ game.example.yaml         # 游戏+模型+分布式示例配置
│  └─ model.providers.example.yaml
├─ src/werewolf/
│  ├─ config.py                 # 配置模型与加载
│  ├─ models.py                 # 结构化输出模型
│  ├─ game.py                   # 夜晚/白天核心循环 + MsgHub/fanout_pipeline
│  ├─ distributed.py            # 分布式执行钩子（模拟/多进程预留）
│  ├─ logger.py                 # 对局日志落盘
│  ├─ main.py                   # CLI 入口
│  └─ streamlit_app.py          # UI 页面
├─ tests/
├─ Dockerfile
├─ docker-compose.yml
├─ requirements.txt
└─ .env.example
```

核心机制：
- **消息驱动**：使用 `MsgHub` + `fanout_pipeline` 在讨论阶段广播消息。
- **结构化输出约束**：使用 Pydantic 模型（`DiscussionModelCN`、`WerewolfKillModelCN`、`WitchActionModelCN`、`VoteModelCN` 等）。
- **核心流程完整**：夜晚（狼人讨论/刀人、预言家查验、女巫行动）→ 白天（讨论、投票）循环。
- **角色提示词融合三国性格**：每个玩家使用“身份 + 三国性格”提示约束策略。
- **容错**：讨论和广播环节有异常保护，单个代理异常不会直接中断全局对局。

## 2. Docker-first 运行

### 2.1 准备

```bash
cp .env.example .env
# 按需填写 OPENAI_API_KEY / OPENAI_BASE_URL 等
```

### 2.2 运行 CLI 对局

```bash
docker compose run --rm werewolf
```

### 2.3 运行 Streamlit UI

```bash
docker compose up ui
# 打开 http://localhost:8501
```

## 3. 本地运行（可选）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
python -m werewolf.main --config config/game.example.yaml --mode simulate
streamlit run src/werewolf/streamlit_app.py
```

## 4. 配置说明

`config/game.example.yaml` 支持：
- `players`: 玩家列表（`name/role/character`）
- `game.max_days`: 最大天数
- `game.mode`: `simulate` 或 `llm`
- `game.enable_distributed` + `game.distributed`: 分布式钩子
- `model`: 模型提供方与 API 配置

`config/model.providers.example.yaml` 提供了多个 OpenAI 兼容端点模板（官方/第三方/本地网关）。

可通过 CLI 覆盖：

```bash
python -m werewolf.main --config config/game.example.yaml --mode simulate --max-days 5 --seed 7
```

## 5. 日志

每次运行会生成：
- `logs/run_YYYYMMDD_HHMMSS.log`

日志记录完整多智能体关键事件：阶段切换、讨论、狼人刀人、预言家查验、女巫行动、投票和淘汰结果。

## 6. 分布式支持

当前提供 `distributed.py` 钩子抽象：
- `simulated`：单进程模拟（默认）
- `local_multiprocess`：保留接口（可接入 multiprocessing/Ray）
- `remote_stub`：保留多机调度接口（可接入 RPC / 消息队列）

多进程/多机建议：
1. 将 `run_map` 替换为实际执行器（如 Ray actor 或 Celery worker）。
2. 使用统一消息总线（Redis/Kafka）同步玩家状态。
3. 在配置中声明 `workers` 列表并分配 player -> worker。

## 7. 免费额度模型/API 说明

可优先尝试：
- 提供试用额度的 OpenAI 兼容平台（按各平台活动为准）
- 本地开源模型 + OpenAI 兼容网关（如 vLLM / LocalAI / Ollama 网关）

如果外部免费额度不可用，推荐本地部署开源模型并填入 `.env` 中的兼容 endpoint。

## 8. 测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
