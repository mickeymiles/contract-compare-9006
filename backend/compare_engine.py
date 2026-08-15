"""
合同比对系统 — 智能三层比对引擎 v2.0

第一层：规则引擎 — 操作符归一化 + 单位换算 + 数值逻辑判断
第二层：实体匹配 — 同义词词典 + 编辑距离 + 指标名称变体识别
第三层：语义向量 — sentence-transformers 余弦相似度 + 阈值分层

核心原则：合同是基准，供应商逐条核对。
比对方向：合同要求 → 检查供应商是否满足。
"""
import re
import json
import os
from models import get_db


# ═══════════════════════════════════════════
#  第〇层：文本预处理
# ═══════════════════════════════════════════

def _preprocess(text: str) -> str:
    """文本预处理：全角转半角、统一符号、去噪"""
    if not text:
        return ''
    # 全角转半角
    result = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            result.append(' ')
        else:
            result.append(ch)
    text = ''.join(result)
    # 统一比较符号
    text = text.replace('≥', '≥').replace('≧', '≥')
    text = text.replace('≤', '≤').replace('≦', '≤')
    text = text.replace('！', '!').replace('？', '?')
    text = text.replace('：', ':').replace('；', ';').replace('，', ',')
    # 去除多余空格
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ═══════════════════════════════════════════
#  第一层：操作符归一化 + 单位换算
# ═══════════════════════════════════════════

# 操作符中文 → 符号映射表
OPERATOR_MAP = {
    '≥': '>=', '≧': '>=', '大于等于': '>=', '大于或等于': '>=',
    '不低于': '>=', '不小于': '>=', '最少': '>=', '最低': '>=',
    '不少于': '>=', '至少': '>=', '下限': '>=',
    '≤': '<=', '≦': '<=', '小于等于': '<=', '小于或等于': '<=',
    '不高于': '<=', '不大于': '<=', '最多': '<=', '最高': '<=',
    '不超过': '<=', '上限': '<=',
    '>': '>', '大于': '>', '高于': '>', '超过': '>', '多于': '>',
    '<': '<', '小于': '<', '低于': '<', '少于': '<',
    '=': '=', '等于': '=', '为': '=', '是': '=', '额定': '=', '标配': '=',
}

# 单位归一化映射表（含换算系数，以最小单位为基准）
# 格式: 单位 → (标准单位, 换算系数)
# 注意：裸 'G' 'T' 等由 normalize_unit() 预处理为 GB/TB，此处只处理标准单位
UNIT_NORMALIZE = {
    # 存储（大单位优先匹配）
    'TB': ('TB', 1), 'T': ('TB', 1),
    'GB': ('GB', 1), 'MB': ('MB', 1), 'KB': ('KB', 1),
    # 频率
    'GHZ': ('GHz', 1), 'GHz': ('GHz', 1),
    'MHZ': ('MHz', 1), 'MHz': ('MHz', 1),
    # 带宽
    'MBPS': ('Mbps', 1), 'Mbps': ('Mbps', 1),
    'GBPS': ('Gbps', 1), 'Gbps': ('Gbps', 1),
    # 功率
    'W': ('W', 1), 'KW': ('W', 1000), 'kW': ('W', 1000),
    # 计算
    '核': ('cores', 1), 'CORES': ('cores', 1), 'CORE': ('cores', 1),
    # 通用
    '个': ('个', 1), '台': ('台', 1), '套': ('套', 1),
    '年': ('年', 1), 'Y': ('年', 1), 'YR': ('年', 1),
    # 电压电流
    'V': ('V', 1), 'A': ('A', 1),
    'MM': ('mm', 1), 'CM': ('cm', 1), 'M': ('m', 1),
    'KG': ('kg', 1), 'G': ('g', 1),
}


def _normalize_op_text(text: str) -> str:
    """将文本中的中文操作符替换为符号"""
    for cn_op, sym_op in sorted(OPERATOR_MAP.items(), key=lambda x: -len(x[0])):
        if cn_op in text:
            text = text.replace(cn_op, sym_op)
    return text


def _parse_range_op(val: str):
    """提取值中的范围运算符和数值。
    返回 (operator: str, number: float|None, unit: str)
    例如: '不低于1T' → ('>=', 1.0, 'T'), '系统盘≥64G' → ('>=', 64.0, 'G')
    """
    text = _preprocess(val)
    text = _normalize_op_text(text)

    # 先尝试在字符串任意位置匹配 操作符+数值+单位
    m = re.search(r'(>=|<=|>|<|=)\s*(\d+\.?\d*)\s*([A-Za-z\u4e00-\u9fff]*)', text)
    if m:
        op = m.group(1)
        num = float(m.group(2))
        unit = m.group(3).strip().upper()
        # 去除末尾标点（。.，, 等）
        unit = re.sub(r'[。，,\.\s]+$', '', unit)
        if unit in UNIT_NORMALIZE:
            base_unit, factor = UNIT_NORMALIZE[unit]
            num = num * factor
            unit = base_unit
        return (op, num, unit)

    # 无操作符，尝试提取纯数值
    num_match = re.search(r'(\d+\.?\d*)\s*([A-Za-z\u4e00-\u9fff]+)', text)
    if num_match:
        num = float(num_match.group(1))
        unit = num_match.group(2).strip().upper()
        unit = re.sub(r'[。，,\.\s]+$', '', unit)
        if unit in UNIT_NORMALIZE:
            base_unit, factor = UNIT_NORMALIZE[unit]
            num = num * factor
            unit = base_unit
        return (None, num, unit)

    return (None, None, text)


def _range_aware_match(contract_val: str, supplier_val: str) -> bool:
    """范围感知比对：合同有 ≥/≤ 等运算符时，判断供应商数值是否满足条件。
    支持单位换算（如 T↔TB）。
    """
    # 先做规整化
    c_val = _preprocess(contract_val)
    s_val = _preprocess(supplier_val)
    c_val = _normalize_op_text(c_val)
    s_val = _normalize_op_text(s_val)

    c_op, c_num, c_unit = _parse_range_op(c_val)
    s_op, s_num, s_unit = _parse_range_op(s_val)

    # 双方都没有数值 → 回退到文本比对
    if c_num is None or s_num is None:
        return c_val == s_val

    # 单位不一致 → 尝试换算
    if c_unit != s_unit:
        # 尝试同类型单位换算
        # TB/GB 互转
        storage_units = {'TB': 1, 'GB': 1000, 'MB': 1000000, 'KB': 1000000000}
        if c_unit in storage_units and s_unit in storage_units:
            # 统一到 TB
            c_tb = c_num * storage_units[c_unit] / storage_units['TB']
            s_tb = s_num * storage_units[s_unit] / storage_units['TB']
            c_num, s_num = c_tb, s_tb
            c_unit = s_unit = 'TB'
        # GHz/MHz 互转
        elif c_unit == 'GHZ' and s_unit == 'MHZ':
            s_num = s_num / 1000
            s_unit = 'GHZ'
        elif c_unit == 'MHZ' and s_unit == 'GHZ':
            c_num = c_num / 1000
            c_unit = 'GHZ'
        # W/KW 互转
        elif c_unit == 'W' and s_unit == 'KW':
            s_num = s_num * 1000
            s_unit = 'W'
        elif c_unit == 'KW' and s_unit == 'W':
            c_num = c_num * 1000
            c_unit = 'W'
        else:
            return False  # 无法换算，不匹配

    # 合同有范围运算符 → 判断供应商数值是否满足
    if c_op == '>=':
        return s_num >= c_num
    elif c_op == '<=':
        return s_num <= c_num
    elif c_op == '>':
        return s_num > c_num
    elif c_op == '<':
        return s_num < c_num
    # 合同无运算符 → 精确匹配
    return abs(c_num - s_num) < 0.001  # 浮点容差


