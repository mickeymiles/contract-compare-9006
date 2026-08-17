# 任务清单：CC-005 回款周期分析测试

- [x] T1 确认回款函数真实行为（列识别/年份过滤/zone 分档/按月累计）—— 已通过代码阅读完成
- [x] T2 编写 `tests/test_payment_cycle.py`
  - [x] T2.1 临时 datasource 构造（versions.json + H.xlsx + R.xlsx）
  - [x] T2.2 用例 1：基础结构（months 3 桶 / regions / province_stats / source_version）
  - [x] T2.3 用例 2：enriched_rows 字段计算（cycle_days / zone / last_payback_date / 年份过滤）
  - [x] T2.4 用例 3：zone 五档边界（0.5 / 1 / 2 / 3 年）
  - [x] T2.5 用例 4：无总合同表降级
  - [x] T2.6 用例 5：无里程碑表降级（cycle_days=0 / zone='0.5以内'）
- [x] T3 运行 `python3 -m pytest tests/test_payment_cycle.py -q` 通过
- [x] T4 回归 contract-compare 既有测试不破坏
- [x] T5 归档 `changes/20260817-cc005-payment-cycle-tests` → `archive/`
- [x] T6 更新 `specs/TRACEABILITY.md`（CC-005 覆盖状态）与 `archive/README.md` 归档记录
