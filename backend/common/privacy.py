"""客户/项目敏感信息脱敏（跨域共享）。"""
import re

# 匹配列名：甲方名称/客户名称/客户简称/客户分类/最终用户/项目名称/项目描述等
# 例外：客户标识（脱敏键，如 QDHEKJ）保留，不视为敏感列
PRIVACY_HEADER_PATTERN = re.compile(
    r"(甲方|客户|业主|招标人|采购人|建设单位|使用单位|最终用户)"
    r"(名称|简称|全称|分类|编号)?$|"
    r"^(项目名称|项目描述|项目简介|合同名称|合同名|合同标题)$|"
    r"主合同客户名称|关键客户"
)


def is_privacy_header(h):
    """判断列名是否为客户/项目敏感信息"""
    return bool(h) and bool(PRIVACY_HEADER_PATTERN.search(str(h)))


def filter_privacy_headers(headers):
    """过滤掉敏感列，返回保留的列索引（数据列下标）"""
    keep = []
    for i, h in enumerate(headers):
        if not is_privacy_header(h):
            keep.append(i)
    return keep


def sanitize_excel_file(path):
    """就地删除 Excel 文件中所有 sheet 的敏感列（客户名/客户简称/项目名等）。

    返回 (changed, dropped_cols)。仅支持 .xlsx；.xls 无法就地改写时返回 (False, [])。
    """
    dropped_cols = set()
    if not str(path).lower().endswith('.xlsx'):
        return False, []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path)
    except Exception:
        return False, []
    modified = False
    for ws in wb.worksheets:
        headers = [str(c.value) if c.value is not None else '' for c in ws[1]]
        drop_idx = [i for i, h in enumerate(headers) if is_privacy_header(h)]
        if not drop_idx:
            continue
        dropped_cols.update(headers[i] for i in drop_idx)
        # 从后往前删除列，避免索引错位
        for i in sorted(drop_idx, reverse=True):
            ws.delete_cols(i + 1, 1)
        modified = True
    if modified:
        wb.save(path)
    wb.close()
    return modified, sorted(dropped_cols)