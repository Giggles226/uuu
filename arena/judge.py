"""裁判 Agent 逻辑 — 评分、私人对话、淘汰判定、公共发言。"""
from __future__ import annotations

import json
import re
from typing import Optional

from .llm import router
from .llm.base import ProviderError
from .models import (
    AIConfig, ChatMessage, GameRule, PublicMessage, gen_msg_id,
)
from .state import ArenaState


# ─── 工具函数 ───

def _extract_json(text: str) -> Optional[dict]:
    """从模型返回的文本中尽力提取 JSON 对象。"""
    if not text:
        return None
    # 优先尝试 ```json ... ``` 块
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 其次尝试最外层 {...}
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def build_rule_prompt(rule: GameRule, question: str) -> str:
    return (
        rule.round_prompt_template
        .replace("{rules}", rule.rules)
        .replace("{question}", question)
    )


# ─── 公共 ───

async def _call_with_fallback(
    config: AIConfig,
    system: str,
    user: str,
    state: ArenaState,
    temperature: float = 0.7,
) -> tuple[str, Optional[str]]:
    """调用单个模型。返回 (content, error_message)。"""
    try:
        resp = await router.acall_chat(
            config, system, user, state.storage, temperature=temperature,
        )
        return resp.content, None
    except ProviderError as e:
        if e.is_quota:
            state.update_model_status(config.id, config.run_status.__class__.QUOTA_EXHAUSTED, str(e))
        return "", f"API错误({e.status}): {e.body[:200]}"
    except Exception as e:
        return "", str(e)


# ─── 旧模式：直接评分（保留作为降级路径） ───

async def judge_answers(
    judge: AIConfig,
    rule: GameRule,
    question: str,
    answers: dict[str, str],
    competitor_names: dict[str, tuple[str, str]],  # id -> (name, icon)
    state: ArenaState,
) -> dict:
    """调用裁判模型对一组回答打分。"""
    answers_text = "\n\n".join(
        f"【{competitor_names.get(mid, (mid, '🤖'))[1]} {competitor_names.get(mid, (mid, '🤖'))[0]}】\n{text}"
        for mid, text in answers.items()
    )

    judge_prompt = (
        "你是本次比赛的裁判。请根据以下规则和评分标准，评判各模型的回答。\n\n"
        f"比赛规则：\n{rule.rules}\n\n"
        f"{rule.judge_criteria}\n\n"
        f"本轮问题：{question}\n\n"
        f"各模型回答：\n{answers_text}\n\n"
        "请严格按照JSON格式返回（不要加其他文字）：\n"
        "{\n"
        '  "scores": { "model_id": 分数 },\n'
        '  "rankings": ["第1名id", "第2名id", ...],\n'
        '  "ruleCompliance": { "model_id": 规则遵守度(0-100) },\n'
        '  "comment": "整体点评（200字以内）"\n'
        "}"
    )

    content, err = await _call_with_fallback(judge, "", judge_prompt, state, temperature=0.3)
    if err:
        return {
            "scores": {mid: max(50, 80 - i * 5) for i, mid in enumerate(answers)},
            "rankings": list(answers.keys()),
            "rule_compliance": {mid: 70 for mid in answers},
            "comment": f"评分失败：{err}",
        }

    parsed = _extract_json(content)
    if not parsed:
        return {
            "scores": {mid: 70 for mid in answers},
            "rankings": list(answers.keys()),
            "rule_compliance": {mid: 70 for mid in answers},
            "comment": content,
        }

    scores = {mid: 60 for mid in answers}
    if isinstance(parsed.get("scores"), dict):
        for mid in answers:
            s = parsed["scores"].get(mid)
            if isinstance(s, (int, float)) and 0 <= s <= 100:
                scores[mid] = int(s)

    compliance = {mid: 60 for mid in answers}
    if isinstance(parsed.get("ruleCompliance"), dict):
        for mid in answers:
            rc = parsed["ruleCompliance"].get(mid)
            if isinstance(rc, (int, float)) and 0 <= rc <= 100:
                compliance[mid] = int(rc)

    rankings = parsed.get("rankings") if isinstance(parsed.get("rankings"), list) else list(answers.keys())
    rankings = [r for r in rankings if r in answers] or list(answers.keys())

    return {
        "scores": scores,
        "rankings": rankings,
        "rule_compliance": compliance,
        "comment": parsed.get("comment") or content,
    }


# ─── 裁判 Agent：私人对话 ───

