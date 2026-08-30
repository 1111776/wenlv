"""生成《文旅多Agent行程规划系统》完整答辩/交付 PPT。"""

from __future__ import annotations

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# 配色
PRIMARY = RGBColor(0x16, 0x77, 0xFF)  # 蓝
DARK = RGBColor(0x1F, 0x2D, 0x3D)  # 深灰
GREEN = RGBColor(0x52, 0xC4, 0x1A)
RED = RGBColor(0xF5, 0x22, 0x2D)
ORANGE = RGBColor(0xFA, 0xAD, 0x14)
GRAY = RGBColor(0x8C, 0x8C, 0x8C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xF0, 0xF5, 0xFF)


def add_bg(slide, color=WHITE):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def add_title(slide, text, left=0.5, top=0.3, width=9, size=30, color=DARK, bold=True):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(0.8))
    tf = box.text_frame
    tf.text = text
    p = tf.paragraphs[0]
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    return box


def add_text(slide, text, left=0.5, top=1.2, width=9, height=5.5, size=14, color=DARK):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(size)
        p.font.color.rgb = color
        if line.startswith("## "):
            p.font.size = Pt(size + 4)
            p.font.bold = True
            p.font.color.rgb = PRIMARY
        elif line.startswith("### "):
            p.font.size = Pt(size + 2)
            p.font.bold = True
        elif line.startswith("  - ") or line.startswith("- "):
            p.level = 0
    return box


def add_bullets(slide, items, left=0.6, top=1.3, width=8.8, height=5.4, size=14, gap=8):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        # item 可能是 (标题, 内容) 或纯字符串
        if isinstance(item, tuple):
            title, content = item
            p.text = f"■ {title}"
            p.font.bold = True
            p.font.size = Pt(size)
            p.font.color.rgb = PRIMARY
            p.space_after = Pt(2)
            sub = tf.add_paragraph()
            sub.text = f"    {content}"
            sub.font.size = Pt(size - 2)
            sub.font.color.rgb = DARK
            sub.space_after = Pt(gap)
        else:
            p.text = f"• {item}"
            p.font.size = Pt(size)
            p.font.color.rgb = DARK
            p.space_after = Pt(gap)
    return box


def cover(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白布局
    add_bg(slide, PRIMARY)
    add_title(slide, "文旅多 Agent 行程规划系统", 0.8, 2.0, 9, 44, WHITE)
    add_text(slide, "基于 8 个 AI Agent 协作的文旅资源调研与个性化行程规划\n"
                    "—— 真实数据 · 断点续传 · 图记忆 · 运行态强干预", 0.8, 3.2, 9, 1.5, 20, WHITE)
    add_text(slide, "版本 v2.0  ·  2026-08-28", 0.8, 5.4, 9, 0.6, 14, RGBColor(0xD0, 0xE4, 0xFF))


def section(prs, num, title):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, LIGHT)
    add_title(slide, f"{num}  {title}", 0.8, 2.5, 9, 36, PRIMARY)


prs = Presentation()
prs.slide_width = Inches(10)
prs.slide_height = Inches(7.5)

# ============ 封面 ============
cover(prs)

# ============ 目录 ============
section(prs, "", "目录")
add_bullets(prs.slides[1], [
    "一、项目背景", "二、项目痛点", "三、项目目标与需求", "四、技术难点",
    "五、项目亮点", "六、系统架构", "七、8 个 Agent 详解", "八、核心技术实现",
    "九、数据源与数据模型", "十、API 与前端", "十一、部署与启动", "十二、完整流程演示",
    "十三、测试与验收", "十四、设计决策", "十五、总结",
], size=16, gap=10)

# ============ 一、项目背景 ============
section(prs, "一", "项目背景")
add_bullets(prs.slides[2], [
    ("业务背景", "传统文旅行业靠人工查资料 + Excel 排行程，一个行程从需求到方案需几小时到一整天"),
    ("三大业务痛点", "① 数据静态过时 ② 无风险拦截（差评景点/超预算/夜行） ③ 无容灾（崩溃即丢失）"),
    ("技术背景", "人工智能课程多 Agent 协同工单，分两期：多Agent-2（文旅规划）+ 工单7（图记忆+强干预）"),
    ("工期约束", "1 人独立完成，v1.0 共 7 人日 + 工单7 增量 3 人日，需做大量「最小增量、最大复用」取舍"),
], size=14)

