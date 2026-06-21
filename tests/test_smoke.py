"""Smoke tests for the AI Tavern Arena core modules."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from arena.models import (
    AIConfig, ApiKeyConfig, ApiType, GameRule, GameStatus,
    ModelStatus, RoundRecord, PrivateChat, ChatMessage, PublicMessage,
    create_default_rule, create_empty_ai_config, pick_color, pick_icon,
)
from arena.storage import Storage
from arena.state import ArenaState
from arena.llm import (
    BaseAdapter, UniversalRequest, UniversalMessage, UniversalResponse,
    ProviderError, looks_like_quota_error,
    get_adapter, get_default_endpoint, resolve_credentials,
)
from arena.llm.base import (
    OpenAICompatAdapter, AnthropicAdapter, GeminiAdapter,
    BaiduAdapter, HunyuanAdapter, ZhipuAdapter, StepFunAdapter,
)
from arena.llm.router import DEFAULT_ENDPOINTS
from arena.compression import compress_rounds, build_restore_context
from arena.snapshot import create_snapshot, restore_snapshot, resume_game
from arena.judge import build_rule_prompt, _extract_json
from arena.arena_logic import ArenaRunner, PHASE_LABELS


# ─── 测试 1: 数据模型序列化 ───

def test_models_serialization():
    cfg = create_empty_ai_config()
    cfg.name = "GPT-4o"
    cfg.model_name = "gpt-4o"
    d = cfg.to_dict()
    restored = AIConfig.from_dict(d)
    assert restored.name == "GPT-4o"
    assert restored.api_type == ApiType.OPENAI
    print("✓ test_models_serialization")


def test_default_rule():
    rule = create_default_rule()
    d = rule.to_dict()
    restored = GameRule.from_dict(d)
    assert restored.max_rounds == 5
    assert restored.max_private_turns == 3
    assert "{rules}" in restored.round_prompt_template
    print("✓ test_default_rule")


# ─── 测试 2: 存储 ───

def test_storage():
    tmp = tempfile.mkdtemp()
    try:
        s = Storage(tmp)
        # API keys
        s.upsert_api_key(ApiKeyConfig(ApiType.OPENAI, "sk-test", ""))
        keys = s.load_api_keys()
        assert len(keys) == 1
        assert keys[0].api_key == "sk-test"
        # 替换
        s.upsert_api_key(ApiKeyConfig(ApiType.OPENAI, "sk-new", ""))
        keys = s.load_api_keys()
        assert len(keys) == 1
        assert keys[0].api_key == "sk-new"
        # 删除
        s.delete_api_key(ApiType.OPENAI)
        assert s.load_api_keys() == []
        print("✓ test_storage")
    finally:
        shutil.rmtree(tmp)


# ─── 测试 3: 状态机 ───

def test_state_lifecycle():
    tmp = tempfile.mkdtemp()
    try:
        s = Storage(tmp)
        state = ArenaState()
        state.bind_storage(s)
        # 添加选手
        a = state.add_competitor(AIConfig(
            id="", name="A", api_type=ApiType.OPENAI, endpoint="", api_key="",
            model_name="m1", color=pick_color(0), icon=pick_icon(0),
        ))
        b = state.add_competitor(AIConfig(
            id="", name="B", api_type=ApiType.ANTHROPIC, endpoint="", api_key="",
            model_name="m2", color=pick_color(1), icon=pick_icon(1),
        ))
        assert len(state.competitors) == 2
        # 提升为裁判
        state.set_judge_model(a)
        assert state.judge_model is not None
        assert len(state.competitors) == 1
        # 添加私有对话
        state.init_private_chats([b.id])
        state.add_private_message(b.id, ChatMessage("m1", "judge", "hi", 0))
        assert len(state.private_chats) == 1
        # 淘汰
        state.eliminate_models([b.id], {b.id: "test"})
        assert b.id in state.eliminated_models
        # 持久化
        state2 = ArenaState()
        state2.bind_storage(s)
        assert len(state2.competitors) == 1
        assert state2.judge_model is not None
        assert state2.eliminated_models == [b.id]
        print("✓ test_state_lifecycle")
    finally:
        shutil.rmtree(tmp)


# ─── 测试 4: 协议转换（核心需求） ───

def test_protocol_normalization():
    """测试归一化 -> 各厂商 -> 反归一化的完整双向流程。"""
    req = UniversalRequest(
        model="gpt-4o",
        messages=[
            UniversalMessage("system", "You are helpful."),
            UniversalMessage("user", "Hi"),
            UniversalMessage("assistant", "Hello!"),
            UniversalMessage("user", "How are you?"),
        ],
        temperature=0.7,
        max_tokens=2048,
    )

    # ── OpenAI 形态
    p = OpenAICompatAdapter().to_provider_payload(req)
    assert p["model"] == "gpt-4o"
    assert len(p["messages"]) == 4
    assert p["messages"][0]["role"] == "system"

    # ── Anthropic：system 抽离
    p = AnthropicAdapter().to_provider_payload(req)
    assert "system" in p
    assert p["system"] == "You are helpful."
    # messages 里只有 user/assistant
    roles = [m["role"] for m in p["messages"]]
    assert "system" not in roles

    # ── Gemini：{model} 占位符 + systemInstruction + parts
    adapter = GeminiAdapter()
    p = adapter.to_provider_payload(req)
    assert p["systemInstruction"]["parts"][0]["text"] == "You are helpful."
    assert p["contents"][0]["parts"][0]["text"] == "Hi"
    # 端点替换
    url = adapter.resolve_endpoint(
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "gemini-1.5-pro",
    )
    assert "gemini-1.5-pro" in url
    assert "{model}" not in url

    # ── 反向：各家响应 -> 归一化
    cases = [
        (OpenAICompatAdapter(), {"choices": [{"message": {"content": "A"}}]}, "A"),
        (AnthropicAdapter(), {"content": [{"type": "text", "text": "B"}]}, "B"),
        (GeminiAdapter(), {"candidates": [{"content": {"parts": [{"text": "C"}]}}]}, "C"),
        (BaiduAdapter(), {"choices": [{"message": {"content": "D"}}]}, "D"),
        (HunyuanAdapter(), {"choices": [{"message": {"content": "E"}}]}, "E"),
        (ZhipuAdapter(), {"choices": [{"message": {"content": "F"}}]}, "F"),
        (StepFunAdapter(), {"choices": [{"message": {"content": "G"}}]}, "G"),
    ]
    for adapter, payload, expected in cases:
        resp = adapter.from_provider_payload(payload)
        assert resp.content == expected, f"{type(adapter).__name__} failed: got {resp.content!r}"
    print("✓ test_protocol_normalization")


# ─── 测试 5: 端点表 ───

def test_default_endpoints():
    expected = {
        ApiType.OPENAI, ApiType.ANTHROPIC, ApiType.GOOGLE, ApiType.VOLCENGINE,
        ApiType.BAIDU, ApiType.ALIBABA, ApiType.HUNYUAN, ApiType.MOONSHOT,
        ApiType.ZHIPU, ApiType.STEPFUN,
    }
    for t in expected:
        assert t in DEFAULT_ENDPOINTS
        assert DEFAULT_ENDPOINTS[t].startswith("http")
    print("✓ test_default_endpoints")


# ─── 测试 6: 额度检测 ───

def test_quota_detection():
    assert looks_like_quota_error(429, "rate limit exceeded")
    assert looks_like_quota_error(402, "insufficient balance")
    assert looks_like_quota_error(403, "quota exceeded for account")
    assert looks_like_quota_error(500, "余额不足")  # 关键字
    assert not looks_like_quota_error(200, "ok")
    print("✓ test_quota_detection")


# ─── 测试 7: 快照 ───

def test_snapshots():
    tmp = tempfile.mkdtemp()
    try:
        s = Storage(tmp)
        state = ArenaState()
        state.bind_storage(s)
        a = state.add_competitor(AIConfig(
            id="", name="A", api_type=ApiType.OPENAI, endpoint="", api_key="",
            model_name="m1", color=pick_color(0), icon=pick_icon(0),
        ))
        b = state.add_competitor(AIConfig(
            id="", name="B", api_type=ApiType.ANTHROPIC, endpoint="", api_key="",
            model_name="m2", color=pick_color(1), icon=pick_icon(1),
        ))
        state.set_judge_model(a)
        snap = create_snapshot(state, "test")
        snaps = s.load_snapshots()
        assert len(snaps) == 1
        # 恢复
        restore_snapshot(state, snaps[0])
        assert state.judge_model is not None
        assert state.judge_model.name == "A"
        print("✓ test_snapshots")
    finally:
        shutil.rmtree(tmp)


# ─── 测试 8: 压缩 ───

def test_compression():
    r = RoundRecord(
        round=0, question="Test?", rule_reminder="",
        private_chats=[], public_messages=[],
        eliminated_this_round=["x"], answers={"a": "ans"},
        scores={"a": 80}, judge_comment="good", timestamp=0,
    )
    s = compress_rounds([r])
    assert "第1轮" in s
    assert "x" in s
    assert "good" in s
    print("✓ test_compression")


# ─── 测试 9: JSON 提取 ───

def test_json_extraction():
    assert _extract_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert _extract_json("prefix {\"a\": 1} suffix") == {"a": 1}
    assert _extract_json("no json here") is None
    assert _extract_json("") is None
    print("✓ test_json_extraction")


# ─── 测试 10: 路由表 ───

def test_router():
    # 每个 ApiType 都应能拿到 adapter
    for at in ApiType:
        adapter = get_adapter(at)
        assert adapter is not None
        assert adapter.api_type == at or at == ApiType.CUSTOM or at in (
            ApiType.VOLCENGINE, ApiType.ALIBABA, ApiType.MOONSHOT
        )
    # 端点
    assert "openai.com" in get_default_endpoint(ApiType.OPENAI)
    assert "anthropic.com" in get_default_endpoint(ApiType.ANTHROPIC)
    assert "{model}" in get_default_endpoint(ApiType.GOOGLE)
    print("✓ test_router")


if __name__ == "__main__":
    test_models_serialization()
    test_default_rule()
    test_storage()
    test_state_lifecycle()
    test_protocol_normalization()
    test_default_endpoints()
    test_quota_detection()
    test_snapshots()
    test_compression()
    test_json_extraction()
    test_router()
    print()
    print("=== ALL SMOKE TESTS PASSED ===")