def _range_explain(contract_val: str, supplier_val: str) -> str:
    """生成范围比对的解释文本"""
    c_op, c_num, c_unit = _parse_range_op(_normalize_op_text(_preprocess(contract_val)))
    s_op, s_num, s_unit = _parse_range_op(_normalize_op_text(_preprocess(supplier_val)))
    if c_num is None or s_num is None:
        return f'文本不匹配：「{contract_val}」≠「{supplier_val}」'
    if c_unit != s_unit:
        return f'单位不一致：合同「{c_unit}」≠ 报价「{s_unit}」（无法自动换算）'
    if c_op:
        satisfied = _range_aware_match(contract_val, supplier_val)
        verb = '✅满足' if satisfied else '❌不满足'
        return f'{verb}：合同要求{c_op}{c_num}{c_unit}，报价提供{s_num}{s_unit}'
    if abs(c_num - s_num) < 0.001:
        return f'数值一致：{c_num}{c_unit}'
    return f'数值不匹配：合同{c_num}{c_unit} ≠ 报价{s_num}{s_unit}'


# ═══════════════════════════════════════════
#  第二层：同义词词典 + 编辑距离
# ═══════════════════════════════════════════

# 指标名称同义词词典
SYNONYM_DICT = {
    'cpu': ['cpu', '处理器', '中央处理器', 'cpu型号', 'cpu规格', 'cpu参数', '处理器型号'],
    '内存': ['内存', '运行内存', 'ram', 'memory', '内存大小', '内存容量', '内存规格', '系统内存'],
    '硬盘': ['硬盘', '磁盘', '存储', '硬盘容量', '磁盘容量', '存储容量',
             '系统硬盘', '数据硬盘', 'ssd', 'hdd', '硬盘规格', '存储空间', '硬盘大小'],
    '网口': ['网口', '网络接口', '网卡', '以太网口', '网络端口', 'rj45', '光口', '电口'],
    '电源': ['电源', '供电', '冗余电源', '双电源', '电源模块', 'psu', '电源规格'],
    '风扇': ['风扇', '散热', '风冷', '散热风扇', '冷却'],
    '显卡': ['显卡', 'gpu', '图形处理器', '显示卡', '图形卡', 'gpu卡'],
    '操作系统': ['操作系统', 'os', '系统', '操作系统版本', '系统版本'],
    '质保': ['质保', '保修', '维保', '售后服务', '质保期', '保修期', '服务期限'],
    '尺寸': ['尺寸', '规格尺寸', '外形尺寸', '大小', '体积', '长宽高'],
    '重量': ['重量', '净重', '毛重', '自重'],
    '功耗': ['功耗', '功率', '额定功率', '最大功耗', 'tdp', '典型功耗'],
    '温度': ['温度', '工作温度', '运行温度', '环境温度', '耐温'],
    '湿度': ['湿度', '工作湿度', '运行湿度', '环境湿度'],
    '防护等级': ['防护等级', 'ip等级', '防护', '防水', '防尘', 'ip'],
    '接口': ['接口', '端口', 'i/o', 'io接口', '输入输出', '外设接口', '扩展接口'],
    'raid': ['raid', '磁盘阵列', '阵列卡', 'raid卡', 'raid级别', 'raid等级'],
    '内存插槽': ['内存插槽', 'dimm插槽', '内存槽位', 'dimm槽'],
    '扩展插槽': ['扩展插槽', 'pcie', 'pci-e', '扩展槽', 'pcie插槽'],
    '带宽': ['带宽', '吞吐量', '吞吐', '速率', '传输速率', '网络带宽'],
    '延迟': ['延迟', '时延', '延时', '响应时间', 'latency'],
    '并发': ['并发', '并发数', '并发连接', '并发连接数', '同时连接数'],
}


def _edit_distance(s1: str, s2: str) -> int:
    """Levenshtein 编辑距离"""
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            insert = prev[j + 1] + 1
            delete = curr[j] + 1
            replace = prev[j] + (0 if c1 == c2 else 1)
            curr.append(min(insert, delete, replace))
        prev = curr
    return prev[-1]


def _jaccard_similarity(s1: str, s2: str) -> float:
    """Jaccard 相似度（2-gram 字符级）"""
    if not s1 or not s2:
        return 0.0
    # 字符 2-gram
    def _ngrams(s, n=2):
        s = s.lower().replace(' ', '')
        return set(s[i:i+n] for i in range(len(s)-n+1))
    g1 = _ngrams(s1)
    g2 = _ngrams(s2)
    if not g1 or not g2:
        return 0.0
    intersection = len(g1 & g2)
    union = len(g1 | g2)
    return intersection / union if union > 0 else 0.0


def _find_synonym_group(word: str) -> str:
    """查找词语所属的同义词组，返回标准指标名"""
    word_lower = word.lower().strip()
    # 精确匹配
    for std_name, synonyms in SYNONYM_DICT.items():
        if word_lower in [s.lower() for s in synonyms]:
            return std_name
    # 子串匹配（处理「系统硬盘容量」→ 匹配「硬盘」）
    for std_name, synonyms in SYNONYM_DICT.items():
        for syn in synonyms:
            if syn.lower() in word_lower or word_lower in syn.lower():
                return std_name
    return word


