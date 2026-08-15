"""从本地脱敏库导出种子数据，生成 seeds/seed_data.sql（含项目名补充脱敏）

背景：
- 服务器端脱敏已覆盖 客户名称/人员名称（映射表 name_abbr_mapping.json：full 176 条 + core 508 条）
- 但宽表 project_name 仍残留真实机构/地名/厂商名（东软教育、口腔医院、华为、深信服、
  松江区、西藏自治区、青海省、青岛青新网络、杭州湾、国创、黄岛 等）
- 本脚本导出时对 project_name 应用 映射表子串替换 + 补充词典，生成干净的种子 SQL

产出：
- seeds/seed_data.sql    幂等 SQL（DELETE + INSERT，含分析宽表与 ETL 任务定义）
- seeds/seed_meta.json   种子元信息（来源、时间、脱敏规则、行数）

用法：
    python3 scripts/export_seed.py
"""
import json
import os
import re
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "contract_compare.db")
MAP_PATH = os.path.join(BASE, "name_abbr_mapping.json")
SEEDS_DIR = os.path.join(BASE, "seeds")
SQL_PATH = os.path.join(SEEDS_DIR, "seed_data.sql")
META_PATH = os.path.join(SEEDS_DIR, "seed_meta.json")

# 导出表：分析功能相关（宽表 + 任务定义）
TABLES = ["fund_metrics", "indicator_metrics", "analysis_snapshots", "etl_jobs"]

# ---------------------------------------------------------------------------
# 项目名补充脱敏词典（真实名称 -> 代号）
# 优先用映射表 core 子串替换，未覆盖的敏感词走这里
# ---------------------------------------------------------------------------
EXTRA_PROJECT_REPLACE = [
    # 机构 / 公司
    ("东软教育健康科技", "DRJYKJ"),
    ("东软教育", "DRJY"),
    ("口腔医院", "KQYY"),
    ("华为", "HW"),
    ("深信服", "SXF"),
    ("青新网络", "QXWL"),
    ("国创", "GC"),
    ("摆渡平台", "BD平台"),
    # 地名
    ("西藏自治区", "XZZZQ"),
    ("涉藏地区", "SZDQ"),
    ("青海省", "QHS"),
    ("松江区", "SJQ"),
    ("杭州湾", "HZW"),
    ("黄岛", "HD"),
    ("青岛", "QD"),
    ("大连", "DL"),
    ("成都", "CD"),
    ("东北基地", "DBJD"),
]

# 需额外全名替换的项目名（整串映射，命中直接替换）
PROJECT_NAME_WHOLE = {
    "DLDRXXXY2022年东软教育健康科技实训基地一期 1#楼口腔医院、 4#楼西塔楼弱电工程":
        "DLDRXXXY2022年DRJYKJ实训基地一期 1#楼KQYY、 4#楼西塔楼弱电工程",
    "大连东软教育健康科技实训基地一期增补合同": "DLDRJYKJ实训基地一期增补合同",
    "大连东软教育健康科技实训基地二期项目弱电智能化工程": "DLDRJYKJ实训基地二期项目弱电智能化工程",
    "成都东软教育健康科技实训基地弱电二期增补": "CDDRJYKJ实训基地弱电二期增补",
}


def load_name_mapping():
    """加载映射表，返回 core 列表（按 key 长度降序，最长优先匹配）"""
    with open(MAP_PATH, encoding="utf-8") as f:
        data = json.load(f)
    core = data.get("core", {})
    items = sorted(core.items(), key=lambda kv: len(kv[0]), reverse=True)
    return items


def sanitize_project_name(name, map_items):
    """项目名脱敏：整串映射 -> 映射表子串替换 -> 补充词典子串替换"""
    if not name:
        return name
    if name in PROJECT_NAME_WHOLE:
        return PROJECT_NAME_WHOLE[name]
    out = name
    # 1. 映射表 core 子串替换（最长优先）
    for src, dst in map_items:
        if src in out:
            out = out.replace(src, dst)
    # 2. 补充词典子串替换
    for src, dst in EXTRA_PROJECT_REPLACE:
        if src in out:
            out = out.replace(src, dst)
    return out


def snapshot_sanitize(result_json, name_map, map_items):
    """对 analysis_snapshots.result_json 中的项目名称字段做同步脱敏"""
    if not result_json:
        return result_json
    out = result_json
    for src, dst in name_map.items():
        if src in out:
            out = out.replace(src, dst)
    return out


def quote(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def dump_table_sql(conn, table, map_items, name_map):
    """导出单表 INSERT 语句"""
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    stmts = []
    stmts.append(f"DELETE FROM {table};")
    for r in rows:
        vals = []
        for i, c in enumerate(cols):
            v = r[i]
            if table == "fund_metrics" and c == "project_name":
                v = sanitize_project_name(v, map_items)
            elif table == "analysis_snapshots" and c == "result_json":
                v = snapshot_sanitize(v, name_map, map_items)
            vals.append(quote(v))
        stmts.append(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)});"
        )
    return stmts, len(rows)


def main():
    os.makedirs(SEEDS_DIR, exist_ok=True)
    map_items = load_name_mapping()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 先构建 project_name 的 旧->新 映射（供快照 JSON 同步替换）
    name_map = {}
    for r in conn.execute(
        "SELECT DISTINCT project_name FROM fund_metrics WHERE project_name != ''"
    ).fetchall():
        old = r[0]
        new = sanitize_project_name(old, map_items)
        if new != old:
            name_map[old] = new

    lines = []
    lines.append("-- 由 scripts/export_seed.py 自动生成，请勿手工编辑")
    lines.append(f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"-- 数据来源: contract_compare.db（服务器端已脱敏 + 项目名补充脱敏）")
    lines.append("BEGIN TRANSACTION;")
    lines.append("")

    meta_rows = {}
    for t in TABLES:
        stmts, n = dump_table_sql(conn, t, map_items, name_map)
        meta_rows[t] = n
        lines.append(f"-- ==== {t}（{n} 行）====")
        lines.extend(stmts)
        lines.append("")

    lines.append("COMMIT;")

    with open(SQL_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    meta = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_db": "contract_compare.db",
        "desensitization": {
            "customer_name": "服务器端已脱敏（拼音缩写，映射见 name_abbr_mapping.json）",
            "person_name": "服务器端已脱敏（姓+叉叉）",
            "project_name": "本脚本补充脱敏（映射表子串替换 + 补充词典）",
            "numbers": "金额/日期/周期等数值原样保留",
        },
        "project_name_replaced": len(name_map),
        "row_counts": meta_rows,
        "tables": TABLES,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    conn.close()

    print(f"已生成种子 SQL: {SQL_PATH}")
    print(f"已生成元信息:  {META_PATH}")
    print(f"项目名替换:    {len(name_map)} 处")
    for t, n in meta_rows.items():
        print(f"  {t}: {n} 行")
    print("\n项目名替换对照：")
    for old, new in name_map.items():
        print(f"  {old}  =>  {new}")


if __name__ == "__main__":
    main()