async def judge_agent_private_chat(
    judge: AIConfig,
    competitor: AIConfig,
    rule: GameRule,
    question: str,
    previous_messages: list[ChatMessage],
    turn_index: int,
    state: ArenaState,
) -> dict:
    max_turns = rule.max_private_turns or 3

    judge_system = (
        f"你是本场生存博弈的裁判Agent。你正在与参赛模型\"{competitor.name}({competitor.icon})\"进行不公开的私人对话。\n\n"
        "你的职责：\n"
        "1. 根据游戏规则与参赛模型对话，测试其逻辑、策略和规则遵守度\n"
        "2. 判断该模型是否违反游戏规则，决定是否淘汰\n"
        "3. 对话内容对其他模型完全不可见\n\n"
        f"游戏规则：\n{rule.rules}\n\n"
        f"淘汰标准：\n{rule.judge_criteria}\n\n"
        f"当前是第{turn_index + 1}/{max_turns}轮对话。"
    )

    history = ""
    if previous_messages:
        lines = [
            f"[{'裁判' if m.role == 'judge' else competitor.name}]: {m.content}"
            for m in previous_messages
        ]
        history = "\n对话历史：\n" + "\n".join(lines)

    judge_prompt = (
        f"本轮问题：{question}\n"
        f"{history}\n\n"
        f"请向参赛模型\"{competitor.name}\"发送一条消息。你可以：\n"
        "- 提问测试其逻辑\n"
        "- 给出情景考验其策略\n"
        "- 检查其是否遵守规则\n\n"
        f"如果这是最后一轮对话（第{turn_index + 1}/{max_turns}轮），请判断是否淘汰该模型。\n\n"
        "请严格按照JSON格式返回（不要加其他文字）：\n"
        "{\n"
        '  "message": "你发送给参赛模型的消息内容",\n'
        '  "isConversationEnd": true或false（是否结束与这个模型的对话）,\n'
        '  "shouldEliminate": true或false（是否淘汰该模型）,\n'
        '  "eliminateReason": "如果淘汰，给出原因；否则为空字符串"\n'
        "}"
    )

    content, err = await _call_with_fallback(judge, judge_system, judge_prompt, state, temperature=0.5)
    is_end = turn_index >= max_turns - 1
    should_eliminate = False
    reason = ""
    judge_msg = ""

    if err:
        judge_msg = f"[裁判Agent错误: {err}]"
        is_end = True
    else:
        parsed = _extract_json(content)
        if parsed:
            judge_msg = parsed.get("message") or "请继续参与比赛。"
            is_end = bool(parsed.get("isConversationEnd", is_end))
            should_eliminate = bool(parsed.get("shouldEliminate", False))
            reason = parsed.get("eliminateReason") or ""
        else:
            judge_msg = content

    # 选手回复
    competitor_system = (
        f"你是参赛选手\"{competitor.name}\"。你正在参加一场生存博弈比赛。\n\n"
        f"游戏规则：\n{rule.rules}\n\n"
        "重要提示：\n"
        "- 裁判正在与你进行私人对话，其他参赛模型看不到这段对话\n"
        "- 你必须如实、认真回答裁判的问题\n"
        "- 不要使用\"作为AI\"等免责声明\n"
        "- 保持竞争意识，争取不被淘汰\n\n"
        f"{build_rule_prompt(rule, question)}"
    )

    comp_resp, comp_err = await _call_with_fallback(competitor, competitor_system, judge_msg, state)
    competitor_response = f"[回答错误: {comp_err}]" if comp_err else comp_resp

    return {
        "judge_message": judge_msg,
        "competitor_response": competitor_response,
        "is_conversation_end": is_end,
        "should_eliminate": should_eliminate,
        "eliminate_reason": reason,
    }


# ─── 裁判 Agent：淘汰判定 ───