def _param_name_similarity(name1: str, name2: str) -> float:
    """计算两个参数名的相似度。先查同义词组，再算编辑距离比例。"""
    n1 = _preprocess(name1).lower().strip()
    n2 = _preprocess(name2).lower().strip()
    if not n1 or not n2:
        return 0.0

    # 完全相同
    if n1 == n2:
        return 1.0

    # 同义词组判断
    g1 = _find_synonym_group(n1)
    g2 = _find_synonym_group(n2)
    if g1 == g2:
        return 0.95  # 同组，高置信

    # Jaccard 相似度
    jac = _jaccard_similarity(n1, n2)

    # 编辑距离比例
    max_len = max(len(n1), len(n2))
    if max_len == 0:
        return 0.0
    ed_ratio = 1 - (_edit_distance(n1, n2) / max_len)

    # 取较高者
    return max(jac, ed_ratio)


# ═══════════════════════════════════════════
#  第三层：语义向量匹配（jieba 分词 + Jaccard 词重叠）
# ═══════════════════════════════════════════


def _jieba_cut(text: str) -> list:
    """jieba 分词，fallback 到字符 2-gram"""
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        # Fallback: 字符 2-gram
        return [text[i:i+2] for i in range(len(text)-1)]


def _semantic_similarity(text1: str, text2: str) -> float:
    """语义相似度：jieba 分词 + Jaccard 词重叠率"""
    if not text1 or not text2:
        return 0.0
    text1 = _preprocess(text1)
    text2 = _preprocess(text2)
    if text1 == text2:
        return 1.0
    if len(text1) < 4 or len(text2) < 4:
        return -1.0

    try:
        words1 = set(_jieba_cut(text1))
        words2 = set(_jieba_cut(text2))
        # 过滤单字词和纯数字
        words1 = {w.strip() for w in words1 if len(w.strip()) > 1 and not w.strip().isdigit()}
        words2 = {w.strip() for w in words2 if len(w.strip()) > 1 and not w.strip().isdigit()}
        if not words1 or not words2:
            return -1.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0
    except Exception:
        return -1.0


# ═══════════════════════════════════════════
#  旧版兼容函数（保留接口，内部升级）
# ═══════════════════════════════════════════

def normalize_unit(val: str) -> str:
    """单位归一化：32G→32GB, 4核→4cores, 1T→1TB"""
    if not val:
        return ''
    v = _preprocess(val).upper()
    v = re.sub(r'(\d+)G$', r'\1GB', v)
    v = re.sub(r'(\d+)GBB', r'\1GB', v)
    v = re.sub(r'(\d+)T$', r'\1TB', v)
    v = re.sub(r'(\d+)TBB', r'\1TB', v)
    v = v.replace('核', 'CORES')
    v = re.sub(r'(\d+)CORE$', r'\1CORES', v)
    return v


def normalize_spec_value(val: str) -> str:
    """规整化参数值：去空格、统一大小写、统一单位"""
    if not val:
        return ''
    v = _preprocess(val)
    v = normalize_unit(v)
    v = v.replace(' ', '')
    return v.upper()


# ═══════════════════════════════════════════
#  参数提取
# ═══════════════════════════════════════════

def extract_specs(specs_full: str) -> dict:
    """从完整规格文本中提取结构化参数"""
    result = {"cpu": "", "memory": "", "disk": "", "other": ""}
    if not specs_full:
        return result
    text = specs_full
    cpu_match = re.search(r'(?:CPU|处理器|核心)[:：]?\s*([^,，;\n]+)', text, re.I)
    if cpu_match:
        result["cpu"] = cpu_match.group(1).strip()
    mem_match = re.search(r'(?:内存|RAM|Memory)[:：]?\s*([^,，;\n]+)', text, re.I)
    if mem_match:
        result["memory"] = mem_match.group(1).strip()
    disk_match = re.search(r'(?:硬盘|SSD|HDD|存储)[:：]?\s*([^,，;\n]+)', text, re.I)
    if disk_match:
        result["disk"] = disk_match.group(1).strip()
    if not any(result.values()):
        result["other"] = text.strip()
    return result


# ═══════════════════════════════════════════
#  需求片段拆分
# ═══════════════════════════════════════════

def _tokenize(text: str) -> list:
    """将规格文本拆为需求片段，过滤无意义的碎片"""
    if not text:
        return []
    text = _preprocess(text)
    text = text.replace('\n', ',').replace('\\n', ',')
    text = text.replace(';', '/').replace(',', '/').replace(';', '/')
    text = text.replace('，', '/').replace('、', '/').replace('；', '/')
    text = text.replace('。', '/').replace('．', '/').replace('！', '/').replace('？', '/')

    tokens = []
    for segment in text.split('/'):
        segment = segment.strip()
        if not segment:
            continue
        if ' ' in segment and any(c.isascii() and c.isalpha() for c in segment):
            tokens.extend(t.strip() for t in segment.split() if t.strip())
        else:
            tokens.append(segment)

    out = []
    for t in tokens:
        t = t.strip()
        if len(t) < 2:
            continue
        if re.match(r'^[\d.]+$', t):
            continue
        if re.match(r'^[※★●■◆▼▲△▽○◎◇♦◊\-*#]+$', t):
            continue
        if t in ('配置数量', '数量', '台数', '件数', '个数'):
            continue
        if re.match(r'^\d+台$', t):
            continue
        if re.search(r'数量\s*\d+\s*台', t):
            continue
        out.append(t)
    return out


def _normalize_for_match(s: str) -> str:
    """规整化以便匹配：统一单位、缩写"""
    s = _preprocess(s)
    s = s.replace('英寸', '寸').replace('英', '')
    s = s.replace('毫安', 'mAh').replace('mAh时', 'mAh')
    s = s.replace('内存', '').replace('存储', '')
    s = s.replace('米', 'm').replace('厘米', 'cm')
    s = s.replace('公斤', 'kg').replace('千克', 'kg')
    return s


