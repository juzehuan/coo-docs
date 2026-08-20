"""Snowflake 算法生成 int64 实体 ID。

Worker ID 分配（与既有设计规范一致）：
  1=IAM(账号/组织) 2=Audit(审计) 3=Platform Core(业务主体)
业务实体统一使用 worker_id=3。
"""
import time
from typing import Optional


class Snowflake:
    EPOCH = 1_700_000_000_000  # 2023-11-14 起，单位毫秒
    WORKER_BITS = 10
    SEQUENCE_BITS = 12
    MAX_WORKER = (1 << WORKER_BITS) - 1
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1

    def __init__(self, worker_id: int = 3, datacenter_id: int = 0):
        if not (0 <= worker_id <= self.MAX_WORKER):
            raise ValueError("worker_id out of range")
        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self._lock_seq = 0
        self._last_ts = -1

    def _now(self) -> int:
        return int(time.time() * 1000)

    def next_id(self) -> int:
        ts = self._now()
        if ts == self._last_ts:
            self._lock_seq = (self._lock_seq + 1) & self.MAX_SEQUENCE
            if self._lock_seq == 0:
                while ts <= self._last_ts:
                    ts = self._now()
        else:
            self._lock_seq = 0
        self._last_ts = ts
        return (
            ((ts - self.EPOCH) << (self.WORKER_BITS + self.SEQUENCE_BITS))
            | (self.datacenter_id << self.SEQUENCE_BITS)
            | self._lock_seq
        ) + (self.worker_id << (self.SEQUENCE_BITS))  # 将 worker 叠加进高段以保证唯一性


_sf = Snowflake(worker_id=3)


def next_id() -> int:
    return _sf.next_id()