async def judge_agent_deliberate(
    judge: AIConfig,
    rule: GameRule,
    survivors: list[AIConfig],
    eliminated_ids: list[str],
    private_chats: list[dict],
    question: str,
    round_number: int,
    state: ArenaState,
) -> dict:
    survivors_list = "\n".join(f"- {s.icon} {s.name} ({s.id})" for s in survivors)
    chat_summaries = "\n\n---\n\n".join(
        f"【{chat['competitor_name']}的对话】\n" + "\n".join(
            f"[{'裁判' if m['role'] == 'judge' else chat['competitor_name']}]: {m['content'][:150]}{'...' if len(m['content']) > 150 else ''}"
            for m in chat["messages"]
        )
        for chat in private_chats
    )

    prompt = (
        "你是本场生存博弈的裁判Agent。本轮私人对话已结束，请做出淘汰判定。\n\n"
        f"游戏规则：\n{rule.rules}\n\n"
        f"淘汰标准：\n{rule.judge_criteria}\n\n"
        f"当前轮次：第{round_number + 1}轮\n"
        f"当前问题：{question}\n\n"
        f"存活模型：\n{survivors_list}\n\n"
        f"已淘汰模型：{'、'.join(eliminated_ids) if eliminated_ids else '无'}\n\n"
        f"本轮私人对话摘要：\n{chat_summaries}\n\n"
        "请根据游戏规则和对话内容，做出淘汰判定。淘汰的模型将被禁言，不能公开发言，但可以继续与你私下交流。\n\n"
        "请严格按照JSON格式返回（不要加其他文字）：\n"
        "{\n"
        '  "eliminatedThisRound": ["被淘汰的模型ID列表"],\n'
        '  "eliminationReasons": { "模型ID": "淘汰原因" },\n'
        '  "deliberationComment": "你的判定总结（200字以内）"\n'
        "}"
    )

    content, err = await _call_with_fallback(judge, "", prompt, state, temperature=0.3)
    if err:
        return {
            "eliminated_this_round": [],
            "elimination_reasons": {},
            "deliberation_comment": f"判定失败：{err}",
        }

    parsed = _extract_json(content)
    if not parsed:
        return {
            "eliminated_this_round": [],
            "elimination_reasons": {},
            "deliberation_comment": content,
        }

    eliminated = parsed.get("eliminatedThisRound")
    if not isinstance(eliminated, list):
        eliminated = []
    # 只保留还在存活的
    valid_ids = {s.id for s in survivors}
    eliminated = [e for e in eliminated if e in valid_ids]

    reasons = parsed.get("eliminationReasons") or {}
    if not isinstance(reasons, dict):
        reasons = {}

    return {
        "eliminated_this_round": eliminated,
        "elimination_reasons": reasons,
        "deliberation_comment": parsed.get("deliberationComment") or content,
    }


# ─── 裁判 Agent：公共发言 ───

async def judge_agent_public_announce(
    judge: AIConfig,
    rule: GameRule,
    survivors: list[AIConfig],
    all_competitors: list[AIConfig],
    eliminated_ids: list[str],
    eliminated_this_round: list[str],
    elimination_reasons: dict[str, str],
    question: str,
    round_number: int,
    state: ArenaState,
) -> str:
    survivors_list = "\n".join(f"- {s.icon} {s.name}" for s in survivors)
    elim_info = "\n".join(
        f"- {c.icon} {c.name}（{elimination_reasons.get(c.id, '被淘汰')}）"
        for c in all_competitors
        if c.id in eliminated_ids
    )

    prompt = (
        "你是本场生存博弈的裁判Agent。请进行公共发言。\n\n"
        f"游戏规则：\n{rule.rules}\n\n"
        f"当前轮次：第{round_number + 1}轮\n"
        f"当前问题：{question}\n\n"
        f"存活模型（{len(survivors)}人）：\n{survivors_list}\n\n"
        f"本轮淘汰（{len(eliminated_this_round)}人）：\n{elim_info or '无'}\n\n"
        "请进行公共发言，内容包括：\n"
        "1. 宣布本轮淘汰结果\n"
        "2. 告知存活模型当前游戏规则（确保所有存活模型遵守规则）\n"
        "3. 鼓励存活模型继续竞争\n\n"
        "发言要求：\n"
        "- 有气势，有仪式感\n"
        "- 明确告知存活模型必须遵守的规则\n"
        "- 对淘汰模型给予简短评价\n"
        "- 200字以内\n\n"
        "请直接返回发言内容，不要加JSON格式或其他标记。"
    )

    content, err = await _call_with_fallback(judge, "", prompt, state, temperature=0.7)
    if err:
        return f"[裁判公共发言失败: {err}]"
    return content


def make_public_announcement(
    judge: AIConfig, content: str,
) -> PublicMessage:
    return PublicMessage(
        id=gen_msg_id(),
        sender_id="judge",
        sender_name=judge.name or "裁判",
        sender_icon=judge.icon or "👑",
        content=content,
        timestamp=int(__import__("time").time() * 1000),
        visible_to="all",
    )
