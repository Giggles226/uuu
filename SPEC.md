# AI 酒馆竞技场 (uuu) — 架构规范 v1.0

> Flet / Python 重构版。基于 [Giggles226/en](https://github.com/Giggles226/en) 的 TypeScript 原版改写。

## 1. 架构总览

```
┌────────────────────────────────────────────────────────────┐
│                    Flet UI (ui/)                           │
│  arena_view · config_panel · rule_editor · snapshot_panel  │
└──────────────┬─────────────────────────────────────────────┘
               │ 读取/订阅
               ▼
┌────────────────────────────────────────────────────────────┐
│              Arena 业务层 (arena/)                         │
│  state · arena_logic · judge · snapshot · compression      │
└──────────────┬─────────────────────────────────────────────┘
               │ 调用
               ▼
┌────────────────────────────────────────────────────────────┐
│         统一 LLM 协议层 (arena/llm/) ⭐ 核心                │
│   UniversalRequest ──►  Adapter  ──►  HTTP                │
│   UniversalResponse ◄──  Adapter  ◄──  HTTP                │
└──────────────┬─────────────────────────────────────────────┘
               │ 持久化
               ▼
┌────────────────────────────────────────────────────────────┐
│         Storage (JSON 文件 / Android 私有目录)             │
│   api_keys · competitors · judge · rule · rounds · snaps    │
└────────────────────────────────────────────────────────────┘
```

## 2. 核心设计：协议归一化层

### 2.1 数据结构

```python
@dataclass
class UniversalRequest:
    model: str
    messages: list[UniversalMessage]  # [{role, content}, ...]
    temperature: float = 0.7
    max_tokens: int = 4096
    extras: dict  # 厂商特有字段透传

@dataclass
class UniversalResponse:
    content: str
    usage: Optional[dict]
    raw: Optional[dict]  # 厂商原始响应
```

### 2.2 适配器接口

```python
class BaseAdapter:
    api_type: ApiType
    default_endpoint: str
    uses_model_placeholder: bool

    def build_headers(self, api_key) -> dict
    def to_provider_payload(self, req: UniversalRequest) -> dict   # 前向
    def from_provider_payload(self, payload: dict) -> UniversalResponse  # 反向
    def call(self, api_key, endpoint, req, timeout) -> UniversalResponse
```

### 2.3 各厂商差异点

| 厂商 | 关键差异 | Adapter 处理 |
|---|---|---|
| OpenAI | `Authorization: Bearer` + 标准 `messages` | 直接转发 |
| Anthropic | `x-api-key` + `system` 抽离 + `anthropic-version` | `to_provider_payload` 把 system 抽出来 |
| Gemini | `x-goog-api-key` + `systemInstruction` + `parts` + `{model}` 占位符 | system 转 `systemInstruction.parts`，messages 转 `contents.parts` |
| 百度 | 千帆 V2 形态与 OpenAI 相似但端点独立 | 直接 OpenAI 形态 |
| 智谱 / 阶跃 / 混元 | 与 OpenAI 高度相似 | 各自端点独立 |
| 火山 / 通义 / Kimi | 完全 OpenAI 兼容 | 共享 `OpenAICompatAdapter` |
| 自定义 | 用户自定义端点 | 透传 OpenAI 形态 |

## 3. 数据模型

```python
AIConfig       # 单个模型配置
GameRule       # 游戏规则
ChatMessage    # 单条消息（私人对话）
PrivateChat    # 私人会话（含 isActive）
PublicMessage  # 公共发言
RoundRecord    # 单轮记录
GameSnapshot   # 完整快照（用于暂停/恢复）
```

## 4. 游戏状态机

```
IDLE
  ↓ start_round
JUDGE_READING_RULES  ── 0.5s ──►  PRIVATE_CONVERSATIONS
                                              │
                  ┌───────────────────────────┘
                  │ judge 与每个存活选手进行 N 轮私人对话
                  │ 收集所有对话后
                  ▼
              JUDGE_DELIBERATION  ──►  PUBLIC_ANNOUNCEMENT
                                              │
                                              ▼
                                          ROUND_END
                                              │
                              survivors <= 1 │ round+1 < max
                                              ▼
                                          GAME_OVER
```

任何阶段检测到某模型**额度耗尽**（HTTP 429/402 或响应体包含 quota/billing/balance 关键词）→ 自动 `PAUSED` + 保存快照。

## 5. 暂停 / 恢复机制

### 暂停（自动）

触发条件：模型返回 `is_quota_error=True`。
操作：
1. 深拷贝全部状态（competitors / judge / rule / rounds / scores / eliminated）
2. 计算 `compressed_summary`（所有历史的精简文本）
3. 写入 `snapshots.json`
4. `state.status = PAUSED`

### 恢复（手动）

用户点击"▶ 恢复游戏" → 加载最新快照 → 还原所有状态 → 全部 `runStatus = active`。

### 上下文压缩

恢复后下一轮的 `roundPromptTemplate` 会自动注入：
```
【历史回合摘要】
<compressed_summary>

【上一轮回顾】
问题: ...
裁判点评: ...

请继续遵守比赛规则，参加下一轮。
```

## 6. 持久化

桌面端：`./storage/*.json`
Android：`flet.app_storage_path()`（应用私有目录）

| 文件 | 内容 |
|---|---|
| `api_keys.json` | 全局 API Key 配置（CC Switch 风格） |
| `competitors.json` | 参赛模型列表 |
| `judge_model.json` | 裁判模型 |
| `game_rule.json` | 当前规则 |
| `rounds.json` | 历史回合记录 |
| `total_scores.json` | 累计积分 |
| `arena_state.json` | 临时状态（eliminated/round 等） |
| `snapshots.json` | 完整快照列表 |

## 7. UI 设计

- 框架：Flet 0.85
- 主题：Material 3 Dark（`ft.ThemeMode.DARK`）
- 布局：垂直 `Column`，移动端友好（`ResponsiveRow`）
- 卡片样式：半透明背景 + 圆角 + 细边框（"glass card"）
- 响应式：每个面板自带 `state.on_change(refresh)` 回调

## 8. 异步模型

- 同步路径：UI 事件 → `state.xxx()` → 改 dataclass → `notify()` → `page.update()`
- 异步路径：游戏主循环用 `page.run_task(_drive_loop)` 启动 asyncio 协程

```python
async def _drive_loop():
    while state.status == LOADING:
        await runner.tick()         # 推进一阶段
        await asyncio.sleep(0.05)   # 让出控制权
```

## 9. 测试

`tests/test_smoke.py` 覆盖：
- 数据模型序列化往返
- 存储 CRUD
- 状态机生命周期
- **协议归一化（核心）** — 11 个厂商的双向转换
- 端点表完整性
- 额度关键字检测（中文 + 英文）
- 快照创建 / 恢复
- 上下文压缩
- JSON 提取容错
- 路由分发

运行：`PYTHONPATH=. python tests/test_smoke.py`

## 10. 已知限制 / 后续工作

- ❌ 不支持本地 LLM（Ollama / llama.cpp）— 纯远程 API
- ❌ 流式输出（所有模型走完整响应再展示）
- ❌ 音频 / 多模态
- ⏳ 实际 Android APK 构建需要在本地配置 Android SDK
- ⏳ UI 动画与原版 glass-morphism 风格略有差异（Flet Material 限制）

## 11. 与原版（en）的对应关系

| 原 TS 文件 | 本 Py 文件 |
|---|---|
| `src/types/index.ts` | `arena/models.py` |
| `src/stores/arenaStore.ts` | `arena/state.py` |
| `src/services/apiKeyManager.ts` | `arena/storage.py` + `arena/llm/router.py` |
| `src/services/ai_adapters/universal.ts` | `arena/llm/base.py` + `arena/llm/router.py` |
| `src/components/Arena.tsx` | `ui/arena_view.py` + `arena/arena_logic.py` |
| `src/components/ConfigPanel.tsx` | `ui/config_panel.py` |
| `src/components/RuleEditor.tsx` | `ui/rule_editor.py` |
| `src/components/SnapshotPanel.tsx` | `ui/snapshot_panel.py` |
