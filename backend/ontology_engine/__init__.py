# -*- coding: utf-8 -*-
"""本体轨（NO-012 emp-009）：基于实体的 LLM 自主决策轨道（独立于现轨）。"""

from . import schema

schema.ensure_core_tables()


def init():
    schema.ensure_core_tables()