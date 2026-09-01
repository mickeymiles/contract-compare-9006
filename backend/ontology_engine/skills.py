# -*- coding: utf-8 -*-
"""Skill 定义加载（本地文件版）。

迁移说明：原依赖 neuops-agent-demo 的 `app/skill_loader.py`（带 DB / seed_data 多级装载）。
本工程只需要 Skill JSON 里的**声明式内容**（邮件 A-G 模板、参与方兜底），
不需要 LLM system prompt 拼装与 MCP 工具绑定，故简化为纯文件加载 + mtime 热更新缓存。

目录：backend/ontology_engine/skills/<skill_id>.json
返回结构与原 load_skill 保持兼容（调用方读 sk["skill"] / sk["templates"] / sk["tools"]）。
"""
import json
import os

_SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
_cache = {}


def skill_dir() -> str:
    return os.getenv("ONT_SKILL_DIR", _SKILL_DIR)


def load_skill(skill_id: str):
    """按 skill_id 读 JSON 定义；文件缺失 / 解析失败返回 None（调用方自行降级）。"""
    skill_id = (skill_id or "").strip()
    if not skill_id:
        return None
    path = os.path.join(skill_dir(), f"{skill_id}.json")
    if not os.path.isfile(path):
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _cache.get(skill_id)
    if cached and cached.get("mtime") == mtime:
        return cached
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return None
    result = {
        "skill": raw,
        "templates": raw.get("templates") or {},
        "tools": raw.get("tools") or [],
        "participants": raw.get("participants") or {},
        "compose": raw.get("compose") or {},
        "source": "json",
        "mtime": mtime,
    }
    _cache[skill_id] = result
    return result