# ============ 二、项目痛点 ============
section(prs, "二", "项目痛点")
add_bullets(prs.slides[3], [
    ("痛点1：语义遗忘", "用户第1次说「海鲜过敏」，两周后系统忘了，又推荐海鲜餐厅 —— 缺长期记忆"),
    ("痛点2：状态不刷新", "运行中某景点台风停运，系统不知道，仍按旧信息编排 —— 缺运行态纠偏"),
    ("痛点3：长任务无容灾", "8个Agent跑几分钟，中途崩溃全部丢失 —— 缺断点续传"),
    ("痛点4：无风险拦截", "人工排行程可能推荐差评景点/超预算20%/夜行路段 —— 缺HITL门控"),
    ("痛点5：假数据假智能", "早期用种子数据+Mock LLM，景点路线推理全是假的 —— 缺真实数据"),
], size=14)

# ============ 三、项目目标与需求 ============
section(prs, "三", "项目目标与需求")
add_bullets(prs.slides[4], [
    ("一句话目标", "把「人工排行程」改造成「AI 自动调研工厂」：输入一句需求，8个Agent自动完成调研、编排、预算、报告"),
    ("8个Agent协同", "偏好解析→任务拆解→网页调研→舆情评估→日程编排→预算计算→人工审核→报告生成"),
    ("断点续传", "planning-with-files，全程持久化 travel_plan.md，崩溃5秒内恢复"),
    ("HITL人机协作", "超预算20%/高危夜行/严重舆情 → 挂起人工审核"),
    ("图记忆(工单7)", "跨行程沉淀知识图谱，修复语义遗忘"),
    ("运行态强干预(工单7)", "主管带验签修改运行中状态，修复状态不刷新"),
    ("性能红线", "QPS≥200 / P95<300ms / 错误率<0.1% / 检索<150ms / 干预成功率100%"),
], size=14)

# ============ 四、技术难点 ============
section(prs, "四", "技术难点（7 个）")
add_bullets(prs.slides[5], [
    ("断点续传正确性", "原子写入(temp+fsync+replace) + checksum + 快照回退 + 幂等恢复"),
    ("异步队列崩溃接管", "Redis Streams consumer group + PEL + XAUTOCLAIM 自认领"),
    ("审核并发防重", "Lua CAS 抢占 + DB 条件更新兜底 + 会话租约锁"),
    ("写入-入队竞态", "先 commit 再入队，否则 Worker 抢跑报「行程不存在」（容器化才暴露）"),
    ("图记忆抽取检索", "真实LLM抽取任意过敏原 + 向量/图双路检索 + 缓存"),
    ("强干预安全原子性", "HMAC验签 + nonce防重放 + SETNX锁 + 三写一事务"),
    ("真实数据接入的坑", "高德key没拼参数/百炼json_object需含json字/nigx缓存旧IP致502"),
], size=13)

# ============ 五、项目亮点 ============
section(prs, "五", "项目亮点")
add_bullets(prs.slides[6], [
    ("全链路真实数据", "高德(景点/路线/天气/营业时间/评分/图片) + 百炼LLM(8Agent+记忆) + 虚拟房价"),
    ("完整行程规划", "每日三餐餐饮推荐 + 景点图片(可放大) + 营业时间 + 出发/返程日期自动算天数"),
    ("规划文件即大脑", "travel_plan.md 既是可解释看板，又是断点载体（Manus-style）"),
    ("性能大幅超标", "QPS 1109(5.5x)、P95 35ms(快8x)、检索0.3ms(快500x)、干预100%"),
    ("工程细节扎实", "原子写+checksum+快照、Lua CAS+DB兜底、防抖+幂等+超时+心跳"),
    ("容器化暴露真bug", "写入-入队竞态、nginx 502 均被真实部署发现并根治"),
    ("工单7全量落地", "图记忆+强干预，数据模型/引擎/API/前端/测试/文档完整闭环"),
    ("精致前端", "真实风景壁纸 + 状态看板友好化(进度条+步骤卡片)"),
], size=13)

