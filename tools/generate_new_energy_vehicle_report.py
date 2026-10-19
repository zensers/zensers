# -*- coding: utf-8 -*-
"""
新能源汽车行业深度研究报告生成脚本

使用德勤风格模板生成新能源汽车行业深度研究报告。
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def generate_toc_html(sections: List[Dict[str, Any]]) -> str:
    """生成目录 HTML"""
    toc_items = []
    for i, section in enumerate(sections, 1):
        title = section.get("title", f"第{i}章")
        toc_items.append(f'''
            <li class="toc-item">
                <span class="chapter-num">{i:02d}</span>
                <span class="chapter-title">{title}</span>
                <span class="chapter-page">{i + 2}</span>
            </li>
        ''')
    return "\n".join(toc_items)


def generate_content_html(sections: List[Dict[str, Any]]) -> str:
    """生成正文 HTML"""
    content_parts = []
    
    for i, section in enumerate(sections, 1):
        title = section.get("title", f"第{i}章")
        content = section.get("content", "")
        
        # 章节标题
        content_parts.append(f'<h1 class="chapter-title">{i:02d} {title}</h1>')
        
        # 章节内容（转换 Markdown 到 HTML）
        html_content = markdown_to_html(content)
        content_parts.append(f'<div class="section-content">{html_content}</div>')
    
    return "\n".join(content_parts)


def markdown_to_html(text: str) -> str:
    """简单的 Markdown 到 HTML 转换"""
    import re
    
    if not text:
        return ""
    
    lines = text.split('\n')
    html_lines = []
    in_table = False
    table_rows = []
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            if in_table:
                # 结束表格
                html_lines.append('<table>')
                for i, row in enumerate(table_rows):
                    if i == 0:
                        html_lines.append('<thead><tr>')
                        for cell in row:
                            html_lines.append(f'<th>{cell}</th>')
                        html_lines.append('</tr></thead>')
                    elif i == 1:
                        # 跳过分隔行
                        continue
                    else:
                        html_lines.append('<tbody><tr>')
                        for cell in row:
                            html_lines.append(f'<td>{cell}</td>')
                        html_lines.append('</tr></tbody>')
                html_lines.append('</table>')
                in_table = False
                table_rows = []
            html_lines.append('')
            continue
        
        # 检查是否是表格行
        if stripped.startswith('|') and stripped.endswith('|'):
            if not in_table:
                in_table = True
            # 解析表格行
            cells = [cell.strip() for cell in stripped.split('|')[1:-1]]
            # 跳过分隔行
            if all(set(cell) <= set('- ') for cell in cells):
                continue
            table_rows.append(cells)
            continue
        
        # 如果正在处理表格但当前行不是表格行，结束表格
        if in_table:
            html_lines.append('<table>')
            for i, row in enumerate(table_rows):
                if i == 0:
                    html_lines.append('<thead><tr>')
                    for cell in row:
                        html_lines.append(f'<th>{cell}</th>')
                    html_lines.append('</tr></thead>')
                elif i == 1:
                    continue
                else:
                    html_lines.append('<tbody><tr>')
                    for cell in row:
                        html_lines.append(f'<td>{cell}</td>')
                    html_lines.append('</tr></tbody>')
            html_lines.append('</table>')
            in_table = False
            table_rows = []
        
        # 标题
        if stripped.startswith('#'):
            level = len(stripped) - len(stripped.lstrip('#'))
            title_text = stripped[level:].strip()
            if level == 1:
                html_lines.append(f'<h2 class="section-title">{title_text}</h2>')
            elif level == 2:
                html_lines.append(f'<h3 class="subsection-title">{title_text}</h3>')
            elif level == 3:
                html_lines.append(f'<h4 class="sub-subsection-title">{title_text}</h4>')
            continue
        
        # 粗体
        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        
        # 斜体
        stripped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', stripped)
        
        # 列表
        if stripped.startswith('- ') or stripped.startswith('* '):
            html_lines.append(f'<li>{stripped[2:]}</li>')
            continue
        
        # 数字列表
        num_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        if num_match:
            html_lines.append(f'<li>{num_match.group(2)}</li>')
            continue
        
        # 普通段落
        html_lines.append(f'<p>{stripped}</p>')
    
    # 处理文件末尾的表格
    if in_table:
        html_lines.append('<table>')
        for i, row in enumerate(table_rows):
            if i == 0:
                html_lines.append('<thead><tr>')
                for cell in row:
                    html_lines.append(f'<th>{cell}</th>')
                html_lines.append('</tr></thead>')
            elif i == 1:
                continue
            else:
                html_lines.append('<tbody><tr>')
                for cell in row:
                    html_lines.append(f'<td>{cell}</td>')
                html_lines.append('</tr></tbody>')
        html_lines.append('</table>')
    
    return '\n'.join(html_lines)


def generate_report_html(
    topic: str,
    sections: List[Dict[str, Any]],
    exec_summary: str = "",
    key_findings: List[str] = None,
) -> str:
    """生成完整报告 HTML"""
    
    # 读取模板
    template_path = ROOT / "templates" / "professional_report.html"
    template = template_path.read_text(encoding="utf-8")
    
    # 生成目录
    toc_html = generate_toc_html(sections)
    
    # 生成正文
    content_html = generate_content_html(sections)
    
    # 添加关键发现
    if key_findings:
        findings_html = '<div class="key-findings"><h2>关键发现</h2><ul>'
        for finding in key_findings:
            findings_html += f'<li>{finding}</li>'
        findings_html += '</ul></div>'
        content_html = findings_html + content_html
    
    # 替换模板变量
    html = template.replace("{{title}}", topic)
    html = html.replace("{{subtitle}}", f"{topic}深度研究报告")
    html = html.replace("{{date}}", datetime.now().strftime("%Y年%m月"))
    html = html.replace("{{report_type}}", "行业深度研究")
    html = html.replace("{{toc_items}}", toc_html)
    html = html.replace("{{content}}", content_html)
    html = html.replace("{{page_num}}", "1")
    
    return html


def create_sample_data() -> Dict[str, Any]:
    """创建新能源汽车行业示例数据"""
    return {
        "sections": [
            {
                "title": "执行摘要",
                "content": """
