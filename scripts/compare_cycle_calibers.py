#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比 9006 内部两套回款周期口径的差异（真实数据）。

- 页面口径 project_metrics.payment_cycle()：里程碑优先，回退 finance_detail
- 本体口径 ontos_abox.abox_payment_cycle()：finance_detail 优先，里程碑回退

用法: python3 compare_cycle_calibers.py [样本数]
"""
import sqlite3
import sys

sys.path.insert(0, "/home/ubuntu/contract-compare/backend")

from core import project_metrics as pm          # noqa: E402  ② 页面口径
from ontos_abox import abox_payment_cycle       # noqa: E402  ③ 本体口径

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 60
DB = "/home/ubuntu/contract-compare/contract_compare.db"


def main():
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT contract_no, project_no, name FROM core_project "
        "ORDER BY project_id DESC LIMIT ?", (LIMIT,)).fetchall()
    conn.close()

    same, diff, both_none, page_only, ontos_only = 0, 0, 0, 0, 0
    samples = []

    for cno, pno, name in rows:
        no = cno or pno
        if not no:
            continue
        try:
            a = pm.payment_cycle(no)              # ② 页面
            va = a.get("cycle_days")
            sa = a.get("source", "")
        except Exception as e:
            va, sa = None, f"ERR:{e}"
        try:
            b = abox_payment_cycle(no)            # ③ 本体
            vb = b.get("cycle_days") if b.get("success") else None
            sb = b.get("recv_source", "")
        except Exception as e:
            vb, sb = None, f"ERR:{e}"

        if va is None and vb is None:
            both_none += 1
        elif va is not None and vb is None:
            page_only += 1
            samples.append((no, name, va, vb, sa, sb))
        elif va is None and vb is not None:
            ontos_only += 1
            samples.append((no, name, va, vb, sa, sb))
        elif va == vb:
            same += 1
        else:
            diff += 1
            samples.append((no, name, va, vb, sa, sb))

    total = len(rows)
    print(f"样本 {total} 条")
    print("=" * 78)
    print(f"  两者相同          : {same}")
    print(f"  两者都有但值不同  : {diff}   ← 口径差异")
    print(f"  两边都算不出      : {both_none}")
    print(f"  仅页面能算出      : {page_only}")
    print(f"  仅本体能算出      : {ontos_only}")
    print("=" * 78)

    if samples:
        print(f"\n差异明细（前 12 条）：")
        print(f"  {'合同号':<16}{'名称'[:12]:<14}{'页面':>8}{'本体':>8}  来源(页面→本体)")
        print("  " + "-" * 74)
        for no, name, va, vb, sa, sb in samples[:12]:
            nm = (name or "")[:12]
            print(f"  {no:<16}{nm:<14}{str(va):>8}{str(vb):>8}  {sa}→{sb}")

    print(f"\n结论：两套口径在 {(diff + page_only + ontos_only)}/{total} 条上不一致 "
          f"({(diff + page_only + ontos_only) / max(total,1) * 100:.0f}%)")


if __name__ == "__main__":
    main()