def _token_found(token: str, target_text: str) -> tuple:
    """
    检查合同需求是否在供应商文本中出现。三层比对：
    1. 规则引擎：数字+范围判断
    2. 分词子串匹配 + 同义词
    3. 语义向量兜底
    返回: (found: bool, method: str)
    """
    if not token or not target_text:
        return False, '', ''

    token = _preprocess(token)
    target_text = _preprocess(target_text)

    t_norm = _normalize_for_match(token)
    target_norm = _normalize_for_match(target_text)

    # ── 第一层：规则引擎 ──
    # 1.0 直接子串
    if t_norm in target_norm:
        return True, '', ''

    # 1.1 范围感知检测（扩大匹配范围）
    has_range_op = re.search(r'(>=|<=|>|<)\s*\d+\.?\d*', _normalize_op_text(t_norm))
    if has_range_op:
        range_op_match = re.search(r'(>=|<=|>|<)\s*(\d+\.?\d*)\s*([A-Za-z\u4e00-\u9fff]*)',
                                   _normalize_op_text(t_norm))
    else:
        range_op_match = None
    if range_op_match:
        op_sym = range_op_match.group(1)
        ct_num = float(range_op_match.group(2))
        ct_unit = range_op_match.group(3).strip().upper()

        # 单位归一化
        if ct_unit in UNIT_NORMALIZE:
            base_u, factor = UNIT_NORMALIZE[ct_unit]
            ct_num = ct_num * factor
            ct_unit = base_u

        # 在目标文本中找所有数值+单位
        target_nums = re.findall(r'(\d+\.?\d*)\s*([A-Za-z\u4e00-\u9fff]*)', target_norm)
        for t_num_str, t_unit in target_nums:
            t_unit_orig = t_unit
            t_num = float(t_num_str)
            t_unit = t_unit.strip().upper()
            if t_unit in UNIT_NORMALIZE:
                base_u, factor = UNIT_NORMALIZE[t_unit]
                t_num = t_num * factor
                t_unit = base_u
            # 单位比对
            if ct_unit:
                if not t_unit:
                    continue
                # 供应商单位可能捕获多余文字（如"年原厂维保"），用前缀匹配
                if not t_unit.startswith(ct_unit):
                    continue
                # 截取匹配的单位部分用于显示
                t_unit = ct_unit
                t_unit_orig = ct_unit
            sp_detail = f'{t_num_str}{t_unit_orig}'
            if op_sym == '>=' and t_num >= ct_num:
                return True, 'range', sp_detail
            if op_sym == '<=' and t_num <= ct_num:
                return True, 'range', sp_detail
            if op_sym == '>' and t_num > ct_num:
                return True, 'range', sp_detail
            if op_sym == '<' and t_num < ct_num:
                return True, 'range', sp_detail

    # 1.2 数字+单位模式
    num_unit = re.findall(r'(\d+\.?\d*)\s*([A-Za-z\u4e00-\u9fff]+)', t_norm)
    if num_unit:
        all_found = True
        for num, unit in num_unit:
            pattern = num + unit
            if pattern in target_norm:
                continue
            if num in target_norm and unit in target_norm:
                continue
            if num in target_norm:
                continue
            all_found = False
            break
        if all_found:
            eng_words = re.findall(r'[A-Za-z]{3,}', token)
            if eng_words:
                eng_missing = [w for w in eng_words if w.lower() not in target_text.lower()]
                if eng_missing:
                    return False, '', ''
            return True, '', ''

    # ── 第二层：同义词 + 分词匹配 ──
    # 2.1 同义词组判断（大幅放宽）
    tok_group = _find_synonym_group(token)
    # 在目标文本中找所有可能的指标名
    target_parts = re.split(r'[/,;，；\s]+', target_text)
    for part in target_parts:
        part = part.strip()
        if not part:
            continue
        part_group = _find_synonym_group(part)
        if tok_group == part_group:
            return True, 'synonym', ''

    # 2.2 编辑距离匹配（关键词级）
    words = re.findall(r'[\u4e00-\u9fff\w]{2,}', t_norm)
    if words:
        missing = [w for w in words if w not in target_norm]
        if missing:
            # 对每个缺失词做编辑距离匹配
            target_words = re.findall(r'[\u4e00-\u9fff\w]{2,}', target_norm)
            all_matched = True
            for mw in missing:
                best_sim = max((_jaccard_similarity(mw, tw) for tw in target_words), default=0)
                if best_sim < 0.7:
                    all_matched = False
                    break
            if all_matched:
                return True, 'fuzzy', ''
            # 70% CJK 字符匹配
            cjk_chars = [c for c in t_norm if '\u4e00' <= c <= '\u9fff']
            if cjk_chars:
                found_cjk = sum(1 for c in cjk_chars if c in target_norm)
                if found_cjk / len(cjk_chars) >= 0.7:
                    return True, 'fuzzy', ''
            if len(missing) < len(words) * 0.5:
                nums = re.findall(r'\d+', token)
                if not nums:
                    return False, '', ''
                if not all(n in target_text for n in nums):
                    return False, '', ''
        return True, '', ''

    # ── 第三层：语义向量 ──
    # 纯文本无数字 → 尝试语义匹配
    has_nums = bool(re.search(r'\d', token))
    if not has_nums and len(token) >= 6:
        sim = _semantic_similarity(token, target_text)
        if sim > 0.85:
            return True, 'semantic', ''
        if sim >= 0:
            return False, f'semantic_low({sim:.2f})', ''

    return False, '', ''


# ═══════════════════════════════════════════
#  参数比对（核心）
# ═══════════════════════════════════════════

def compare_params(contract_specs: dict, supplier_specs: dict,
                   contract_full: str = '', supplier_full: str = '') -> tuple:
    """
    比对参数 — 合同为基准，逐条检查供应商是否满足。
    返回: (is_match: bool, diff_text: str, match_note: str)
      match_note: ''=完全匹配, '判断符合'=范围/同义词语义判断通过
    """
    range_matched = False

    # 1. 结构化字段比对（CPU/内存/硬盘）—— 带范围判断
    struct_diffs = []
    struct_range_matched = False
    has_structured = any(
        contract_specs.get(k) or supplier_specs.get(k)
        for k in ['cpu', 'memory', 'disk']
    )
    if has_structured:
        for key, label in [("cpu", "CPU"), ("memory", "内存"), ("disk", "硬盘")]:
            c_val = normalize_spec_value(contract_specs.get(key, ''))
            s_val = normalize_spec_value(supplier_specs.get(key, ''))
            if c_val and s_val:
                if c_val == s_val:
                    continue
                if _range_aware_match(c_val, s_val):
                    struct_range_matched = True
                    continue
                struct_diffs.append(f"❗{label}: 合同「{contract_specs.get(key, '')}」→ 报价「{supplier_specs.get(key, '')}」")
                struct_diffs.append(f"   ⚡判断：{_range_explain(c_val, s_val)}")

    # 2. 非结构化文本 — 需求逐条核对
    ct_text = _preprocess(contract_full or '').strip()
    sp_text = _preprocess(supplier_full or '').strip()

    if not ct_text and not sp_text:
        if struct_range_matched:
            return True, '', '判断符合'
        return True, '', ''
    if not ct_text:
        if struct_range_matched:
            return True, '', '判断符合'
        return True, '', ''
    if not sp_text:
        if struct_range_matched:
            return True, '', '判断符合'
        return False, '❗供应商未填写参数描述', ''
    if ct_text == sp_text:
        if struct_range_matched:
            return True, '', '判断符合'
        return True, '', ''

    # 合同文本不像真实参数规格 → 跳过参数比对
    _spec_indicators = [
        r'\d+\s*(GB|TB|MB|G|T|核|CORES|GHz|MHz|W|瓦|V|A|mm|cm|m|kg|寸|英寸|U|RU|Mbps|Gbps|RPM|转)',
        r'[≥≤><=]\s*\d+', r'\d+\s*[≥≤><=]',
        r'(支持|最大|最小|不低于|不高于|吞吐|并发|延迟|带宽|存储|容量)',
        r'(CPU|内存|硬盘|SSD|HDD|RAID|网口|电源|风扇|显卡|操作系统|质保|防护|raid)',
    ]
    has_real_specs = any(re.search(pat, ct_text, re.I) for pat in _spec_indicators)
    if not has_real_specs:
        if struct_range_matched:
            return True, '', '判断符合'
        return True, '', ''

    ct_tokens = _tokenize(ct_text)
    sp_tokens = _tokenize(sp_text)

    if not ct_tokens:
        return True, '', ''

    # 逐条核对
    unmatched = []
    match_methods = set()
    match_details = []
    for token in ct_tokens:
        found, method, sp_val = _token_found(token, sp_text)
        if not found:
            unmatched.append(f"❌ 合同要求「{token}」，供应商未注明")
        elif method:
            match_methods.add(method)
            if method == 'range' and sp_val:
                # 清理 token 末尾标点符号
                clean_token = token.rstrip('。！？，、；：.!?,;:')
                match_details.append(f"{clean_token}: 合同要求{clean_token}，供应商{sp_val} → 范围判断通过")

    # 供应商多写的内容（仅提示）
    extras = []
    for token in sp_tokens:
        f, *_ = _token_found(token, ct_text)
        if not f:
            extras.append(f"ℹ️ 供应商多写「{token}」（合同中无此要求）")

    if unmatched:
        lines = unmatched
        if extras:
            lines.append('')
            lines.extend(extras[:3])
        return False, '\n'.join(lines), ''

    # 判断匹配类型
    if struct_range_matched:
        match_methods.add('range')
    match_note_parts = []
    if match_details:
        match_note = '判断符合: ' + '; '.join(match_details)
    else:
        if 'range' in match_methods:
            match_note_parts.append('范围判断')
        if 'synonym' in match_methods:
            match_note_parts.append('同义词匹配')
        if 'fuzzy' in match_methods:
            match_note_parts.append('模糊匹配')
        if 'semantic' in match_methods:
            match_note_parts.append('语义匹配')
        match_note = '判断符合' if match_note_parts else ''

    extras_text = '\n'.join(extras[:3]) if extras else ''
    return True, extras_text if extras else '', match_note