# 核心发现

中国新能源汽车市场正处于高速增长期，2024年销量突破1000万辆，渗透率超过35%。比亚迪、特斯拉、蔚来等头部企业引领市场发展，技术创新和政策支持共同推动行业进步。

## 关键数据

- **市场规模**：2024年中国新能源汽车销量达1,020万辆，同比增长38%
- **渗透率**：新能源汽车新车销量占比达35.2%，较2023年提升8.5个百分点
- **出口增长**：新能源汽车出口量达120万辆，同比增长65%
- **技术突破**：固态电池、800V高压平台、智能驾驶技术加速落地

## 投资建议

**推荐评级**：行业整体"看好"

重点关注：
1. **电池技术**：固态电池、钠离子电池等新技术方向
2. **智能驾驶**：L3级自动驾驶商业化落地
3. **充电设施**：超充网络建设加速
4. **海外市场**：中国品牌出海机会

## 风险提示

- 原材料价格波动风险
- 技术迭代风险
- 政策调整风险
- 国际贸易摩擦风险
"""
            },
            {
                "title": "市场规模与增长",
                "content": """
# 全球新能源汽车市场

## 全球销量分析

2024年全球新能源汽车销量达到1,800万辆，同比增长35%。其中，中国市场占比超过55%，继续保持全球最大新能源汽车市场地位。

## 中国市场规模

### 销量数据

| 年份 | 销量（万辆） | 同比增长 | 渗透率 |
|------|-------------|----------|--------|
| 2020 | 136.7 | 10.9% | 5.4% |
| 2021 | 352.1 | 157.6% | 13.4% |
| 2022 | 688.7 | 95.6% | 25.6% |
| 2023 | 742.0 | 35.5% | 31.6% |
| 2024 | 1,020.0 | 37.5% | 35.2% |

### 增长驱动因素

1. **政策支持**：新能源汽车购置税减免、双积分政策持续推动
2. **技术进步**：电池成本下降、续航里程提升
3. **消费升级**：消费者对智能电动汽车接受度提高
4. **基础设施**：充电桩建设加速，使用便利性提升

## 未来市场预测

根据行业研究机构预测，2025年中国新能源汽车销量将达到1,300万辆，渗透率有望突破45%。到2030年，新能源汽车销量占比可能超过60%。
"""
            },
            {
                "title": "产业链分析",
                "content": """
# 产业链全景

新能源汽车产业链涵盖上游原材料、中游零部件制造、下游整车制造和后市场服务。

## 上游：原材料与核心部件

### 动力电池

动力电池是新能源汽车的核心部件，成本占比约40%。

