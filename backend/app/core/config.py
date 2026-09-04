"""全局配置。

所有运行期可变参数都通过环境变量（前缀 ``WENLV_``）注入，
避免把魔法数写死在业务代码多处（对应说明书 S7/S8/S12 等裁决）。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。字段名与 ``WENLV_`` 前缀的环境变量一一对应。"""

    model_config = SettingsConfigDict(
        env_prefix="WENLV_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # 基础
    # ------------------------------------------------------------------ #
    app_name: str = "文旅多Agent行程规划系统"
    env: str = "dev"  # dev / prod
    log_level: str = "INFO"

    # ------------------------------------------------------------------ #
    # 数据库 / Redis
    # ------------------------------------------------------------------ #
    database_url: str = "postgresql+asyncpg://wenlv:wenlv@localhost:5432/wenlv"
    redis_url: str = "redis://localhost:6379/0"
    redis_prefix: str = "wenlv"  # 全部 Redis key 的统一前缀

    # ------------------------------------------------------------------ #
    # JWT
    # ------------------------------------------------------------------ #
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_seconds: int = 86400  # 24h，砍掉 refresh（S19）

    # ------------------------------------------------------------------ #
    # 工作区（travel_plan.md 状态文件）
    # ------------------------------------------------------------------ #
    workspace_root: str = "./workspace"  # 每行程一个子目录 workspace/{plan_id}
    snapshot_max: int = 5  # 保留最近 N 份快照

    # ------------------------------------------------------------------ #
    # HITL 阈值（可配）
    # ------------------------------------------------------------------ #
    budget_over_ratio: float = 0.45  # 超预算比例阈值（S7，超 45% 才触发人工审核）
    budget_review_threshold: float = 30000  # 预算金额超过此阈值即触发人工审核
    review_timeout_hours: int = 24  # 审批超时（S8）
    sentiment_min_score: float = 0.25  # 舆情综合分低于此值视为严重（§5.2）
    night_start_hour: int = 22  # 高危夜行开始时刻 22:00
    night_end_hour: int = 6  # 高危夜行结束时刻 06:00
    hitl_demo: bool = True  # 是否在种子数据里保留负面舆情/夜行风险（默认开启，人工审核是核心功能）

    # ------------------------------------------------------------------ #
    # 票价折扣（门票/车票的儿童/老人政策，可配，不写死）
    # ------------------------------------------------------------------ #
    ticket_child_discount: float = 0.5  # 门票儿童折扣（0.5 = 半价）
    ticket_elder_discount: float = 0.0  # 门票老人折扣（0.0 = 免费；可改为 0.5 半价）—— 兜底默认，见下方按年龄分档
    transport_child_discount: float = 0.5  # 车票儿童折扣（高铁儿童半价）
    transport_elder_discount: float = 1.0  # 车票老人折扣（1.0 = 不免费，全价）

    # 老人门票按年龄分档（国有/政府定价 A 级景区，只免首道大门票）：
    #   60-64 半价（多数省份）；65 及以上免首道大门票；60 以下按成人全价。
    #   免票不含观光车/索道/游船/演出/园中园，需另计（这里只算首道大门票）。
    ticket_elder_free_age: int = 65  # 该年龄（含）以上免首道大门票
    ticket_elder_half_age: int = 60  # 该年龄（含）至 free_age 之间半价

    # ------------------------------------------------------------------ #
    # LLM
    # ------------------------------------------------------------------ #
    llm_mode: str = "mock"  # mock | real（S13：开发/压测走 Mock）
    llm_api_key: str = ""
    llm_base_url: str = ""  # OpenAI 兼容端点，如 https://xxx.compatible-mode/v1
    llm_model: str = ""  # 模型名，如 qwen3.7-plus
    llm_max_concurrency: int = 1  # 单 Worker 内 LLM 并发信号量（§3.1 背压）

    # ------------------------------------------------------------------ #
    # Embedding（RAG：语义向量，复用百炼 OpenAI 兼容 /embeddings）
    # ------------------------------------------------------------------ #
    embedding_model: str = "text-embedding-v3"  # 百炼 embedding 模型
    embedding_dim: int = 768  # 向量维度（text-embedding-v3 支持 1024/768/512）
    vector_backend: str = "pgvector"  # pgvector | cosine（cosine=应用层兜底）

    # ------------------------------------------------------------------ #
    # 高德地图（真实数据）
    # ------------------------------------------------------------------ #
    amap_key: str = ""  # 高德 Web 服务 API Key
    amap_enabled: bool = True  # 是否启用真实高德数据（关掉则回退本地种子）
    amap_cache_ttl: int = 3600  # 高德结果缓存（秒）

    # ------------------------------------------------------------------ #
    # 队列 / 恢复
    # ------------------------------------------------------------------ #
    request_stream: str = "stream:plan.requests"  # 新计划入队
    resume_stream: str = "stream:plan.resume"  # HITL 通过后续跑
    events_stream: str = "stream:plan.events"  # WS 广播备份（可选）
    consumer_group: str = "cg:wenlv-workers"
    stream_maxlen: int = 10000  # 近似裁剪，防 pending 无界
    stream_block_ms: int = 2000  # XREADGROUP 阻塞读
    claim_min_idle_ms: int = 500  # XAUTOCLAIM 自认领（S12）
    heartbeat_ttl: int = 3  # 心跳 TTL（秒）

    # 提交防抖 / 审核租约
    submit_lock_ttl: int = 5  # 秒（S26）
    review_lock_ttl: int = 300  # 秒（5 分钟，S28）
    plan_lock_ttl: int = 30  # 行程级互斥（秒）

    # 状态缓存 TTL
    status_cache_ttl: int = 30  # 秒


@lru_cache
def get_settings() -> Settings:
    """返回单例配置（进程内缓存）。"""
    return Settings()


settings = get_settings()
