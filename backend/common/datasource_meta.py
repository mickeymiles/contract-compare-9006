"""数据源版本元数据（跨域共享）。"""
import json
import os

from common.paths import DATASOURCE_DIR

# 数据源版本元数据文件
DS_META_FILE = os.path.join(DATASOURCE_DIR, 'versions.json')


def _load_ds_meta():
    if os.path.exists(DS_META_FILE):
        with open(DS_META_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_ds_meta(meta):
    with open(DS_META_FILE, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _ensure_table(meta, table_name):
    if table_name not in meta:
        meta[table_name] = {'versions': [], 'next_id': 1}
    return meta[table_name]