# ============ 六、系统架构 ============
section(prs, "六", "系统架构（6 层）")
add_bullets(prs.slides[7], [
    ("前端层", "React 18 + TS + AntD，6页面，WebSocket实时推送"),
    ("API网关层", "FastAPI + JWT/RBAC + 统一错误码 + HMAC验签（不执行长任务）"),
    ("业务服务层", "高德/原子写/锁/队列/恢复/安全 等可复用逻辑"),
    ("Agent编排层", "LangGraph StateGraph + 8节点DAG + 条件边 + 记忆/干预"),
    ("数据层", "PostgreSQL(10表权威) + Redis(Streams/锁/缓存) + 文件(断点恢复源)"),
    ("外部数据源", "高德地图(地理编码/POI/路径/天气/营业时间/图片) + 阿里云百炼LLM(qwen3.7-flash)"),
], size=14)

# ============ 七、8个Agent详解 ============
section(prs, "七", "8 个 Agent 详解")
add_bullets(prs.slides[8], [
    ("① Intake 偏好解析", "解析需求→结构化偏好(目的地/天数/预算/过敏)，真实LLM"),
    ("② Planner 任务拆解", "CoT拆解≥8条调研任务(景点/酒店/餐饮/交通/购物)"),
    ("③ Web Research 调研", "高德POI搜索真实景点/酒店，ReAct+安全过滤+断点"),
    ("④ Sentiment 舆情评估", "对真实POI做风险识别，规则引擎打分"),
    ("⑤ Itinerary 日程编排", "按天编排+高德路径规划真实路线，读取干预补丁"),
    ("⑥ Budget 预算计算", "分项汇总+虚拟房价，判断超预算"),
    ("⑦ Human Review 审核", "风险场景挂起路由人工审批，不调LLM"),
    ("⑧ Report 报告生成", "汇总生成报告(天气+路线+行程+酒店+预算)"),
], size=13)

# ============ 八、核心技术实现 ============
section(prs, "八", "核心技术实现")
add_bullets(prs.slides[9], [
    ("断点续传", "temp→fsync→os.replace→目录fsync，任何时刻崩溃文件要么旧版要么新版，绝无半份"),
    ("五状态机", "planning→running→suspended→completed + recovering/failed/cancelled"),
    ("HITL门控", "超预算20%/夜行/舆情→挂起→主管抢占(Lua CAS)→通过续跑/驳回终止"),
    ("图记忆", "LLM抽取三元组→upsert→向量+图双路检索→Redis缓存(0.3ms)"),
    ("强干预", "HMAC验签→nonce防重放→SETNX锁→三写一事务→节点入口应用补丁"),
    ("安全", "JWT+RBAC + 注入检测 + 内容过滤 + 工具白名单"),
], size=14)

# ============ 九、数据源与数据模型 ============
section(prs, "九", "数据源与数据模型")
add_bullets(prs.slides[10], [
    ("高德地图(1 key 6能力)", "地理编码/POI搜索/路径规划/天气/营业时间/景点图片，全真实"),
    ("阿里云百炼 LLM", "qwen3.7-flash，8 Agent 推理 + 记忆抽取"),
    ("虚拟房价", "真实酒店POI名 + 城市等级分档估算价"),
    ("业务表(6张)", "users/travel_plans/agent_tasks/review_records/budget_records/audit_logs"),
    ("图记忆表(4张)", "graph_nodes/graph_edges/memory_events/interventions"),
    ("密钥安全", ".env 注入，.gitignore 忽略，不入 git"),
], size=14)

# ============ 十、API与前端 ============
section(prs, "十", "API 与前端")
add_bullets(prs.slides[11], [
    ("API(5组20+接口)", "认证/行程/审核/记忆(工单7)/运维"),
    ("记忆接口", "intervene(干预)/rollback(回滚)/graph(子图)/search(检索)/interventions(历史)"),
    ("前端6页面", "登录注册/工作台/行程列表/行程详情/审核台/记忆图谱"),
    ("行程详情亮点", "景点图片(可放大) + 三餐餐饮 + 营业时间 + 日期 + 状态看板友好化"),
    ("审核台亮点", "表格内直出按钮(抢占/通过/驳回)，无隐藏抽屉"),
    ("记忆图谱亮点", "实体卡片 + 检索 + 干预弹窗 + 干预历史"),
    ("视觉", "登录页真实风景壁纸 + 内容区图片背景 + 卡片圆角阴影"),
], size=13)

