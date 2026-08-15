# 合同比对系统（contract-compare）

合同资金占用与回款周期分析系统。后端 FastAPI + SQLite，前端原生 HTML/JS，支持合同导入、资金占用分析、回款周期分析、指标看板。

## 快速开始

```bash
# 新环境一键初始化（建库 + 导入脱敏种子数据）
./bootstrap.sh

# 启动服务（默认端口 9006，可用环境变量 CC_PORT 覆盖）
python backend/main.py
# 或
CC_PORT=9007 python backend/main.py
```

启动后访问：`http://localhost:9006`

## 目录结构

```
contract-compare/
├── backend/               # FastAPI 后端
│   ├── main.py            # 应用入口与全部 API
│   ├── models.py          # SQLite 模型与 init_db 建表
│   └── requirements.txt   # Python 依赖
├── frontend/              # 前端静态资源（原生 HTML/JS/CSS）
├── scripts/
│   ├── export_seed.py     # 从脱敏库导出种子 SQL（含项目名补充脱敏）
│   └── import_seed.py     # 幂等导入种子数据
├── seeds/
│   ├── seed_data.sql      # 脱敏种子数据（git 发布）
│   └── seed_meta.json     # 种子元信息（来源/脱敏规则/行数）
├── datasource/            # 原始 xlsx（.gitignore 忽略，不入库）
├── name_abbr_mapping.json # 客户名称脱敏映射表（真实名 -> 拼音缩写）
├── tests/                 # pytest 接口冒烟测试
└── bootstrap.sh           # 新环境一键初始化
```

## 数据链路与脱敏

```
原始 xlsx（服务器） → ETL → SQLite 宽表 → 分析页面
                    ↓ 脱敏
           seeds/seed_data.sql（git 发布）
                    ↓ import_seed.py（幂等）
           新环境 SQLite 宽表
```

脱敏策略（**名称替换 + 数值保留**）：

| 字段 | 处理方式 |
|---|---|
| 客户名称 / 甲方 | 拼音缩写（如 `东软集团` → `DRJT`），映射见 `name_abbr_mapping.json` |
| 人员名称 | 姓 + 叉叉（如 `袁善鹏` → `袁叉叉`） |
| 项目名称 | 映射表子串替换 + 补充词典（东软/华为/深信服/松江区/西藏等） |
| 金额 / 日期 / 周期 | **数值原样保留**，分析结果与现网一致 |

重新生成种子（当本地脱敏库更新后）：

```bash
python3 scripts/export_seed.py   # 生成 seeds/seed_data.sql + seed_meta.json
python3 scripts/import_seed.py   # 导入到数据库（幂等）
```

## 测试

```bash
python -m pytest tests/ -v
```

## git 发布注意事项

- `*.xlsx`、`*.db`、`uploads/`、`*.bak_*` 已加入 `.gitignore`，不会误提交
- git 只发布：代码 + `seeds/seed_data.sql`（脱敏种子）+ `name_abbr_mapping.json`（脱敏映射）
- 新环境执行 `./bootstrap.sh` 即可从零到页面可用
