# -*- coding: utf-8 -*-
"""emp-009 本体轨调度运行时：监听线程（asyncio task）生命周期由数字员工页面开关驱动。

设计要点（对齐用户需求：页面启用=即时拉起监听轮询线程 / 页面停用=即时停止）：
- 权威开关 = DB 中 emp-009.enabled，经 execution.needs_exec() 综合本轨前提（ONT_MODE∈{ontology,split}
  且 ONT_EXEC=1）与技能启用状态。线上部署先设好本轨 env 前提，页面开关即在其上即时控制线程。
- ONT_SCHEDULER 为可选「总闸」：显式设为 "0" 时彻底禁用自动调度（即便页面启用也不起）；
  不设置或设为 "1" 时由页面开关决定。
- sync_scheduler() 幂等、可重复调用：启动期与每次 emp-009 启停都调它，自行决定创建/取消 task。
"""
import asyncio
import os

from . import execution
from .config import PORT

_ont_task = None  # asyncio.Task | None


def should_run() -> bool:
    """是否应运行 emp-009 监听线程。"""
    if os.getenv("ONT_SCHEDULER", "1") == "0":
        return False
    return execution.needs_exec()


async def _ont_loop():
    """本体轨 emp-009 全流程自走调度：每 60s POST /run-full（SEEN 认领 + 入向回复 + LLM 决策执行）。"""
    import httpx
    await asyncio.sleep(40)  # 启动后等 40 秒再开始
    while True:
        try:
            use_llm = os.getenv("ONT_SCHEDULER_USE_LLM", "0") == "1"
            # trust_env=False：目标是本机自身端口，若继承 shell 的 HTTP_PROXY
            # 会被代理拦成 502，常驻调度将静默空转。
            async with httpx.AsyncClient(trust_env=False) as client:
                await client.post(
                    f"http://127.0.0.1:{PORT}/api/ontology-emp009/run-full",
                    json={"use_llm": use_llm}, timeout=60)
        except Exception:
            pass
        await asyncio.sleep(60)


async def sync_scheduler():
    """按 should_run() 同步监听 task 生命周期（页面开关的落点）。幂等。"""
    global _ont_task
    if should_run():
        if _ont_task is None or _ont_task.done():
            _ont_task = asyncio.create_task(_ont_loop())
    else:
        if _ont_task is not None and not _ont_task.done():
            _ont_task.cancel()
            try:
                await _ont_task
            except (asyncio.CancelledError, Exception):
                pass
            _ont_task = None


def stop_now():
    """进程退出时调用：取消并丢弃 task。"""
    global _ont_task
    if _ont_task is not None and not _ont_task.done():
        _ont_task.cancel()
    _ont_task = None
