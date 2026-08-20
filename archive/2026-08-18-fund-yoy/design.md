# 设计文档：资金占用同比分析（YoY）

- 变更编号：`20260818-fund-yoy` | 关联规格：CC-006 FR-13

## 1. 数据流

```
付款/收款明细 Excel
   ↓ (fund_analyze 主循环)
每合同 _cashflow（date/type/amount/balance）
   ↓ 合并
global_cashflow（date/type/amount，跨合同逐笔，按日期排序）
   ↓ 返回 data.flows
前端 loadFundDimOverview(data)
   ├─ calcYoY(flows) → 4 张同比 KPI 卡（本期/上期/变化%）
   └─ fundChartMonthCompare(flows) → 月度同比对比图
   └─ fundChartMonthLine(flows, rows) → 趋势图付款/回款曲线恢复
```

## 2. 后端设计（backend/main.py）

### 2.1 全局现金流合并

在 `fund_analyze` 主循环（每个合同构建 `_cashflow` 后）追加：

```python
# 循环外初始化
_global_cashflow = []
# 每合同循环内（_cashflow 构造完成后）
_global_cashflow.extend(_cashflow)
```

- `_cashflow` 元素：`{'flow_id', 'date': '%Y-%m-%d', 'type': 'PAY'|'RECEIVE', 'amount': int(付款为负/回款为正), 'balance': int}`
- 跨合同按日期聚合无需重新排序（前端按 date 过滤求和，与顺序无关）
- `balance` 字段对跨合同合并无全局语义，前端同比计算不使用它（仅取 PAY/RECEIVE 的 amount）

### 2.2 返回结构

`result['data']` 增加：

```python
'flows': _global_cashflow,
```

## 3. 前端设计（frontend/index.html）

### 3.1 同比口径工具函数

```js
function fundYoY(flows){
  // 窗口：本期 2026-01-01~REPORT_CUTOFF(2026-08-12)；上期 2025-01-01~2025-08-12
  const CUT='2026-08-12', P0='2026-01-01', P1='2025-01-01', P2='2025-08-12';
  const agg=(s,e,type)=>{ let t=0; for(const f of flows){ if(f.type!==type)continue; if(f.date>=s&&f.date<=e) t+=f.amount; } return t; };
  const curPay=-agg(P0,CUT,'PAY'), prevPay=-agg(P1,P2,'PAY');
  const curRecv=agg(P0,CUT,'RECEIVE'), prevRecv=agg(P1,P2,'RECEIVE');
  const curNet=curRecv-curPay, prevNet=prevRecv-prevPay;
  // 当前资金占用同比：本期=grand_occupy（外部传入）；上期=截至 P2 的累计净余额负值
  const prevOcc=Math.max(0,-flows.filter(f=>f.date<=P2).reduce((s,f)=>s+f.amount,0));
  const pct=(c,p)=> p===0?null:((c-p)/p*100);
  return {curPay,prevPay,curRecv,prevRecv,curNet,prevNet,prevOcc,
          payPct:pct(curPay,prevPay), recvPct:pct(curRecv,prevRecv),
          netPct:pct(curNet,prevNet), occPct:pct(null,prevOcc)};
}
```

### 3.2 同比 KPI 卡（替换原 3 张静态卡）

```
[📤 累计付款(YTD)]  ¥xx 亿  ↥ +x% vs 去年同期
[📥 累计回款(YTD)]  ¥xx 亿  ↥ +x% vs 去年同期
[⚖️ 净现金流(YTD)]  ¥x 亿    ↧ -x% vs 去年同期
[💰 当前资金占用]  ¥xx 亿  ↧ -x% vs 去年同期
```

- 数值用现有 `fundMoney` 格式化
- 变化样式：`yoy-up`（↥ 青/绿）、`yoy-down`（↧ 橙/红）、`yoy-flat`（— 灰）；**语义色**：付款/回款/净现金流变化中性色（青），当前资金占用上升=红（占用增加压力）、下降=绿
- 结构复用现有 `.cards > .card > .lbl/.val`，附加 `.yoy` 子元素

### 3.3 月度同比对比图 `fundChartMonthCompare(flows)`

- X 轴：`['1月','2月',...,'8月']`（2026 已发生月份 1-8）
- 系列（bar，4 组，`barGap:'30%'`）：
  - `2025付款`（灰蓝 `#5b6b8c`）、`2026付款`（亮蓝 `#4f8cff`）
  - `2025回款`（灰绿 `#3d7a5f`）、`2026回款`（亮绿 `#22c55e`）
- `tooltip.formatter`：展示本月付款/回款及 `↥/↧ x%` 同比
- 注册到 `fundDimCharts['chartMonthCompare']`，加入 `switchFundDimTab` resize 集
- `grid` 复用趋势图配置（`left:64,right:16,top:44,bottom:30`）

### 3.4 趋势图修复

`fundChartMonthLine(flows, rows)` 的 `data.flows` 将由后端提供，付款/回款曲线自动恢复；无需改动该函数逻辑。

## 4. 测试设计

新增 `tests/test_fund_yoy.py`（用例标注 `# CC-006 FR-13`）：

- `test_fund_analyze_has_flows`：`POST /api/fund/analyze` 返回 `data.flows`，且元素含 date/type/amount，付款 amount<0、回款 amount>0
- `test_yoy_window_pay_recv`：给定构造 flows，验证本期/上期付款、回款求和与变化率
- `test_yoy_prev_zero`：上期为 0 时变化率返回 null（前端显示 `—`）

## 5. 影响面

- 后端：仅 `fund_analyze` 一处增加 `_global_cashflow` 合并与 `data.flows` 返回；`fund_metrics` 快照逻辑不变
- 前端：总览 Tab（`loadFundDimOverview`）与新增图表，其它 4 个 Tab 不动
- 性能：flows 约 1 万条 JSON 序列化，量级可忽略