# ═══════════════════════════════════════════
#  匹配键规整化
# ═══════════════════════════════════════════

def _match_key(name: str, model: str) -> tuple:
    """规整化匹配键：去空格、去换行、统一全半角括号"""
    n = (name or '').strip().replace('\n', '').replace('\r', '').replace('（', '(').replace('）', ')').replace(' ', '').lower()
    m = (model or '').strip().replace('\n', '').replace('\r', '').replace('（', '(').replace('）', ')').replace(' ', '').lower()
    return (m, n)


# ═══════════════════════════════════════════
#  模糊匹配层
# ═══════════════════════════════════════════

def _model_prefix_overlap(m1: str, m2: str) -> float:
    """型号前缀重叠率。如 AF-1000-L2100-U9 vs AF-1000-L2100-P9 → 0.75"""
    if not m1 or not m2:
        return 0.0
    tokens1 = re.split(r'[-/\s]+', m1.lower())
    tokens2 = re.split(r'[-/\s]+', m2.lower())
    match_count = 0
    for t1, t2 in zip(tokens1, tokens2):
        if t1 == t2:
            match_count += 1
        else:
            break
    max_len = max(len(tokens1), len(tokens2))
    return match_count / max_len if max_len > 0 else 0.0


def _fuzzy_find_supplier(ct_name: str, ct_model: str,
                          supplier_index: dict,
                          matched_supplier_ids: set) -> tuple:
    """模糊匹配：精确key匹配失败时，按型号/名称相似度找最佳供应商。"""
    ct_full = f"{ct_name} {ct_model}".strip().lower()
    ct_model_norm = (ct_model or '').strip().lower()
    ct_name_norm = (ct_name or '').strip().lower()

    model_patterns = re.findall(r'[A-Za-z0-9][A-Za-z0-9\-/._]+[A-Za-z0-9]', ct_full)

    best_candidates = []
    best_score = 0.0
    best_note = ''

    for key, candidates in supplier_index.items():
        sp_model, sp_name = key
        available = [c for c in candidates if c['id'] not in matched_supplier_ids]
        if not available:
            continue

        score = 0.0
        notes = []

        if sp_model and len(sp_model) >= 4:
            if sp_model in ct_full:
                score += 50
                notes.append(f'型号"{sp_model}"在合同中找到')
            elif ct_model_norm and ct_model_norm in sp_model:
                score += 40
                notes.append('合同型号是供应商型号的子串')
            else:
                prefix_score = _model_prefix_overlap(ct_model_norm, sp_model)
                if prefix_score >= 0.5:
                    score += int(prefix_score * 40)
                    notes.append('型号前缀匹配')
                for mp in model_patterns:
                    mp_l = mp.lower()
                    if mp_l in sp_model or sp_model in mp_l:
                        score += 30
                        notes.append('型号片段匹配')
                        break
                    ps = _model_prefix_overlap(mp_l, sp_model)
                    if ps >= 0.5:
                        score += int(ps * 30)
                        notes.append('型号片段前缀匹配')
                        break

        if sp_name and ct_name_norm:
            ct_tokens = set(re.findall(r'[\u4e00-\u9fff\w]{2,}', ct_name_norm))
            sp_tokens = set(re.findall(r'[\u4e00-\u9fff\w]{2,}', sp_name))
            if ct_tokens and sp_tokens:
                overlap = ct_tokens & sp_tokens
                token_score = len(overlap) / max(len(ct_tokens), len(sp_tokens))
                score += token_score * 30
                if overlap:
                    top = list(overlap)[:3]
                    notes.append(f'名称匹配:{",".join(top)}')

        if sp_name and len(sp_name) >= 2 and sp_name in ct_full:
            score += 20

        if score > best_score:
            best_score = score
            best_candidates = available
            best_note = '; '.join(notes[:3]) if notes else ''

    if best_score >= 35 and best_candidates:
        return (best_candidates, f'[模糊匹配] {best_note}')
    return ([], '')


# ═══════════════════════════════════════════
#  核心比对逻辑
# ═══════════════════════════════════════════