**主要供应商**：
- 宁德时代（CATL）：全球市占率35%
- 比亚迪（BYD）：刀片电池技术领先
- LG新能源：韩国市场主导
- 三星SDI：高端市场布局

**技术路线**：
- 磷酸铁锂（LFP）：成本优势，安全性好
- 三元锂（NCM/NCA）：能量密度高，续航长
- 固态电池：下一代技术方向

### 电机电控

电机电控系统是新能源汽车的动力核心。

**技术趋势**：
- 永磁同步电机：效率高，成本适中
- 800V高压平台：充电快，效率高
- 碳化硅（SiC）器件：提升系统效率

## 中游：零部件制造

### 电驱动系统

电驱动系统集成电机、电控、减速器，向高度集成化发展。

**主要企业**：
- 比亚迪：全产业链布局
- 精进电动：专业电驱动供应商
- 汇川技术：工业自动化龙头

### 热管理系统

热管理系统对电池安全和续航至关重要。

**技术方向**：
- 热泵空调：节能高效
- 电池热管理：精准温控
- 集成化设计：降低成本

## 下游：整车制造

### 主要车企

**自主品牌**：
- 比亚迪：2024年销量超400万辆
- 吉利汽车：极氪品牌表现亮眼
- 长安汽车：深蓝、阿维塔布局
- 蔚来、小鹏、理想：新势力代表

**合资品牌**：
- 特斯拉：上海超级工厂产能释放
- 大众ID系列：传统车企转型
- 丰田bZ系列：氢电并行路线

## 后市场服务

### 充电服务

充电桩建设加速，超充网络逐步完善。

**数据**：
- 2024年公共充电桩保有量超300万个
- 超充桩占比提升至15%
- 车桩比降至2.5:1

### 电池回收

电池回收市场潜力巨大，2024年市场规模超200亿元。

**主要企业**：
- 格林美：电池回收龙头
- 光华科技：湿法回收技术
- 邦普循环：宁德时代子公司
"""
            },
            {
                "title": "竞争格局",
                "content": """
# 市场竞争格局

中国新能源汽车市场呈现多元化竞争格局，自主品牌、新势力、合资品牌三方角逐。

## 市场份额分析

### 2024年销量排名

| 排名 | 品牌 | 销量（万辆） | 市占率 | 同比增长 |
|------|------|-------------|--------|----------|
| 1 | 比亚迪 | 427.2 | 41.9% | 41.3% |
| 2 | 特斯拉 | 65.7 | 6.4% | 12.8% |
| 3 | 吉利汽车 | 68.7 | 6.7% | 48.2% |
| 4 | 长安汽车 | 52.3 | 5.1% | 62.1% |
| 5 | 广汽埃安 | 48.6 | 4.8% | 77.5% |
| 6 | 理想汽车 | 37.6 | 3.7% | 181.6% |
| 7 | 蔚来汽车 | 22.1 | 2.2% | 30.2% |
| 8 | 小鹏汽车 | 19.0 | 1.9% | 17.3% |

## 竞争策略分析

### 比亚迪：全产业链垂直整合

**核心优势**：
- 电池、电机、电控全产业链自研
- 规模效应显著，成本控制能力强
- 品牌矩阵完善，覆盖各细分市场

**技术亮点**：
- 刀片电池：安全性领先
- DM-i超级混动：油耗低
- 易四方平台：高端化突破

### 特斯拉：技术创新与品牌溢价

**核心优势**：
- 智能驾驶技术领先
- 品牌影响力强
- 超级充电网络完善

**技术亮点**：
- FSD自动驾驶：持续迭代
- 一体化压铸：提升效率
- Dojo超算：训练数据处理

### 新势力：差异化竞争

**蔚来**：
- 换电模式：补能便利
- 用户服务：高端体验
- 子品牌乐道：下沉市场

**小鹏**：
- 智能驾驶：技术领先
- 飞行汽车：前瞻布局
- 海外市场：积极拓展

**理想**：
- 增程式技术：解决里程焦虑
- 家庭用户定位：精准营销
- 产品定义能力：爆款频出

## 竞争趋势

1. **价格战加剧**：新能源汽车价格竞争白热化
2. **智能化竞争**：智能驾驶成为核心差异化因素
3. **品牌向上**：自主品牌冲击高端市场
4. **出海加速**：中国品牌国际化步伐加快
"""
            },
            {
                "title": "技术趋势",
                "content": """
# 技术发展趋势

