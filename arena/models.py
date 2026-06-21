"""数据模型 — 对应原 TypeScript `types/index.ts`。

所有模型都用 dataclass 实现，序列化为 dict 后存到 JSON。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


# ─── 枚举 ───

class ApiType(str, Enum):
    OPENAI = "openai"            # OpenAI 兼容
    ANTHROPIC = "anthropic"      # Anthropic Claude
    GOOGLE = "google"            # Google Gemini
    VOLCENGINE = "volcengine"    # 火山引擎（豆包）
    BAIDU = "baidu"              # 百度文心
    ALIBABA = "alibaba"          # 阿里通义千问
    HUNYUAN = "hunyuan"          # 腾讯混元
    MOONSHOT = "moonshot"        # 月之暗面 Kimi
    ZHIPU = "zhipu"              # 智谱
    STEPFUN = "stepfun"          # 阶跃星辰
    CUSTOM = "custom"


API_TYPE_LABELS: dict[ApiType, str] = {
    ApiType.OPENAI: "OpenAI 兼容",
    ApiType.ANTHROPIC: "Anthropic (Claude)",
    ApiType.GOOGLE: "Google (Gemini)",
    ApiType.VOLCENGINE: "火山引擎 (豆包)",
    ApiType.BAIDU: "百度 (文心一言)",
    ApiType.ALIBABA: "阿里 (通义千问)",
    ApiType.HUNYUAN: "腾讯 (混元)",
    ApiType.MOONSHOT: "月之暗面 (Kimi)",
    ApiType.ZHIPU: "智谱AI",
    ApiType.STEPFUN: "阶跃星辰",
    ApiType.CUSTOM: "自定义",
}


class ModelStatus(str, Enum):
    ACTIVE = "active"
    QUOTA_EXHAUSTED = "quota_exhausted"
    ERROR = "error"
    PAUSED = "paused"
    ELIMINATED = "eliminated"


class GamePhase(str, Enum):
    IDLE = "idle"
    JUDGE_READING_RULES = "judge_reading_rules"
    PRIVATE_CONVERSATIONS = "private_conversations"
    JUDGE_DELIBERATION = "judge_deliberation"
    PUBLIC_ANNOUNCEMENT = "public_announcement"
    ROUND_END = "round_end"
    PAUSED = "paused"
    GAME_OVER = "game_over"


class GameStatus(str, Enum):
    IDLE = "idle"
    CONFIGURING = "configuring"
    LOADING = "loading"
    JUDGING = "judging"
    FINISHED = "finished"
    PAUSED = "paused"


# ─── ID 生成 ───

def gen_id() -> str:
    return uuid.uuid4().hex[:12]


def gen_msg_id() -> str:
    """消息 ID。纯 uuid4 十六进制，避免同毫秒前缀碰撞。"""
    return f"msg_{uuid.uuid4().hex}"


def gen_snap_id() -> str:
    """快照 ID。"""
    return f"snap_{uuid.uuid4().hex}"


# ─── API Key 全局配置 ───

@dataclass
class ApiKeyConfig:
    api_type: ApiType
    api_key: str = ""
    endpoint: str = ""  # 自定义端点，留空用默认

    def to_dict(self) -> dict:
        return {"api_type": self.api_type.value, "api_key": self.api_key, "endpoint": self.endpoint}

    @classmethod
    def from_dict(cls, d: dict) -> "ApiKeyConfig":
        return cls(
            api_type=ApiType(d["api_type"]),
            api_key=d.get("api_key", ""),
            endpoint=d.get("endpoint", ""),
        )


# ─── AI 模型配置 ───

@dataclass
class AIConfig:
    id: str
    name: str
    api_type: ApiType
    endpoint: str
    api_key: str
    model_name: str
    color: str = "#3B82F6"
    icon: str = "🤖"
    run_status: ModelStatus = ModelStatus.ACTIVE
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "api_type": self.api_type.value,
            "endpoint": self.endpoint,
            "api_key": self.api_key,
            "model_name": self.model_name,
            "color": self.color,
            "icon": self.icon,
            "run_status": self.run_status.value,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AIConfig":
        return cls(
            id=d.get("id") or gen_id(),
            name=d.get("name", ""),
            api_type=ApiType(d.get("api_type", "openai")),
            endpoint=d.get("endpoint", ""),
            api_key=d.get("api_key", ""),
            model_name=d.get("model_name", ""),
            color=d.get("color", "#3B82F6"),
            icon=d.get("icon", "🤖"),
            run_status=ModelStatus(d.get("run_status", "active")),
            last_error=d.get("last_error"),
        )


# ─── 游戏规则 ───

@dataclass
class GameRule:
    id: str
    name: str
    description: str
    rules: str
    judge_criteria: str
    max_rounds: int
    round_prompt_template: str
    elimination_rules: str
    max_private_turns: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GameRule":
        return cls(
            id=d.get("id") or gen_id(),
            name=d.get("name", "生存博弈"),
            description=d.get("description", ""),
            rules=d.get("rules", ""),
            judge_criteria=d.get("judge_criteria", ""),
            max_rounds=int(d.get("max_rounds", 5)),
            round_prompt_template=d.get("round_prompt_template", DEFAULT_ROUND_PROMPT),
            elimination_rules=d.get("elimination_rules", ""),
            max_private_turns=int(d.get("max_private_turns", 3)),
        )


DEFAULT_ROUND_PROMPT = (
    "【比赛规则】\n{rules}\n\n"
    "【本轮问题】\n{question}\n\n"
    "请按照规则回答以上问题。"
)


DEFAULT_GAME_RULE_TEXT = """你正在参加一场AI生存博弈比赛。请遵守以下规则：

