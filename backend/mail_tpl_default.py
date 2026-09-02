# -*- coding: utf-8 -*-
"""智能体邮件 A–G 模板的**系统默认内容**（只读常量）。

用途：
  「邮件模板」页面要展示「当前真正生效的模板」，而页面自定义库
  （procurement_mail_template）只保存被改过的字段——留空表示沿用默认。
  因此必须有一份默认内容，才能显示"实际会发出去是长什么样"。

来源：一次性从 neuops-agent-demo 的 skills/skill-proc-mail-inquiry.json 导出
（与 9007 侧 mail_tpl.load_templates() 的兜底同源，两侧保持一致）。

注意：本文件是**只读基线**，不要在此改措辞；要改请通过「邮件模板」页面，
改动落在 procurement_mail_template 表。
"""

DEFAULT_MAIL_TEMPLATES = {
    "A": {
        "name": "A-工程师发起询价",
        "subject": "【备件询价】{project_no} {project_name} — {brand} {pn} x {count}",
        "body": "您好，我是运维部工程师，现发起备件询价申请，请协助转达至采购邮箱。\n\n项目编号：{project_no}\n项目名称：{project_name}\n备件类型：{part_type}\n品牌：{brand}\nPN：{pn}\n规格：{spec}\n成色：{condition}\n数量：{count}\n收货地址：{address}\n紧急程度：{urgent}\n最晚发货时间：{latest_ship_time}\n\n本任务编号：{task_no}\n收到回复后将自动汇总并推送审批。\n\n（提示：字段顺序与写法请勿调整，智能体按「字段名：值」逐行解析；成色只能填 全新 / 原厂翻新 / 拆机二手）"
    },
    "B": {
        "name": "B-对外询价-不带收货地址",
        "subject": "【询价】{brand} {pn} x {count} — {urgent} 内回复 [{task_no}]",
        "body": "尊敬的 {supplier} 供应商：\n\n您好！我司正紧急采购以下备件，烦请在 {urgent} 内给予报价：\n\n- 备件类型：{part_type}\n- 品牌：{brand}\n- PN 料号：{pn}\n- 规格参数：{spec}\n- 成色要求：{condition}\n- 采购数量：{count}\n- 最晚发货：{latest_ship_time}\n- 询价截止：{deadline}\n\n请按以上要求回复含税单价与交货周期，谢谢！\n\n（注：收货信息将在确定供应商后于订货邮件中单独告知）\n\n- NeuOps 备件邮件询价系统\n任务编号：{task_no}"
    },
    "C": {
        "name": "C-供应商回复-系统自动归档",
        "subject": "Re: 【询价】{project_no} {brand} {pn} x {count}",
        "body": "（此模板用于展示供应商回复原文；系统自动识别发件人/报价/交货周期并入库。）\n\n供应商回复原文如下：\n{body_placeholder}"
    },
    "D": {
        "name": "D-内部汇总-系统提示最低价优选-抄送审批人",
        "subject": "【询价汇总】{project_no} {brand} {pn} — {suppliers_count}家报价-最低价优选 [{task_no}]",
        "body": "各位好，备件询价任务 {task_no} 已完成 {suppliers_count} 家供应商报价汇总：\n\n项目：{project_no} / {project_name}\n备件：{part_type} / {brand} / {pn} / {spec}\n成色：{condition} x {count}\n询价截止：{deadline}\n\n【报价列表】\n{suppliers}\n\n【系统提示】最低价优选：\n  最低报价：{lowest_quote}\n  报价供应商：{lowest_supplier}\n  系统建议直接与最低价供应商 {lowest_supplier} 确认订货（质量/交货周期确认无误后）。\n\n请审批人 {approver_emails} 确认批准，确认后将下达订货邮件并推进收货流程。\n\n- NeuOps 备件邮件询价系统"
    },
    "E": {
        "name": "E-下达订货-回复选中供应商-带收货地址联系人快递单号测试报告",
        "subject": "【订货确认】{project_no} {brand} {pn} x {count} — 请安排发货 [{task_no}]",
        "body": "尊敬的 {supplier}：\n\n您好！贵司关于 {project_no}（{project_name}）的报价 {quote} 已通过内部审批，现正式下达订货指令，请按以下要求安排发货：\n\n【订货明细】\n- 备件类型：{part_type}\n- 品牌 / PN：{brand} / {pn}\n- 规格：{spec}\n- 成色：{condition}\n- 数量：{count}\n\n【收货信息】\n- 收货人：{receiver_name}\n- 联系电话：{receiver_phone}\n- 收货地址：{address}\n\n【交付要求】\n- 最晚发货时间：{latest_ship_time}\n- 快递单号请在发货后 2 小时内邮件回复本会话\n- 随货请附出厂测试报告 / 成色证明（{condition_display}）\n\n【任务编号】{task_no}\n\n发货后烦请回复本会话，系统将自动登记到货状态。\n\n- NeuOps 备件邮件询价系统"
    },
    "F": {
        "name": "F-中止通知",
        "subject": "【询价中止通知】{project_no} {brand} {pn} — 任务已终止 [{task_no}]",
        "body": "各位好，备件询价任务 {task_no} 已中止，原因如下：\n\n项目：{project_no} / {project_name}\n备件：{part_type} / {brand} / {pn}\n中止原因：{stop_reason}\n\n所有正在进行的对外询价将自动终止，不再接收新报价。\n\n如需重新发起询价，请在会话中重新说明需求。\n\n- NeuOps 备件邮件询价系统"
    },
    "G": {
        "name": "G-采购结束结算通知（内部流完成→外部流供应商）",
        "subject": "【采购结束】{project_no} {brand} {pn} — 任务关闭 [{task_no}]",
        "body": "尊敬的 {supplier} 供应商：\n\n您好！关于 {project_no}（{project_name}）的备件采购（任务 {task_no}），我方已确认收货并完成更换。\n\n本次采购正式结束，进入结算流程。请贵司根据双方确认的订货单与我方后期结算，感谢配合。\n\n【订货摘要】\n- 备件：{part_type} / {brand} / {pn} x {count}\n- 成色：{condition}\n\n- NeuOps 备件邮件询价系统"
    }
}