新能源汽车技术正朝着电动化、智能化、网联化、共享化方向发展。

## 电池技术

### 固态电池

固态电池是下一代电池技术的重要方向。

**技术优势**：
- 能量密度高：可达500Wh/kg
- 安全性好：无液态电解液
- 寿命长：循环次数提升

**产业化进展**：
- 2024年：小批量装车测试
- 2025年：预计量产装车
- 2030年：大规模商业化

### 钠离子电池

钠离子电池是锂离子电池的重要补充。

**技术特点**：
- 资源丰富：钠元素广泛存在
- 成本低：材料成本下降
- 低温性能好：适应寒冷环境

**应用场景**：
- 低速电动车
- 储能系统
- A00级电动车

### 电池结构创新

**CTP（Cell to Pack）技术**：
- 跳过模组，直接集成
- 提升空间利用率
- 降低成本

**CTC（Cell to Chassis）技术**：
- 电池与底盘一体化
- 提升车身刚性
- 降低重量

## 智能驾驶

### L3级自动驾驶

L3级自动驾驶是当前技术发展重点。

**技术要求**：
- 高精度地图
- 多传感器融合
- 冗余系统设计

**商业化进展**：
- 2024年：部分车型量产
- 2025年：大规模推广
- 2030年：L4级逐步落地

### 智能座舱

智能座舱是用户体验的重要载体。

**技术趋势**：
- 大屏化：多屏互动
- 语音交互：自然语言处理
- AR-HUD：增强现实显示
- 车联网：V2X技术

## 电驱动技术

### 800V高压平台

800V高压平台是电驱动技术重要方向。

**技术优势**：
- 充电快：10分钟充电80%
- 效率高：损耗降低
- 重量轻：线束细化

**产业化进展**：
- 2024年：多款车型搭载
- 2025年：成为主流配置

### 碳化硅（SiC）器件

碳化硅器件提升电驱动系统效率。

**技术特点**：
- 耐高温：工作温度更高
- 效率高：开关损耗低
- 体积小：功率密度高

## 轻量化技术

### 材料创新

**铝合金**：车身覆盖件
**高强度钢**：车身结构件
**碳纤维**：高端车型应用

### 制造工艺

**一体化压铸**：减少零部件数量
**激光焊接**：提升连接强度
**3D打印**：快速原型制造
"""
            },
            {
                "title": "政策环境",
                "content": """
# 政策环境分析

政策是新能源汽车产业发展的重要推动力。

## 国家政策

### 产业政策

**《新能源汽车产业发展规划（2021-2035年）》**：
- 2025年：新能源汽车销量占比达20%
- 2030年：纯电动汽车成为新销售车辆主流
- 2035年：新能源汽车占汽车总销量50%以上

**双积分政策**：
- 企业平均燃料消耗量积分
- 新能源汽车积分
- 积分交易机制

### 财税政策

**购置税减免**：
- 2024-2025年：免征购置税
- 2026-2027年：减半征收
- 2028年起：恢复正常税率

**补贴政策**：
- 国家补贴：已退出
- 地方补贴：部分城市仍有
- 企业补贴：车企自行承担

### 基础设施政策

**充电设施建设**：
- 2025年：公共充电桩超500万个
- 车桩比：目标2:1
- 超充网络：重点城市覆盖

**换电设施建设**：
- 换电站建设补贴
- 换电标准统一
- 换电模式推广

## 地方政策

### 一线城市

**北京**：
- 新能源汽车指标
- 限行优惠政策
- 充电设施建设

**上海**：
- 新能源汽车免费牌照
- 充电设施补贴
- 智能网联测试

**深圳**：
- 新能源汽车推广
- 充电设施规划
- 电池回收政策

### 二线城市

各地积极出台新能源汽车推广政策，包括购车补贴、充电设施建设、限行优惠等。

## 国际政策

### 欧盟

**碳排放政策**：
- 2035年：禁售燃油车
- 碳交易机制
- 电池法规

### 美国

**通胀削减法案**：
- 电动车税收抵免
- 本土化生产要求
- 电池供应链安全

### 东南亚

**泰国**：
- 电动车进口关税减免
- 本地生产补贴
- 充电设施建设

**印度**：
- FAME II计划
- 本地生产激励
- 充电设施建设

## 政策趋势

1. **政策延续**：新能源汽车支持政策持续
2. **市场化转型**：补贴逐步退出，市场驱动增强
3. **基础设施**：充电设施建设成为政策重点
4. **国际化**：中国品牌出海政策支持
"""
            },
            {
                "title": "风险分析",
                "content": """
