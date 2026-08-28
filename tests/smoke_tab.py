#!/usr/bin/env python3
"""Tab/DOM 结构 & 行为冒烟脚本（9006 服务端远程 HTTP）"""
import re, urllib.request, sys

BASE = "http://127.0.0.1:9006"
html = urllib.request.urlopen(BASE + "/procurement").read().decode("utf-8")
js   = urllib.request.urlopen(BASE + "/procurement.app.js").read().decode("utf-8")

ok = True
def check(name, cond, detail=""):
    global ok
    mark = "[OK]" if cond else "[FAIL]"
    print(f"{mark} {name}{(' — ' + detail) if detail else ''}")
    if not cond: ok = False

panels = re.findall(r'<div\s+id="proc-tab-(\w+)"\s+class="proc-top-panel', html)
check("5 个 proc-top-panel 面板存在", set(panels) == {'tasks','ledger','supplier','contract','mailcc'}, f"实际={panels}")

tabs = re.findall(r'class="proc-top-tab[^"]*"\s+data-tab="(\w+)"', html) or re.findall(r'data-tab="(\w+)"\s+onclick="switchTopTab', html)
check("5 个 proc-top-tab 按钮存在", set(tabs) == {'tasks','ledger','supplier','contract','mailcc'}, f"实际={tabs}")

n = len(re.findall(r'id="detailTaskId"', html))
check("detailTaskId 不重复", n == 1, f"实际={n}")

for pid in ["page-proc-list","page-proc-new","page-proc-detail"]:
    m = len(re.findall(rf'id="{pid}"', html))
    check(f"子页 {pid} 唯一", m == 1, f"实际={m}")

for oid in ["detailTabBase","detailTabQuote","detailTabAction"]:
    m = len(re.findall(rf'id="{oid}"', html))
    check(f"旧 Tab 容器 {oid} 已移除", m == 0, f"实际={m}")

hits = len(re.findall(r"detailTab(Base|Quote|Action)\.style\.display", js))
check("JS 不直接操作旧 Tab DOM", hits == 0, f"实际={hits}")

modals = re.findall(r'<div\s+id="(\w+Modal)"\s+class="modal"', html)
check(f"Modal 数量>=5", len(modals) >= 5, f"实际={modals}")

a = "initProcUI()" in js
m = re.search(r"document\.addEventListener\(['\"]DOMContentLoaded['\"],\s*\(\)\s*=>\s*\{([\s\S]{0,400}?)\}\);", js)
direct = False
if m and "initProcUI" not in m.group(1) and "loadTaskList" in m.group(1):
    direct = True
check("启动单入口=initProcUI", a and not direct, f"有initProcUI={a}; DOMContentLoaded裸load={direct}")

seg = ""
if "/* 顶层 Tab 内容容器" in html:
    i = html.index("/* 顶层 Tab 内容容器")
    seg = html[i:i+400]
    # 去掉 /* */ 注释再查，避免注释里的 '!important' 误判
    no_comment = __import__('re').sub(r"/\*[\s\S]*?\*/", "", seg)
    bad = "!important" in no_comment
    check("proc-top-panel 不含 !important", not bad, f"CSS规则: {no_comment[:200].strip()}")

print()
print("ALL SMOKE PASS" if ok else "SMOKE FAIL")
sys.exit(0 if ok else 1)
