# Delta Spec：CC-005 回款周期分析（测试覆盖）

> 本 delta 不修改任何既有 Requirement，仅新增测试标准（TC）与测试位置声明，
> 用于将"测试绑定规格"落地到 CC-005。

## ADDED Requirements

### Requirement: 回款周期分析测试覆盖

系统 SHALL 为回款周期分析提供单元测试，覆盖：双数据源加载、按月累计、
周期区间划分（zone 五档）、年份过滤与数据源缺失降级。

#### Scenario: 回款周期测试全绿

- GIVEN 已构造临时 datasource（总合同表 + 项目里程碑表 + versions.json）
- WHEN 运行 `python3 -m pytest tests/test_payment_cycle.py -q`
- THEN 全部用例通过，且不依赖真实服务

## MODIFIED Requirements

无。

## REMOVED Requirements

无。
