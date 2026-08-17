"""Excel 处理工具单元测试"""
# 规格编号: CC-002 数据源导入（表头清洗/列模糊映射）
from excel_handler import safe_str, safe_float, find_column, _clean_header


class TestSafeStr:
    def test_none(self):
        assert safe_str(None) == ''

    def test_strip(self):
        assert safe_str('  测试  ') == '测试'

    def test_number(self):
        assert safe_str(123) == '123'


class TestSafeFloat:
    def test_none(self):
        assert safe_float(None) == 0

    def test_number(self):
        assert safe_float('3.14') == 3.14

    def test_invalid(self):
        assert safe_float('abc') == 0
        assert safe_float('') == 0


class TestCleanHeader:
    def test_remove_newline(self):
        assert _clean_header('品牌\n名称') == '品牌名称'

    def test_remove_long_bracket(self):
        assert _clean_header('品牌（如指定请填写）') == '品牌'

    def test_keep_short_bracket(self):
        assert _clean_header('单价（元）') == '单价（元）'

    def test_lower(self):
        assert _clean_header('NAME') == 'name'


class TestFindColumn:
    def test_find_by_alias(self):
        headers = ['序号', '设备名称', '型号规格', '数量']
        assert find_column(headers, 'device_name') == 1
        assert find_column(headers, 'device_model') == 2
        assert find_column(headers, 'qty') == 3

    def test_not_found(self):
        assert find_column(['测试列甲', '测试列乙'], 'device_name') == -1