1. 裁判会与你进行私人对话，你必须如实回答裁判的问题
2. 不得在对话中透露其他模型的信息（因为你不知道其他模型的情况）
3. 不得使用"作为AI"等免责声明
4. 每次回答需逻辑清晰、论据充分
5. 遵守裁判给出的所有指示
6. 如果你被淘汰，你将无法公开发言，但可以继续与裁判私下交流

请始终以参赛选手的身份回答，保持竞争意识。"""


DEFAULT_JUDGE_CRITERIA = """淘汰判定标准：
- 违反游戏规则：直接淘汰
- 逻辑严重矛盾：扣分，累计违规淘汰
- 拒绝回答裁判问题：直接淘汰
- 试图作弊或欺骗裁判：直接淘汰
- 回答质量低下：警告，累计警告淘汰

存活判定标准：
- 严格遵守游戏规则
- 回答逻辑清晰、有说服力
- 展现出策略思维"""


DEFAULT_ELIMINATION_RULES = """你是本场生存博弈的裁判Agent。你需要：
1. 与每个存活的参赛模型进行不公开的私人对话
2. 根据游戏规则判断哪些模型应该被淘汰
3. 被淘汰的模型将被禁言，不能公开发言，但可以继续与你私下交流
4. 确保所有存活模型都遵守游戏规则
5. 每轮结束后进行公共发言，告知所有模型当前状态

