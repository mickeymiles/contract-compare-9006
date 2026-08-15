"""合同比对引擎核心算法单元测试（断言基于当前真实行为）"""
from compare_engine import (
    normalize_unit, normalize_spec_value, extract_specs,
    _preprocess, _parse_range_op, _range_aware_match,
    _edit_distance, _find_synonym_group, _param_name_similarity,
)


class TestNormalizeUnit:
    """单位归一化：G→GB、T→TB、核→CORES"""

    def test_g_to_gb(self):
        assert normalize_unit('32G') == '32GB'
        assert normalize_unit('32g') == '32GB'

    def test_t_to_tb(self):
        assert normalize_unit('1T') == '1TB'
        assert normalize_unit('2T') == '2TB'

    def test_core(self):
        assert normalize_unit('4核') == '4CORES'
        assert normalize_unit('8Core') == '8CORES'

    def test_standard_unchanged(self):
        assert normalize_unit('64GB') == '64GB'

    def test_empty(self):
        assert normalize_unit('') == ''


class TestNormalizeSpecValue:
    """规格值归一化：去空格 + 统一单位 + 大写"""

    def test_unit(self):
        assert normalize_spec_value('32G') == '32GB'
        assert normalize_spec_value('1T') == '1TB'
        assert normalize_spec_value('4核') == '4CORES'

    def test_strip_space(self):
        assert normalize_spec_value('16GB DDR4') == '16GBDDR4'
        assert normalize_spec_value(' INTEL XEON ') == 'INTELXEON'

    def test_upper(self):
        assert normalize_spec_value('intel xeon') == 'INTELXEON'


class TestExtractSpecs:
    """参数提取：从规格文本提取 cpu/memory/disk"""

    def test_full_extract(self):
        r = extract_specs('CPU: Intel Xeon 16核, 内存: 64GB DDR4, 硬盘: 2TB SSD')
        assert r['cpu'] == 'Intel Xeon 16核'
        assert r['memory'] == '64GB DDR4'
        assert r['disk'] == '2TB SSD'

    def test_no_structured_param(self):
        r = extract_specs('端口: 48x10GbE')
        assert r['cpu'] == ''
        assert r['other'] != ''


class TestPreprocess:
    """文本预处理：全角转半角、统一符号"""

    def test_fullwidth_to_halfwidth(self):
        assert _preprocess('３２ＧＢ　内存，ＣＰＵ') == '32GB 内存,CPU'

    def test_empty(self):
        assert _preprocess('') == ''


class TestRangeOp:
    """范围操作符解析与范围感知比对"""

    def test_parse_range(self):
        op, num, unit = _parse_range_op('不低于1T')
        assert op == '>='
        assert num == 1.0
        assert unit == 'TB'

    def test_range_match_unit_convert(self):
        assert _range_aware_match('1T', '1TB') is True

    def test_range_match_satisfy(self):
        assert _range_aware_match('不低于1T', '2TB') is True


class TestEditDistance:
    """编辑距离"""

    def test_levenshtein(self):
        assert _edit_distance('kitten', 'sitting') == 3
        assert _edit_distance('', 'abc') == 3
        assert _edit_distance('abc', 'abc') == 0


class TestSynonym:
    """同义词组识别与参数名相似度"""

    def test_find_group(self):
        assert _find_synonym_group('处理器') == 'cpu'
        assert _find_synonym_group('ram') == '内存'
        assert _find_synonym_group('硬盘容量') == '硬盘'

    def test_name_similarity_identical(self):
        assert _param_name_similarity('内存', '内存') == 1.0

    def test_name_similarity_synonym(self):
        assert _param_name_similarity('内存', 'RAM') == 0.95
