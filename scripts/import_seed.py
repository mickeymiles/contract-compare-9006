"""幂等导入种子数据（seeds/seed_data.sql -> SQLite）

- 种子 SQL 本身包含 DELETE + INSERT，导入前自动 init_db() 建表
- 幂等：可重复执行
- 支持指定目标数据库文件（默认 backend 配置的 contract_compare.db）

用法：
    python3 scripts/import_seed.py
    python3 scripts/import_seed.py --db /path/to/contract_compare.db
"""
import argparse
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_SQL = os.path.join(BASE, "seeds", "seed_data.sql")

# 默认数据库路径与 backend/models.py 保持一致
DEFAULT_DB = os.path.join(BASE, "contract_compare.db")


def init_db(db_path):
    """调用 backend.models.init_db 建表（幂等），保证导入目标表存在"""
    sys.path.insert(0, os.path.join(BASE, "backend"))
    try:
        import models
        models.DB_PATH = db_path  # 建表到目标库
        models.init_db()
        print(f"✅ init_db() 建表完成（{db_path}）")
    except Exception as e:
        print(f"⚠️  init_db 失败（{e}），尝试直接导入（若表不存在会报错）")


def main():
    parser = argparse.ArgumentParser(description="幂等导入种子数据")
    parser.add_argument("--db", default=DEFAULT_DB, help="目标 SQLite 数据库文件")
    args = parser.parse_args()

    if not os.path.exists(SEED_SQL):
        print(f"❌ 种子文件不存在: {SEED_SQL}\n   请先运行 python3 scripts/export_seed.py 生成")
        sys.exit(1)

    # 确保数据库所在目录存在
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)

    init_db(args.db)

    conn = sqlite3.connect(args.db)
    try:
        with open(SEED_SQL, encoding="utf-8") as f:
            sql = f.read()
        conn.executescript(sql)
        conn.commit()

        # 校验行数
        cur = conn.cursor()
        tables = ["fund_metrics", "indicator_metrics", "analysis_snapshots", "etl_jobs"]
        print("📊 导入后行数校验：")
        for t in tables:
            cur.execute(f"SELECT count(*) FROM {t}")
            print(f"  {t}: {cur.fetchone()[0]} 行")
        print("✅ 种子数据导入完成")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"❌ 导入失败: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
