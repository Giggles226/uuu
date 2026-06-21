# 🍺 AI 酒馆竞技场 (AI Tavern Arena)

> 可定制规则的多模型博弈竞技平台 · 远程 API · 自动快照暂停恢复 · 上下文压缩还原

**Flet / Python 重构版** — 原项目 [Giggles226/en](https://github.com/Giggles226/en) 是 React + Tauri，
本仓库使用 [Flet](https://flet.dev) (Python + Flutter) 完整重写，**专注于打包 Android APK**。

---

## 这是什么？

一个让 **2-24 个 AI 大模型同台竞技** 的应用。你可以自由定义比赛规则，让不同厂商的模型互相较量，
由裁判模型评判胜负。支持 OpenAI、Anthropic、Gemini、豆包、文心一言、通义千问、混元、Kimi、智谱、阶跃星辰等
所有主流平台。

## 与原版区别

| 项 | 原版 (en) | 本版 (uuu) |
|---|---|---|
| 框架 | React 19 + Tauri 2 (Rust) | **Flet 0.85 (Python + Flutter)** |
| 状态管理 | Zustand | `ArenaState` dataclass + `page.update()` |
| 持久化 | localStorage | **JSON 文件** (适配 Android 私有目录) |
| 本地 LLM | Ollama (Tauri 后端管理) | ❌ 不支持（纯远程 API） |
| 打包 | `npm run tauri build` → EXE | **`flet build apk` → APK** |
| 主要语言 | TypeScript | **Python 3.10+** |

## 核心特性

| 能力 | 说明 |
|---|---|
| 🤖 多模型竞技 | 2-24 个模型同时参赛，不限厂商 |
| 📜 自由规则 | 完全自定义比赛规则，每轮自动注入给所有模型 |
| 👑 裁判 Agent | 私人对话 + 淘汰判定 + 公共发言 |
| 🔄 协议归一化 | **统一 LLM 协议层** — 各厂商 API 协议双向转换 |
| ⏸️ 智能暂停 | 额度耗尽自动暂停，保存全量快照 |
| 🗜️ 上下文压缩 | 恢复时压缩历史摘要 + 当前轮完整上下文 |
| 💾 配置持久化 | 模型配置 + 规则 + 快照自动保存 |
| 📱 Android | 一键打包 APK |

## 🔄 协议归一化（核心设计）

各厂商 API 协议差异巨大（OpenAI、Anthropic 把 system 抽离，Gemini 用 `parts`/`systemInstruction`，百度千帆 V2 自定义字段…），
本项目实现 **"前向归一化 + 反向回译"** 模式：

```
                  ┌─────────────────────┐
                  │  UniversalRequest   │  ← 统一请求
                  │  - model            │
                  │  - messages[]       │
                  │  - temperature      │
                  │  - max_tokens       │
                  └──────────┬──────────┘
                             │
        ┌──────────┬─────────┼─────────┬──────────┐
        ▼          ▼         ▼         ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ OpenAI │ │Anthropic│ │ Gemini │ │  百度  │ │ 智谱…  │  ← to_provider_payload()
   │ 形态   │ │  形态   │ │  形态  │ │  形态  │ │  形态  │     （前向：归一化 → 厂商）
   └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘
        │          │         │         │          │
        ▼          ▼         ▼         ▼          ▼
   各厂商 HTTP API  （Bearer / x-api-key / x-goog-api-key …）
        │          │         │         │          │
        ▼          ▼         ▼         ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ 厂商响应│ │ 厂商响应│ │ 厂商响应│ │ 厂商响应│ │ 厂商响应│
   └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘ └────┬───┘
        │          │         │         │          │
        └──────────┴─────────┼─────────┴──────────┘
                             ▼
                  ┌─────────────────────┐
                  │ UniversalResponse   │  ← 统一响应
                  │  - content          │
                  │  - usage            │
                  │  - raw              │
                  └─────────────────────┘     （反向：厂商 → 归一化）
```

调用方（裁判 / 竞技场）只跟 `UniversalRequest` / `UniversalResponse` 打交道，**完全不知道底下是 OpenAI、Anthropic 还是文心**。

详见 [SPEC.md](./SPEC.md) 和 [arena/llm/base.py](./arena/llm/base.py)。

## 快速开始

### 桌面端开发

```bash
# 1. 克隆
git clone https://github.com/Giggles226/uuu.git
cd uuu

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行
python main.py
# 或
flet run main.py
```

### 打包 Android APK

```bash
# 安装 Flet CLI（已包含在 flet 包中）
pip install flet

# 初始化 Android 项目（首次）
flet create .

# 构建 APK
flet build apk
# 产物在: build/apk/app-release.apk
```

> 注：完整 APK 构建需要本地安装 Android SDK / NDK / Java 17。
> Flet 官方文档：<https://flet.dev/docs/guides/python/packaging-android-app>

### 运行测试

```bash
PYTHONPATH=. python tests/test_smoke.py
```

## 使用指南

1. **配置全局 API Key** — 点击"全局 API Key → 管理"，填入各厂商的 Key（也可以在添加模型时单独填）
2. **添加参赛模型** — "+ 添加"，选 API 类型、模型名。可选 2-24 个。
3. **指定裁判** — 点击模型行的 👑 图标，设为裁判。
4. **（可选）编辑规则** — 自定义比赛规则、评分标准、私人对话回合数。
5. **输入问题并开始** — 点 "🚀 开始游戏"。

## 项目结构

```
uuu/
├── main.py                       # Flet 应用入口
├── requirements.txt
├── README.md
├── SPEC.md                       # 架构规范
├── arena/                        # 核心业务逻辑（与 UI 解耦）
│   ├── models.py                 # 数据模型
│   ├── storage.py                # JSON 持久化
│   ├── state.py                  # 竞技场状态机
│   ├── compression.py            # 上下文压缩
│   ├── snapshot.py               # 快照 / 暂停 / 恢复
│   ├── judge.py                  # 裁判 Agent
│   ├── arena_logic.py            # 主游戏循环
│   └── llm/                      # 统一 LLM 协议层 ⭐
│       ├── base.py               # Universal* + 各厂商 Adapter
│       └── router.py             # 路由 + 凭证解析
├── ui/                           # Flet UI
│   ├── arena_view.py             # 主视图
│   ├── config_panel.py           # 模型 / API Key 配置
│   ├── rule_editor.py            # 规则编辑器
│   ├── snapshot_panel.py         # 快照面板
│   └── utils.py
├── tests/
│   └── test_smoke.py             # 11 个 smoke test
└── storage/                      # 运行时 JSON 数据
```

## 技术栈

- **Python** 3.10+
- **Flet** 0.25+ (Flutter for Python)
- **httpx** (异步 HTTP 客户端，支持超时与重试)

## API 厂商矩阵

| 厂商 | 协议适配器 | 端点 |
|---|---|---|
| OpenAI / 通用 | `OpenAICompatAdapter` | `https://api.openai.com/v1/chat/completions` |
| 火山引擎 (豆包) | `OpenAICompatAdapter` | `https://ark.cn-beijing.volces.com/api/v3/...` |
| 阿里 (通义) | `OpenAICompatAdapter` | `https://dashscope.aliyuncs.com/compatible-mode/v1/...` |
| 月之暗面 (Kimi) | `OpenAICompatAdapter` | `https://api.moonshot.cn/v1/...` |
| 智谱 (GLM) | `ZhipuAdapter` | `https://open.bigmodel.cn/api/paas/v4/...` |
| 阶跃星辰 | `StepFunAdapter` | `https://api.stepfun.com/v1/...` |
| 腾讯 (混元) | `HunyuanAdapter` | `https://api.hunyuan.cloud.tencent.com/v1/...` |
| 百度 (文心) | `BaiduAdapter` | `https://qianfan.baidubce.com/v2/...` |
| Anthropic (Claude) | `AnthropicAdapter` | `https://api.anthropic.com/v1/messages` |
| Google (Gemini) | `GeminiAdapter` | `https://generativelanguage.googleapis.com/.../models/{model}:generateContent` |
| 自定义 | `CustomAdapter` | 透传 OpenAI 形态 |

## License

MIT
