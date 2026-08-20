# 设计：资金占用多维度分析与预警体系

> 变更编号：`20260818-fund-multidim`
> 日期：2026-08-18 | 状态：已评审

## 技术方案

### 数据链路

```
付款/收款明细表 ─┐
                ├─ FIFO 冲抵（现有 fund_analyze 不改算法）→ fund_metrics 宽表（加维度列+新指标）
总合同表 v2 ────┤      ↑ join 合同编号
里程碑表 v2 ────┘
        │
        ├─ 新增 ETL job「fund-multidim」按 (dim_type × month) 聚合 → indicator_metrics
        ├─ 风险分级（读 risk_config 阈值）→ risk_level 写入 fund_metrics / 聚合结果
        └─ 前端 5 Tab + ECharts（读 /api/fund/dim/*、/api/fund/risk/*）
```

### 核心决策

1. **算法不变**：FIFO 冲抵逻辑（`fund_analyze` 内 1523-1739 行）不修改，仅在聚合阶段扩展。
2. **维度标签通过 join 获得**：在 `fund_analyze` 内新增 `_load_contract_dims()`，读取总合同表与里程碑表最新版本，构建 `{contract_no: dims}` 映射，写入宽表。
3. **敏感键策略**：新增 `_encode_customer_key(name)`（拼音缩写 + 稳定哈希 4 位）；优先用总合同表「客户标识」原文。
4. **风险分级纯函数**：`_calc_risk_level(occupy_days, recv_rate, occupy_intensity, occupy_amount, cfg)` 返回 level + suggestion，便于单测。
5. **宽表指标**：回款率 = total_recv / contract_amount；占用强度 = current_occupy / contract_amount（合同额为 0 时回退按占用金额/累计付款）。
6. **聚合查询走宽表**：`/api/fund/dim/aggregate` 直接对 `fund_metrics` GROUP BY，保证 3 秒内返回（NFR-3）。
7. **前端图表**：复用 index.html 已引入的 ECharts 5.5 + china.json 地图；新增 `fundPanel` 下 5 个 Tab 容器与渲染函数。

## 涉及文件

| 文件 | 改动说明 |
|------|----------|
| `backend/models.py` | `fund_metrics` 加维度列 + 新指标列；新建 `risk_config` 表 |
| `backend/main.py` | `fund_analyze` 增加维度 join 与宽表扩展；新增 `/api/fund/dim/*`、`/api/fund/risk/*`、`/api/fund/dim/export`、ETL job 注册 |
| `backend/excel_handler.py` | `sanitize_excel_file` 调整：保留客户标识列（其余敏感列仍删） |
| `frontend/index.html` | 资金页重构：5 Tab + 10 图表 + 下钻 + 导出按钮 |
| `tests/test_fund_multidim.py` | 新增测试：维度关联、风险分级、趋势预警、聚合、导出 |

## 数据模型变更

### fund_metrics 加列（ALTER TABLE 兼容）

```sql
ALTER TABLE fund_metrics ADD COLUMN region TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN province TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN dept TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN biz_line TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN industry TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN customer_key TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN project_status TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN contract_status TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN sign_year TEXT DEFAULT '';
ALTER TABLE fund_metrics ADD COLUMN recv_rate REAL DEFAULT 0;      -- 回款率
ALTER TABLE fund_metrics ADD COLUMN occupy_intensity REAL DEFAULT 0; -- 占用强度
ALTER TABLE fund_metrics ADD COLUMN risk_level TEXT DEFAULT 'healthy'; -- 风险等级
```

### 新建 risk_config 表

```sql
CREATE TABLE IF NOT EXISTS risk_config (
    key TEXT PRIMARY KEY,
    value REAL NOT NULL,
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
-- 默认行：days_green=30, days_yellow=90, days_orange=180, recv_rate=0.5,
--          intensity=0.5, amount_high=1000000, trend_months=2
```

## 备选方案（可选）

- **实时 join 而非写宽表**：查询时动态 join 总合同表。未选：维度聚合需秒级返回，且总合同表可能变更，预写宽表更稳定。
- **客户名称直接编码进宽表**：直接对名称做不可逆哈希入库。未选：与现有种子数据 `QDHEKJ` 风格（拼音缩写）不一致，无法人工辨识集合。

## 兼容性说明

- 新增路由均为新增，不破坏现有 `/api/fund/*`。
- `fund_metrics` 增量加列，旧库自动 ALTER；宽表为空时提示先跑分析。
- 敏感清洗策略变化影响 `sanitize_excel_file` 与 TC-2，测试同步更新。
