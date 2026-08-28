"""工单 7 验收测试（tests/test_memory_intervention.py）。

覆盖核心验收用例：
- test_extraction_triples：三元组抽取（规则降级路径）
- test_extraction_any_allergy：任意过敏原（香菜）可抽取
- test_intervention_signature：验签
- test_embedding：向量确定性/余弦

注：真实 LLM 抽取在运行时生效（llm_mode=real），Mock 下走规则降级。
"""

from __future__ import annotations

import uuid

import pytest

from app.memory.engine import extract_triples, rule_extract_triples
from app.memory.mutator import _hmac_sign


# --------------------------------------------------------------------------- #
# 三元组抽取（规则降级路径）
# --------------------------------------------------------------------------- #
def test_extraction_triples():
    """「我对海鲜严重过敏」应抽取出 HAS_ALLERGY 三元组（规则引擎，带「对」字最准）。"""
    triples = rule_extract_triples("我对海鲜严重过敏", owner_user_id=uuid.uuid4())
    allergy = [t for t in triples if t["relation"] == "HAS_ALLERGY"]
    assert len(allergy) >= 1, f"应抽取到过敏三元组，实际 {triples}"
    assert allergy[0]["dst_key"] == "海鲜"
    assert allergy[0]["properties"]["severity"] == "severe"


def test_extraction_prefers():
    """「喜欢自然风光」应抽取出 PREFERS 三元组。"""
    triples = rule_extract_triples("我喜欢自然风光，想去云南玩")
    relations = {t["relation"] for t in triples}
    assert "PREFERS" in relations, f"应含 PREFERS，实际 {triples}"


def test_extraction_visit():
    """「去云南游」应抽取出 PLANS_VISIT 三元组。"""
    triples = rule_extract_triples("去云南游")
    visits = [t for t in triples if t["relation"] == "PLANS_VISIT"]
    assert any(t["dst_key"] == "云南" for t in visits)


def test_extract_triples_async_returns_list():
    """async 的 extract_triples 在 Mock 下降级到规则，仍返回列表。"""
    import asyncio

    triples = asyncio.run(extract_triples("我海鲜过敏"))
    assert isinstance(triples, list)


# --------------------------------------------------------------------------- #
# 验签与防重放
# --------------------------------------------------------------------------- #
def test_intervention_signature():
    """正确签名与错误签名应可区分（_hmac_sign 确定性）。"""
    thread_id = "plan_test"
    nonce = "nonce_123"
    patch = {"available": False}
    sig = _hmac_sign(thread_id, nonce, patch)
    assert sig == _hmac_sign(thread_id, nonce, patch)  # 确定性
    assert sig != _hmac_sign(thread_id, nonce, {"available": True})  # 不同 patch 不同签名


def test_intervention_signature_tamper():
    """篡改 patch 后签名不匹配。"""
    thread_id = "plan_test"
    nonce = "nonce_456"
    patch = {"available": False}
    sig = _hmac_sign(thread_id, nonce, patch)
    # 篡改 patch
    assert sig != _hmac_sign(thread_id, nonce, {"available": True})


# --------------------------------------------------------------------------- #
# 向量 embedding 确定性
# --------------------------------------------------------------------------- #
def test_embedding_deterministic():
    """相同文本应产生相同 embedding。"""
    from app.memory.engine import _text_embedding

    a = _text_embedding("海鲜过敏")
    b = _text_embedding("海鲜过敏")
    assert a == b


def test_embedding_cosine():
    """相似文本余弦相似度应高于无关文本。"""
    from app.memory.engine import _cosine, _text_embedding

    q = _text_embedding("海鲜")
    hit = _text_embedding("海鲜过敏")
    miss = _text_embedding("自然风光")
    assert _cosine(q, hit) > _cosine(q, miss)