def _detect_contract_dims(conn, contract_id: int, version_id: int) -> dict:
    """判断主合同有哪些比对维度（按主合同实际列，不固化）。
    优先读 versions.column_mapping 的 contract_semantics，回退到字段值动态判断。"""
    dims = {'specs': False, 'qty': False, 'unit': False, 'price': False, 'amount': False, 'model': False}
    row = conn.execute("SELECT column_mapping FROM versions WHERE id=?", (version_id,)).fetchone()
    if row and row['column_mapping']:
        try:
            cs = json.loads(row['column_mapping']).get('contract_semantics', {})
            if cs:
                dims['specs'] = 'specs_full' in cs
                dims['qty'] = 'qty' in cs
                dims['unit'] = 'unit' in cs
                dims['price'] = 'unit_price' in cs
                dims['amount'] = 'amount' in cs
                dims['model'] = 'device_model' in cs
                return dims
        except Exception:
            pass
    # 回退：动态判断（主合同 items 里对应字段是否有值）
    rows = conn.execute(
        "SELECT specs_full, specs_cpu, specs_memory, specs_disk, contract_qty, "
        "contract_unit, contract_unit_price, contract_amount, device_model "
        "FROM contract_items WHERE contract_id=?", (contract_id,)
    ).fetchall()
    for r in rows:
        if not dims['specs'] and (r['specs_full'] or r['specs_cpu'] or r['specs_memory'] or r['specs_disk']):
            dims['specs'] = True
        if not dims['qty'] and (r['contract_qty'] or 0) > 0:
            dims['qty'] = True
        if not dims['unit'] and r['contract_unit']:
            dims['unit'] = True
        if not dims['price'] and (r['contract_unit_price'] or 0) > 0:
            dims['price'] = True
        if not dims['amount'] and (r['contract_amount'] or 0) > 0:
            dims['amount'] = True
        if not dims['model'] and r['device_model']:
            dims['model'] = True
    return dims


