#!/usr/bin/env python3
"""客户/项目敏感信息存量清理脚本（部署时自动执行 + 可手动运行）。

职责：
1. 清空 contract_compare.db 中 fund_metrics 表的 customer_name / project_name
2. 就地删除 datasource/ 与 fund_data/ 下所有 .xlsx 的敏感列（客户名/客户简称/项目名等）
3. 清理 datasource_meta.json 中记录的列名（过滤敏感列）

用法：
    python3 scripts/clean_privacy.py
"""
import os
import re
import sys
import sqlite3
import glob
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 与 backend/main.py 保持一致：客户名/客户简称/项目名等敏感列一律丢弃
# 例外：客户标识（脱敏键，如 QDHEKJ）保留，用于多维度聚合，不视为敏感列
PRIVACY_HEADER_PATTERN = re.compile(
    r"(甲方|客户|业主|招标人|采购人|建设单位|使用单位|最终用户)"
    r"(名称|简称|全称|分类|编号)?$|"
    r"^(项目名称|项目描述|项目简介|合同名称|合同名|合同标题)$|"
    r"主合同客户名称|关键客户"
)


def is_privacy_header(h):
    return bool(h) and bool(PRIVACY_HEADER_PATTERN.search(str(h)))


def sanitize_excel_file(path):
    """就地删除 Excel 中所有 sheet 的敏感列。返回 (changed, dropped_cols)。"""
    dropped = set()
    if not str(path).lower().endswith('.xlsx'):
        return False, []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path)
    except Exception as e:
        print(f'  跳过 {os.path.basename(path)}: {e}')
        return False, []
    modified = False
    for ws in wb.worksheets:
        headers = [str(c.value) if c.value is not None else '' for c in ws[1]]
        drop_idx = [i for i, h in enumerate(headers) if is_privacy_header(h)]
        if not drop_idx:
            continue
        dropped.update(headers[i] for i in drop_idx)
        for i in sorted(drop_idx, reverse=True):
            ws.delete_cols(i + 1, 1)
        modified = True
    if modified:
        wb.save(path)
    wb.close()
    return modified, sorted(dropped)


def clean_db():
    """清空 fund_metrics 表 customer_name / project_name"""
    db_path = os.path.join(BASE_DIR, 'contract_compare.db')
    if not os.path.exists(db_path):
        print('[DB] contract_compare.db 不存在，跳过')
        return
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("UPDATE fund_metrics SET customer_name='', project_name=''")
        conn.commit()
        print(f'[DB] fund_metrics 已清空客户名/项目名（{cur.rowcount} 行）')
    except sqlite3.OperationalError as e:
        print(f'[DB] 更新失败: {e}')
    finally:
        conn.close()


def clean_files():
    """就地删除 datasource/ 与 fund_data/ 下 xlsx 的敏感列"""
    total_changed = 0
    for d in ('datasource', 'fund_data'):
        dpath = os.path.join(BASE_DIR, d)
        if not os.path.isdir(dpath):
            continue
        for f in sorted(glob.glob(os.path.join(dpath, '*.xlsx'))):
            changed, dropped = sanitize_excel_file(f)
            if changed:
                total_changed += 1
                print(f'[FILE] {os.path.relpath(f, BASE_DIR)} 删除列: {dropped}')
            else:
                print(f'[FILE] {os.path.relpath(f, BASE_DIR)} 无敏感列或跳过')
    print(f'[FILE] 共处理 {total_changed} 个文件')


def clean_meta():
    """过滤 datasource_meta.json 中记录的 columns"""
    meta_path = os.path.join(BASE_DIR, 'datasource_meta.json')
    if not os.path.exists(meta_path):
        print('[META] datasource_meta.json 不存在，跳过')
        return
    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    changed = False
    for tname, tdata in meta.items():
        for ver in tdata.get('versions', []):
            cols = ver.get('columns') or []
            new_cols = [c for c in cols if not is_privacy_header(c)]
            if len(new_cols) != len(cols):
                ver['columns'] = new_cols
                changed = True
    if changed:
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print('[META] datasource_meta.json 列名已过滤')
    else:
        print('[META] 无需更新')


def main():
    print('═══ 客户/项目敏感信息清理 ═══')
    clean_db()
    clean_files()
    clean_meta()
    print('═══ 清理完成 ═══')


if __name__ == '__main__':
    main()