# 风险分析

新能源汽车行业面临多种风险，需要投资者和企业关注。

## 市场风险

### 价格竞争风险

**风险描述**：
- 价格战加剧，利润空间压缩
- 低端市场竞争激烈
- 品牌溢价能力下降

**影响程度**：高

**应对策略**：
- 差异化竞争
- 成本控制
- 品牌建设

### 市场需求波动

**风险描述**：
- 经济周期影响消费能力
- 消费者偏好变化
- 替代技术出现

**影响程度**：中

**应对策略**：
- 多元化产品布局
- 用户需求洞察
- 技术储备

## 技术风险

### 技术迭代风险

**风险描述**：
- 电池技术路线变化
- 智能驾驶技术瓶颈
- 技术标准不统一

**影响程度**：高

**应对策略**：
- 多技术路线布局
- 加大研发投入
- 技术合作

### 供应链风险

**风险描述**：
- 关键原材料供应紧张
- 芯片供应不足
- 供应商集中度高

**影响程度**：高

**应对策略**：
- 供应链多元化
- 战略库存储备
- 国产替代

## 政策风险

### 政策调整风险

**风险描述**：
- 补贴政策退出
- 环保标准提高
- 贸易政策变化

**影响程度**：中

**应对策略**：
- 关注政策动态
- 提前布局
- 多元化市场

### 环保政策风险

**风险描述**：
- 电池回收要求提高
- 生产过程环保要求
- 碳排放交易影响

**影响程度**：中

**应对策略**：
- 绿色生产
- 电池回收体系
- 碳资产管理

## 运营风险

### 质量安全风险

**风险描述**：
- 电池安全问题
- 产品质量控制
- 召回风险

**影响程度**：高

**应对策略**：
- 严格质量控制
- 安全测试验证
- 完善售后服务

### 成本控制风险

**风险描述**：
- 原材料价格波动
- 制造成本上升
- 人工成本增加

**影响程度**：中

**应对策略**：
- 成本优化
- 规模效应
- 自动化生产

## 国际风险

### 贸易摩擦风险

**风险描述**：
- 关税壁垒
- 技术封锁
- 市场准入限制

**影响程度**：高

**应对策略**：
- 本地化生产
- 技术自主
- 多元化市场

### 汇率风险

**风险描述**：
- 汇率波动影响
- 跨境结算风险
- 资金回流风险

**影响程度**：中

**应对策略**：
- 汇率对冲
- 本地化运营
- 多币种结算
"""
            },
            {
                "title": "投资建议与展望",
                "content": """
# 投资建议与展望

## 投资机会分析

### 电池技术领域

**投资机会**：
- 固态电池：下一代技术方向
- 钠离子电池：成本优势明显
- 电池回收：市场潜力巨大

**推荐标的**：
- 宁德时代：全球龙头
- 比亚迪：全产业链布局
- 国轩高科：技术储备丰富

### 智能驾驶领域

**投资机会**：
- L3级自动驾驶：商业化落地
- 智能座舱：用户体验提升
- 车联网：V2X技术应用

**推荐标的**：
- 华为汽车：技术领先
- 德赛西威：智能座舱
- 经纬恒润：汽车电子

### 充电设施领域

**投资机会**：
- 超充网络：建设加速
- 换电模式：标准化推进
- 充电运营：商业模式创新

**推荐标的**：
- 特锐德：充电桩龙头
- 星星充电：运营服务
- 换电联盟：宁德时代等

### 海外市场领域

**投资机会**：
- 东南亚市场：增长潜力大
- 欧洲市场：品牌向上
- 南美市场：新兴市场

**推荐标的**：
- 比亚迪：出海先锋
- 上汽集团：欧洲布局
- 长城汽车：东南亚战略

## 估值分析

### 行业估值

**当前估值水平**：
- 新能源汽车指数PE：25倍
- 历史分位数：40%
- 估值合理偏低

**估值展望**：
- 短期：估值修复
- 中期：业绩驱动
- 长期：成长溢价

### 个股估值

**比亚迪**：
- 2024年PE：20倍
- 2025年PE：15倍
- 目标价：合理

**宁德时代**：
- 2024年PE：18倍
- 2025年PE：14倍
- 目标价：低估

## 投资策略

### 短期策略（3-6个月）