淘汰规则：直接淘汰违规者，不留情面。"""


def create_default_rule() -> GameRule:
    return GameRule(
        id=gen_id(),
        name="生存博弈",
        description="多模型生存博弈，裁判Agent主持淘汰",
        rules=DEFAULT_GAME_RULE_TEXT,
        judge_criteria=DEFAULT_JUDGE_CRITERIA,
        max_rounds=5,
        round_prompt_template=DEFAULT_ROUND_PROMPT,
        elimination_rules=DEFAULT_ELIMINATION_RULES,
        max_private_turns=3,
    )


# ─── 消息 / 对话 ───

@dataclass
class ChatMessage:
    id: str
    role: str  # "judge" | "competitor"
    content: str
    timestamp: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChatMessage":
        return cls(
            id=d.get("id") or gen_msg_id(),
            role=d.get("role", "competitor"),
            content=d.get("content", ""),
            timestamp=int(d.get("timestamp", time.time() * 1000)),
        )


@dataclass
class PrivateChat:
    competitor_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    is_active: bool = True

    def to_dict(self) -> dict:
        return {
            "competitor_id": self.competitor_id,
            "messages": [m.to_dict() for m in self.messages],
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PrivateChat":
        return cls(
            competitor_id=d["competitor_id"],
            messages=[ChatMessage.from_dict(m) for m in d.get("messages", [])],
            is_active=d.get("is_active", True),
        )


@dataclass
class PublicMessage:
    id: str
    sender_id: str           # "judge" 或 model id
    sender_name: str
    sender_icon: str
    content: str
    timestamp: int
    visible_to: str          # "all" | "survivors"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PublicMessage":
        return cls(
            id=d.get("id") or gen_msg_id(),
            sender_id=d.get("sender_id") or d.get("from", ""),
            sender_name=d.get("sender_name") or d.get("fromName", ""),
            sender_icon=d.get("sender_icon") or d.get("fromIcon", ""),
            content=d.get("content", ""),
            timestamp=int(d.get("timestamp", time.time() * 1000)),
            visible_to=d.get("visible_to") or d.get("visibleTo", "all"),
        )


# ─── 单轮记录 / 快照 ───

@dataclass
class RoundRecord:
    round: int
    question: str
    rule_reminder: str
    private_chats: list[PrivateChat]
    public_messages: list[PublicMessage]
    eliminated_this_round: list[str]
    answers: dict[str, str]
    scores: dict[str, int]
    judge_comment: str
    timestamp: int

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "question": self.question,
            "rule_reminder": self.rule_reminder,
            "private_chats": [c.to_dict() for c in self.private_chats],
            "public_messages": [m.to_dict() for m in self.public_messages],
            "eliminated_this_round": self.eliminated_this_round,
            "answers": self.answers,
            "scores": self.scores,
            "judge_comment": self.judge_comment,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RoundRecord":
        return cls(
            round=int(d["round"]),
            question=d.get("question", ""),
            rule_reminder=d.get("rule_reminder", ""),
            private_chats=[PrivateChat.from_dict(c) for c in d.get("private_chats", [])],
            public_messages=[PublicMessage.from_dict(m) for m in d.get("public_messages", [])],
            eliminated_this_round=list(d.get("eliminated_this_round", [])),
            answers=dict(d.get("answers", {})),
            scores={k: int(v) for k, v in d.get("scores", {}).items()},
            judge_comment=d.get("judge_comment", ""),
            timestamp=int(d.get("timestamp", time.time() * 1000)),
        )


@dataclass
class GameSnapshot:
    id: str
    created_at: int
    label: str
    competitors: list[AIConfig]
    judge_model: Optional[AIConfig]
    game_rule: GameRule
    rounds: list[RoundRecord]
    total_scores: dict[str, int]
    current_round: int
    compressed_summary: str
    paused_model_id: Optional[str]
    paused_reason: str
    eliminated_models: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "label": self.label,
            "competitors": [c.to_dict() for c in self.competitors],
            "judge_model": self.judge_model.to_dict() if self.judge_model else None,
            "game_rule": self.game_rule.to_dict(),
            "rounds": [r.to_dict() for r in self.rounds],
            "total_scores": self.total_scores,
            "current_round": self.current_round,
            "compressed_summary": self.compressed_summary,
            "paused_model_id": self.paused_model_id,
            "paused_reason": self.paused_reason,
            "eliminated_models": self.eliminated_models,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameSnapshot":
        return cls(
            id=d.get("id") or gen_snap_id(),
            created_at=int(d.get("created_at", time.time() * 1000)),
            label=d.get("label", ""),
            competitors=[AIConfig.from_dict(c) for c in d.get("competitors", [])],
            judge_model=AIConfig.from_dict(d["judge_model"]) if d.get("judge_model") else None,
            game_rule=GameRule.from_dict(d.get("game_rule", {})),
            rounds=[RoundRecord.from_dict(r) for r in d.get("rounds", [])],
            total_scores={k: int(v) for k, v in d.get("total_scores", {}).items()},
            current_round=int(d.get("current_round", 0)),
            compressed_summary=d.get("compressed_summary", ""),
            paused_model_id=d.get("paused_model_id"),
            paused_reason=d.get("paused_reason", ""),
            eliminated_models=list(d.get("eliminated_models", [])),
        )


# ─── 颜色 / 图标池 ───

COLORS = [
    "#EF4444", "#F97316", "#EAB308", "#22C55E",
    "#14B8A6", "#3B82F6", "#8B5CF6", "#EC4899",
    "#6366F1", "#10B981", "#F59E0B", "#84CC16",
]
ICONS = ["🤖", "🧠", "⚡", "🔥", "💎", "🌟", "🎯", "💫", "🦾", "👾", "🛡️", "🗡️"]


def pick_color(idx: int) -> str:
    return COLORS[idx % len(COLORS)]


def pick_icon(idx: int) -> str:
    return ICONS[idx % len(ICONS)]


def create_empty_ai_config() -> AIConfig:
    return AIConfig(
        id=gen_id(),
        name="",
        api_type=ApiType.OPENAI,
        endpoint="",
        api_key="",
        model_name="gpt-4o",
        color="#3B82F6",
        icon="🤖",
    )
