"""Redis dependencies shared by API and worker process startup."""

from dataclasses import dataclass

from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from ascend_op_eval.config import Settings
from ascend_op_eval.control.broker import EvaluationStore
from ascend_op_eval.control.metrics import RedisMetrics


@dataclass(frozen=True)
class InstanceStorage:
    store: EvaluationStore
    metrics: RedisMetrics
    advisory: Redis

    @classmethod
    def connect(cls, settings: Settings) -> "InstanceStorage":
        """Keep advisory operations on a bounded connection separate from durable state."""
        durable = Redis.from_url(settings.redis_url, decode_responses=False)
        advisory = Redis.from_url(
            settings.redis_url, decode_responses=False,
            socket_connect_timeout=0.25, socket_timeout=0.25,
            retry=Retry(NoBackoff(), 0), retry_on_timeout=False, retry_on_error=[],
        )
        metrics = RedisMetrics(advisory, settings.redis_prefix)
        return cls(EvaluationStore(durable, settings, metrics=metrics), metrics, advisory)