**配置建议**：
- 电池龙头：宁德时代、比亚迪
- 智能驾驶：华为汽车产业链
- 充电设施：特锐德

**风险控制**：
- 仓位控制：不超过30%
- 止损设置：-10%
- 分散投资：3-5只股票

### 中期策略（6-12个月）

**配置建议**：
- 电池技术：固态电池、钠离子电池
- 智能驾驶：L3级自动驾驶
- 海外市场：出海龙头

**风险控制**：
- 仓位控制：不超过40%
- 止损设置：-15%
- 定期调整：季度调仓

### 长期策略（1-3年）

**配置建议**：
- 行业龙头：比亚迪、宁德时代
- 技术创新：固态电池、智能驾驶
- 新兴市场：东南亚、欧洲

**风险控制**：
- 仓位控制：不超过50%
- 止损设置：-20%
- 长期持有：价值投资

## 未来展望

### 行业发展趋势

1. **电动化深化**：新能源汽车渗透率持续提升
2. **智能化加速**：智能驾驶成为标配
3. **网联化普及**：车联网技术广泛应用
4. **全球化拓展**：中国品牌走向世界

### 技术发展方向

1. **电池技术**：固态电池、钠离子电池商业化
2. **智能驾驶**：L4级自动驾驶逐步落地
3. **电驱动技术**：800V高压平台普及
4. **轻量化技术**：新材料、新工艺应用

### 市场格局演变

1. **集中度提升**：头部企业市场份额扩大
2. **品牌分化**：高端、中端、低端市场分化
3. **国际化加速**：中国品牌海外市场份额提升
4. **生态化竞争**：从单一产品到生态服务

## 风险提示

1. **市场风险**：新能源汽车销量不及预期
2. **技术风险**：技术路线变化风险
3. **政策风险**：政策调整风险
4. **国际风险**：国际贸易摩擦风险

**免责声明**：本报告仅供参考，不构成投资建议。投资者应独立判断，自行承担投资风险。
"""
            }
        ],
        "key_findings": [
            "中国新能源汽车市场2024年销量突破1000万辆，渗透率超过35%",
            "比亚迪以427万辆销量稳居市场第一，市占率达41.9%",
            "固态电池、800V高压平台等新技术加速产业化",
            "智能驾驶成为核心差异化因素，L3级自动驾驶逐步落地",
            "政策支持持续，但补贴逐步退出，市场驱动增强",
            "海外市场拓展加速，中国品牌国际化步伐加快",
            "行业竞争加剧，价格战风险需要关注",
            "投资建议：看好电池技术、智能驾驶、充电设施等领域机会"
        ]
    }


async def generate_new_energy_vehicle_report(
    output_dir: str = None,
) -> Dict[str, Any]:
    """
    生成新能源汽车行业深度研究报告
    
    Args:
        output_dir: 输出目录
    
    Returns:
        生成结果
    """
    from src.converters.html_to_word import HTMLToWordConverter
    
    # 设置输出目录
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = ROOT / "output" / "new_energy_vehicle_report"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"开始生成新能源汽车行业深度研究报告")
    print(f"输出目录: {out_dir}")
    
    # 创建示例数据
    sample_data = create_sample_data()
    
    # 生成专业级 HTML
    html_content = generate_report_html(
        topic="中国新能源汽车行业深度研究",
        sections=sample_data["sections"],
        key_findings=sample_data["key_findings"],
    )
    
    # 保存 HTML
    html_file = out_dir / "report.html"
    html_file.write_text(html_content, encoding="utf-8")
    
    # 转换为 Word
    converter = HTMLToWordConverter()
    word_result = converter.convert(
        html=html_content,
        output_path=str(out_dir / "中国新能源汽车行业深度研究.docx"),
    )
    
    print(f"报告生成完成!")
    print(f"  - HTML: {html_file}")
    print(f"  - Word: {out_dir / '中国新能源汽车行业深度研究.docx'}")
    
    return {
        "success": True,
        "topic": "中国新能源汽车行业深度研究",
        "output_dir": str(out_dir),
        "html_file": str(html_file),
        "word_file": str(out_dir / "中国新能源汽车行业深度研究.docx"),
        "word_size": word_result.file_size if word_result.success else 0,
    }


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="新能源汽车行业深度研究报告生成脚本")
    parser.add_argument("--output", help="输出目录")
    
    args = parser.parse_args()
    
    result = asyncio.run(generate_new_energy_vehicle_report(
        output_dir=args.output,
    ))
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