def run_comparison(contract_id: int, version_id: int, check_amount: bool = False):
    conn = get_db()
    c = conn.cursor()

    c.execute("DELETE FROM comparison_results WHERE version_id = ?", (version_id,))

    contracts = [dict(r) for r in c.execute(
        "SELECT * FROM contract_items WHERE contract_id = ?", (contract_id,)
    ).fetchall()]
    suppliers = [dict(r) for r in c.execute(
        "SELECT * FROM supplier_items WHERE contract_id = ? AND version_id = ?",
        (contract_id, version_id)
    ).fetchall()]

    # 主合同比对维度（按主合同实际列动态决定，不固化）
    dims = _detect_contract_dims(conn, contract_id, version_id)

    # 加载列对齐映射：凡是有对应关系的列都要参与比对（语义字段之外的列也逐列比）
    col_mapping = {}
    semantic_compared_cols = set()  # 已有专门比对逻辑的主合同列名
    sem = {}  # 语义字段 → 合同列名（匹配说明里用合同原始列名，不改成「设备名称」等通用名）
    _cm_row = c.execute("SELECT column_mapping FROM versions WHERE id=?", (version_id,)).fetchone()
    if _cm_row and _cm_row['column_mapping']:
        try:
            _cm = json.loads(_cm_row['column_mapping'])
            col_mapping = _cm.get('mapping', {}) or {}
            _cs = _cm.get('contract_semantics', {}) or {}
            sem = dict(_cs)
            for _f in ('device_name', 'device_model', 'specs_full', 'qty', 'unit', 'unit_price', 'amount'):
                if _cs.get(_f):
                    semantic_compared_cols.add(_cs[_f])
        except Exception:
            pass

    # 匹配说明里的列标签 = 合同原始列名（无对应时回退到通用名）
    lbl_name = sem.get('device_name') or '设备名称'
    lbl_model = sem.get('device_model') or '设备型号'
    lbl_specs = sem.get('specs_full') or '参数'
    lbl_qty = sem.get('qty') or '数量'
    lbl_unit = sem.get('unit') or '单位'
    lbl_price = sem.get('unit_price') or '单价'
    lbl_amount = sem.get('amount') or '金额'

    supplier_index = {}
    for s in suppliers:
        key = _match_key(s['device_name'], s['device_model'])
        if key not in supplier_index:
            supplier_index[key] = []
        supplier_index[key].append(s)

    matched_supplier_ids = set()
    results = []

    def _pick_best(candidates, ct_qty):
        if not candidates:
            return None
        for sp in candidates:
            if sp['id'] in matched_supplier_ids:
                continue
            sp_qty = sp['quote_qty'] or 0
            if ct_qty > 0 and sp_qty > 0 and ct_qty == sp_qty:
                return sp
        for sp in candidates:
            if sp['id'] in matched_supplier_ids:
                continue
            sp_qty = sp['quote_qty'] or 0
            if ct_qty == 0 and sp_qty == 0:
                return sp
        for sp in candidates:
            if sp['id'] not in matched_supplier_ids:
                return sp
        return None

    # ===== 正向比对: 合同 → 供应商 =====
    for ct in contracts:
        key = _match_key(ct['device_name'], ct['device_model'])
        candidates = supplier_index.get(key, [])
        sp = _pick_best(candidates, ct['contract_qty'] or 0)
        fuzzy_note = ''

        if sp is None:
            fuzzy_candidates, fuzzy_note = _fuzzy_find_supplier(
                ct['device_name'], ct['device_model'],
                supplier_index, matched_supplier_ids
            )
            if fuzzy_candidates:
                sp = _pick_best(fuzzy_candidates, ct['contract_qty'] or 0)

        if sp is None:
            results.append({
                'contract_item_id': ct['id'],
                'supplier_item_id': None,
                'match_status': '待采购',
                'anomaly_types': json.dumps(['待采购漏报']),
                'anomaly_detail': '合同要求该设备，供应商未报价',
                'qty_diff': '',
                'param_diff': '',
                'match_note': '',
                'version_id': version_id
            })
            continue

        matched_supplier_ids.add(sp['id'])

        anomaly_types = []
        anomaly_details = []

        # 1) 数量比对（主合同有数量列才比）
        qty_diff = ''
        ct_qty = ct['contract_qty'] or 0
        sp_qty = sp['quote_qty'] or 0
        if dims['qty'] and ct_qty > 0 and sp_qty > 0 and ct_qty != sp_qty:
            if sp_qty < ct_qty:
                anomaly_types.append('数量少报')
            else:
                anomaly_types.append('数量多报')
            anomaly_details.append(f'数量不一致: 合同{ct_qty}台 → 报价{sp_qty}台')
            qty_diff = f'{ct_qty},{sp_qty},{sp_qty - ct_qty}'

        # 2) 参数比对（v2.0 三层引擎）— 主合同有参数列才比
        param_diff = ''
        match_note = ''
        params_compared = False  # 双方都有参数文本，参数真正参与了比对
        if dims['specs']:
            ct_specs = {
                'cpu': ct['specs_cpu'] or '',
                'memory': ct['specs_memory'] or '',
                'disk': ct['specs_disk'] or ''
            }
            sp_specs = {
                'cpu': sp['specs_cpu'] or '',
                'memory': sp['specs_memory'] or '',
                'disk': sp['specs_disk'] or ''
            }
            if not any(ct_specs.values()) and ct.get('specs_full'):
                ct_specs = extract_specs(ct['specs_full'])
            if not any(sp_specs.values()) and sp.get('specs_full'):
                sp_specs = extract_specs(sp['specs_full'])

            params_ok, param_text, match_note = compare_params(
                ct_specs, sp_specs,
                ct.get('specs_full', ''), sp.get('specs_full', '')
            )
            if not params_ok:
                anomaly_types.append('参数异常')
                anomaly_details.append(param_text)
                param_diff = param_text
            else:
                # 双方都有参数内容才算真正比对了参数（一方为空则跳过）
                _ct_full = (ct.get('specs_full') or '').strip()
                _sp_full = (sp.get('specs_full') or '').strip()
                if _ct_full and _sp_full:
                    params_compared = True

        # 3) 金额比对（主合同有单价/金额列才比）
        if dims['amount'] or dims['price']:
            ct_price = ct['contract_unit_price'] or 0
            sp_price = sp['quote_unit_price'] or 0
            ct_amt = ct['contract_amount'] or 0
            sp_amt = sp['quote_amount'] or 0
            if ct_price != sp_price or ct_amt != sp_amt:
                anomaly_types.append('金额不一致')
                anomaly_details.append(
                    f'金额不一致: 合同单价{ct_price}/总额{ct_amt} → 报价单价{sp_price}/总额{sp_amt}'
                )

        # 4) 通用列比对：凡是有对应关系（mapping target 非空）且非语义字段的列，逐列比对
        generic_ok = []    # [(列名, 合同值, 供应商值)] 一致
        generic_bad = []   # [(列名, 合同值, 供应商值)] 不一致
        ct_raw = {}
        sp_raw = {}
        try:
            ct_raw = json.loads(ct.get('raw_columns') or '{}') or {}
        except Exception:
            pass
        try:
            sp_raw = json.loads(sp.get('raw_columns') or '{}') or {}
        except Exception:
            pass
        for _ct_col, _sp_col in (col_mapping or {}).items():
            if not _sp_col or _ct_col in semantic_compared_cols:
                continue  # 无对应关系，或已有专门比对逻辑
            _cv = ct_raw.get(_ct_col)
            _sv = sp_raw.get(_sp_col)
            _cv_s = str(_cv).strip() if _cv is not None else ''
            _sv_s = str(_sv).strip() if _sv is not None else ''
            if _cv_s == '' and _sv_s == '':
                continue  # 双方都空，跳过
            if _cv_s == _sv_s:
                generic_ok.append((_ct_col, _cv_s, _sv_s))
            else:
                generic_bad.append((_ct_col, _cv_s, _sv_s))
                anomaly_types.append(f'{_ct_col}不一致')
                anomaly_details.append(f'{_ct_col}不一致: 合同「{_cv_s}」→ 报价「{_sv_s}」')

        # ── 按列对齐顺序生成匹配说明（跟随主合同列实际顺序，不硬编码）──
        def _fmt_num(v):
            try:
                fv = float(v or 0)
                return str(int(fv)) if fv == int(fv) else str(round(fv, 2))
            except (ValueError, TypeError):
                return str(v)

        def _emit_align_lines():
            lines = []
            seq = 0
            ct_name = ct.get('device_name', '') or ''
            sp_name = sp.get('device_name', '') or ''
            ct_model = ct.get('device_model', '') or ''
            sp_model = sp.get('device_model', '') or ''
            ct_qty = ct.get('contract_qty') or 0
            sp_qty = sp.get('quote_qty') or 0
            ct_unit = (ct.get('contract_unit') or '').strip()
            sp_unit = (sp.get('quote_unit') or '').strip()
            ct_price = ct.get('contract_unit_price') or 0
            sp_price = sp.get('quote_unit_price') or 0
            ct_amt = ct.get('contract_amount') or 0
            sp_amt = sp.get('quote_amount') or 0
            # 反向映射：合同列名 → 语义字段
            col_to_field = {}
            for _f, _cn in sem.items():
                col_to_field[_cn] = _f
            # 通用列结果索引
            ok_map = {c: (cv, sv) for c, cv, sv in generic_ok}
            bad_map = {c: (cv, sv) for c, cv, sv in generic_bad}

            for ct_col, sp_col in col_mapping.items():
                if not sp_col:
                    continue  # 无对应关系，跳过
                field = col_to_field.get(ct_col)
                if field == 'device_name':
                    seq += 1
                    nk_ct = _match_key(ct_name, '')[1]
                    nk_sp = _match_key(sp_name, '')[1]
                    if nk_ct == nk_sp and nk_ct:
                        lines.append(f'{seq}. {ct_col}：合同「{ct_name}」vs 供应商「{sp_name}」→ 精确匹配')
                    else:
                        lines.append(f'{seq}. {ct_col}：合同「{ct_name}」vs 供应商「{sp_name}」→ 模糊匹配')
                elif field == 'device_model':
                    seq += 1
                    mk_ct = _match_key('', ct_model)[0]
                    mk_sp = _match_key('', sp_model)[0]
                    if mk_ct == mk_sp and mk_ct:
                        lines.append(f'{seq}. {ct_col}：合同「{ct_model}」vs 供应商「{sp_model}」→ 精确匹配')
                    else:
                        lines.append(f'{seq}. {ct_col}：合同「{ct_model}」vs 供应商「{sp_model}」→ 模糊匹配')
                elif field == 'specs_full':
                    if params_compared:
                        if match_note:
                            pd = match_note.replace('判断符合: ', '')
                            for d in pd.split('; '):
                                d = d.strip()
                                if d:
                                    seq += 1
                                    lines.append(f'{seq}. {ct_col}：{d}')
                        else:
                            seq += 1
                            lines.append(f'{seq}. {ct_col}：一致')
                    elif param_diff:
                        seq += 1
                        lines.append(f'{seq}. {ct_col}：{param_diff}')
                elif field == 'qty':
                    if dims['qty']:
                        seq += 1
                        if ct_qty == sp_qty and ct_qty > 0:
                            lines.append(f'{seq}. {ct_col}：合同{_fmt_num(ct_qty)}{ct_unit} vs 供应商{_fmt_num(sp_qty)}{sp_unit} → 一致')
                        elif ct_qty == 0 and sp_qty == 0:
                            lines.append(f'{seq}. {ct_col}：双方均未填写')
                        elif ct_qty == sp_qty:
                            lines.append(f'{seq}. {ct_col}：一致')
                        else:
                            lines.append(f'{seq}. {ct_col}：合同{_fmt_num(ct_qty)}{ct_unit} vs 供应商{_fmt_num(sp_qty)}{sp_unit} → 不一致')
                elif field == 'unit':
                    if dims['unit'] and (ct_unit or sp_unit):
                        seq += 1
                        if ct_unit == sp_unit:
                            lines.append(f'{seq}. {ct_col}：合同「{ct_unit}」vs 供应商「{sp_unit}」→ 一致')
                        elif ct_unit and sp_unit:
                            lines.append(f'{seq}. {ct_col}：合同「{ct_unit}」vs 供应商「{sp_unit}」→ 不一致')
                        elif ct_unit:
                            lines.append(f'{seq}. {ct_col}：合同「{ct_unit}」，供应商未填写')
                        else:
                            lines.append(f'{seq}. {ct_col}：供应商「{sp_unit}」，合同未填写')
                elif field == 'unit_price':
                    if dims['price']:
                        seq += 1
                        if ct_price == sp_price:
                            lines.append(f'{seq}. {ct_col}：合同{_fmt_num(ct_price)} vs 供应商{_fmt_num(sp_price)} → 一致')
                        else:
                            lines.append(f'{seq}. {ct_col}不一致: 合同{_fmt_num(ct_price)} → 报价{_fmt_num(sp_price)}')
                elif field == 'amount':
                    if dims['amount']:
                        seq += 1
                        if ct_amt == sp_amt and ct_price == sp_price:
                            lines.append(f'{seq}. {ct_col}：一致')
                        else:
                            lines.append(f'{seq}. {ct_col}不一致: 合同单价{_fmt_num(ct_price)}/总额{_fmt_num(ct_amt)} → 报价单价{_fmt_num(sp_price)}/总额{_fmt_num(sp_amt)}')
                else:
                    # 通用列（有对应关系但非语义字段）
                    if ct_col in ok_map:
                        seq += 1
                        cv, sv = ok_map[ct_col]
                        lines.append(f'{seq}. {ct_col}：合同「{cv}」vs 供应商「{sv}」→ 一致')
                    elif ct_col in bad_map:
                        seq += 1
                        cv, sv = bad_map[ct_col]
                        lines.append(f'{seq}. {ct_col}不一致: 合同「{cv}」→ 报价「{sv}」')
            return lines

        if anomaly_types:
            # 异常项也按列对齐顺序生成匹配说明
            anomaly_note = '\n'.join(_emit_align_lines())
            results.append({
                'contract_item_id': ct['id'],
                'supplier_item_id': sp['id'],
                'match_status': '匹配异常',
                'anomaly_types': json.dumps(anomaly_types),
                'anomaly_detail': '\n'.join(anomaly_details),
                'qty_diff': qty_diff,
                'param_diff': param_diff,
                'match_note': anomaly_note,
                'version_id': version_id
            })
        else:
            # 按列对齐顺序生成匹配说明
            final_note = '\n'.join(_emit_align_lines())
            anomaly_detail = fuzzy_note if fuzzy_note else ''
            # 模糊匹配或参数判断符合 → 判定为「判断符合」需人工核实
            if fuzzy_note or match_note:
                final_status = '判断符合'
                if fuzzy_note:
                    anomaly_detail = fuzzy_note
            else:
                final_status = '匹配成功'
            results.append({
                'contract_item_id': ct['id'],
                'supplier_item_id': sp['id'],
                'match_status': final_status,
                'anomaly_types': '[]',
                'anomaly_detail': anomaly_detail,
                'qty_diff': '',
                'param_diff': '',
                'match_note': final_note,
                'version_id': version_id
            })

    # ===== 反向比对: 供应商 → 合同 =====
    for sp in suppliers:
        if sp['id'] in matched_supplier_ids:
            continue
        key = _match_key(sp['device_name'], sp['device_model'])
        found = any(
            _match_key(ct['device_name'], ct['device_model']) == key
            for ct in contracts
        )
        if not found:
            results.append({
                'contract_item_id': None,
                'supplier_item_id': sp['id'],
                'match_status': '供应商增项',
                'anomaly_types': json.dumps(['供应商增项']),
                'anomaly_detail': '该设备不在合同采购范围内，属于私自新增条目',
                'qty_diff': '',
                'param_diff': '',
                'match_note': '',
                'version_id': version_id
            })

    # 写入结果
    for r in results:
        c.execute("""
            INSERT INTO comparison_results
            (contract_id, contract_item_id, supplier_item_id, match_status, anomaly_types,
             anomaly_detail, qty_diff, param_diff, match_note, version_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            contract_id, r['contract_item_id'], r['supplier_item_id'], r['match_status'],
            r['anomaly_types'], r['anomaly_detail'], r['qty_diff'],
            r['param_diff'], r.get('match_note', ''), r['version_id']
        ))

    matched_count = sum(1 for r in results if r['match_status'] == '匹配成功')
    judged_count = sum(1 for r in results if r['match_status'] == '判断符合')
    anomaly_count = sum(1 for r in results if r['match_status'] == '匹配异常')
    pending_count = sum(1 for r in results if r['match_status'] == '待采购')
    extra_count = sum(1 for r in results if r['match_status'] == '供应商增项')

    # 进度 = (精确匹配 + 判断符合) / 合同总条目
    progress = round(((matched_count + judged_count) / len(contracts) * 100), 2) if contracts else 0

    c.execute("""
        UPDATE versions SET
            total_items = ?, matched_count = ?, judged_count = ?,
            anomaly_count = ?, pending_count = ?, extra_count = ?, progress = ?
        WHERE id = ?
    """, (len(suppliers), matched_count, judged_count, anomaly_count, pending_count, extra_count, progress, version_id))

    conn.commit()
    conn.close()

    return {
        'success': True,
        'version_id': version_id,
        'total_items': len(suppliers),
        'matched_count': matched_count,
        'judged_count': judged_count,
        'anomaly_count': anomaly_count,
        'pending_count': pending_count,
        'extra_count': extra_count,
        'progress': progress,
        'total_results': len(results)
    }


# ═══════════════════════════════════════════
#  整单状态判断
# ═══════════════════════════════════════════

def get_overall_status(version_id: int) -> str:
    """判断整单状态"""
    conn = get_db()
    c = conn.cursor()
    v = c.execute("SELECT * FROM versions WHERE id = ?", (version_id,)).fetchone()
    if not v:
        conn.close()
        return '未比对'
    v = dict(v)
    if v['progress'] >= 100:
        conn.close()
        return '整单闭环完成'
    if v['anomaly_count'] > 0 or v['pending_count'] > 0 or v['extra_count'] > 0:
        conn.close()
        return '比对完成（存在异常）'
    if v['total_items'] == 0:
        conn.close()
        return '未比对'
    conn.close()
    return '比对完成'