# ============ 十一、部署与启动 ============
section(prs, "十一", "部署与启动")
add_bullets(prs.slides[12], [
    ("一键启动", "双击 一键启动.bat → 自动构建+启动+打开浏览器；一键关闭.bat 停止"),
    ("7个Docker服务", "api/worker/frontend/postgres/redis/prometheus/grafana"),
    ("访问地址", "前端8080 / API文档8001 / Grafana 3002"),
    ("演示账号", "advisor_demo(顾问) / supervisor_demo(主管)，密码wenlv123"),
    ("端口避让", "因本机常见端口占用，统一改8080/8001/6380/5433/9091/3002"),
    ("nginx根治", "Docker DNS动态解析，api重建不502"),
], size=14)

# ============ 十二、完整流程演示 ============
section(prs, "十二", "完整流程演示（5 场景）")
add_bullets(prs.slides[13], [
    ("场景A 正常生成", "提交「3天杭州游」→8Agent执行→报告含天气+路线+行程+酒店+预算"),
    ("场景B 崩溃恢复", "跑到第6页kill -9→重启→从第7页续跑，前6页不重复"),
    ("场景C 注入拦截", "第7页含「忽略之前指令」→拦截→标记blocked→写审计日志"),
    ("场景D 人工审核", "超预算/夜行/舆情→挂起→主管抢占→通过→续跑出报告"),
    ("场景E 图记忆+干预", "行程1说「海鲜过敏」→行程2自动避开 + 主管干预「台风停运」→自动剔除"),
], size=14)

# ============ 十三、测试与验收 ============
section(prs, "十三", "测试与验收")
add_bullets(prs.slides[14], [
    ("压测结果", "QPS 1109(≥200✅5.5x) / P95 35.4ms(<300✅快8x) / 错误率0%(<0.1%✅)"),
    ("工单7红线", "检索P95 0.3ms(<150✅快500x) / 干预成功率100%(=100%✅)"),
    ("单元测试", "8个用例全绿(test_memory_intervention.py)"),
    ("联调脚本", "e2e_check / recovery_test / simulate_conversation(15轮) / concurrent(50并发)"),
    ("竞态审计", "50并发干预零丢失更新，版本链完整"),
], size=14)

# ============ 十四、设计决策 ============
section(prs, "十四", "设计决策（关键取舍）")
add_bullets(prs.slides[15], [
    ("编排框架", "LangGraph（工单首选，7人日不允许自研图引擎）"),
    ("队列", "Redis Streams（PEL原生断点，比Celery轻）"),
    ("LLM", "抽象Provider，Mock→真实切换（压测不烧钱，演示切真模型）"),
    ("图存储", "PostgreSQL应用层向量（不引Neo4j/pgvector，单机原则）"),
    ("记忆引擎", "自研轻量Mem0风格（3人日不允许消化外部框架黑盒）"),
    ("干预", "HMAC+nonce+三写事务（工单红线：安全验签）"),
], size=14)

# ============ 十五、总结 ============
section(prs, "十五", "总结")
add_bullets(prs.slides[16], [
    ("完成度", "原始需求(多Agent-2) + 工单7(图记忆+强干预) 全部落地，验收级完整"),
    ("数据真实性", "全链路真实数据（高德+百炼），无假数据假智能"),
    ("性能", "四项指标全部达标且大幅超标"),
    ("工程价值", "从零到可交付：架构→开发→容器化→压测→文档→git版本管理"),
    ("核心能力", "断点续传 + HITL + 图记忆 + 强干预 + 安全，五维完整"),
], size=15)

# 保存
import os
out = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "项目讲解.pptx")
prs.save(out)
print(f"PPT 已生成：{out}")
print(f"共 {len(prs.slides)} 页")
