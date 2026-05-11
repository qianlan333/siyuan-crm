"""Unified outbound-send contract.

PR 1（本 PR）只引入 ``SendTask`` 数据类型，不改任何 caller。后续 PR 把 5 个发送
入口逐个内部归一到 ``SendTask`` → ``enqueue_job(**send_task.to_enqueue_kwargs())``。

参见 https://github.com/qianlan333/AI-CRM/pull/248 体检报告中"5 个独立发送入口"段落。
"""
from .dto import VALID_SEND_TASK_SOURCE_KINDS, SendTask

__all__ = ["SendTask", "VALID_SEND_TASK_SOURCE_KINDS"]
