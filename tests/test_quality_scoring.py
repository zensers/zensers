# -*- coding: utf-8 -*-
"""Quality scoring real test — 4 scenarios x 3 pipelines"""
import sys, re
sys.path.insert(0, r"E:\market_report_systerm")

from src.core.quality.checkers import (
    DataCollectionQualityChecker,
    AnalysisQualityChecker,
    ReportQualityChecker,
)

SCENARIO_A = "核心判断市场增长数据来源官方统计如果需求下滑贡献3个百分点意味着投资机会"

SCENARIO_B = """## 市场规模分析

### 核心判断
中国新能源汽车市场2025年规模预计达到1.2万亿元，同比增长25%。这一判断基于以下数据支撑和政策驱动分析。

### 数据来源与支撑
根据中国汽车工业协会数据，2024年新能源汽车销量达到950万辆，市场渗透率35%。
工信部《新能源汽车产业发展规划》设定2025年渗透率40%目标。
乘联会数据显示，2025年Q1销量同比增长32%，达280万辆。

### 驱动因素分解
市场规模增长可分解为：销量增长贡献18个百分点，其中纯电动贡献12个百分点，插混贡献6个百分点；
单车均价提升贡献5个百分点；政策补贴延续贡献2个百分点。

### 反证与边界条件
但需注意：若补贴政策提前退坡，预计影响销量5-8个百分点。同时，三四线城市渗透率仅18%，
远低于一二线城市的45%，下沉市场增速存在不确定性。原材料价格波动（碳酸锂价格2024年波动幅度达40%）
也可能影响成本结构。

### 对投资决策的含义
这意味着：短期（6-12月）行业仍处景气上行期，建议超配整车龙头；中期需关注补贴退坡时点和
下沉市场渗透节奏；长期技术路线（固态电池商业化进度）是核心变量。
"""

SCENARIO_C = """## 新能源汽车行业深度分析

### 核心判断
中国新能源汽车产业正处于从政策驱动向市场驱动转型的关键节点。2025年市场规模预计突破1.2万亿元，
但增速将从2024年的35%逐步回落至20-25%区间，行业进入量增价减的成熟期前夜。
这一判断基于对需求侧、供给侧、政策侧三维度交叉验证。

### 数据来源与口径声明
本分析数据来源（按可信度排序）：
1. 中汽协（官方）：2024年新能源销量950万辆，A股口径，含商用车
2. 乘联会（行业）：2024年零售887万辆，不含商用车，零售口径
3. 工信部（官方）：2025年1-3月产量285万辆，含出口
4. Marklines（国际）：全球2024年新能源销量1450万辆

数据口径差异说明：中汽协与乘联会差异主要在于商用车统计口径（差值约63万辆），
后续分析统一采用中汽协含商用车口径。

### 驱动因素量化分解
2025年市场增长可分解为：
- 内生需求增长：贡献约12个百分点（一线换购+二线增购）
- 下沉市场渗透：贡献约6个百分点（三四线渗透率从18%到25%）
- 出口增量：贡献约4个百分点（东南亚+中东市场）
- 政策延续效应：贡献约3个百分点（购置税减免延续）
- 合计：约25个百分点，与历史增速趋势一致

交叉验证：用Bass扩散模型拟合，预测2025年渗透率39.5%，与工信部40%目标偏差1.5%，
在模型误差范围内。

### 反证与边界条件
需要关注的风险因素：
1. 补贴退坡风险：若2025年底购置税优惠完全取消，根据韩国经验（2016年退坡后销量下滑32%），
   短期冲击可能达15-20个百分点。但中国与韩国差异在于：中国已形成消费习惯（渗透率35% vs 韩国2016年8%），
   预计冲击幅度约8-12个百分点。
2. 技术路线不确定性：固态电池量产时间表从2027推迟至2028-2029的概率约40%（基于专利申请趋势），
   若推迟将延长液态电池主导期，对宁德时代等电池厂商影响中性偏正。
3. 地缘政治风险：欧盟反补贴税已落地（17-35%），对出口增速影响约2-3个百分点。
4. 原材料价格：碳酸锂价格从2023年60万/吨跌至2024年8万/吨，已接近成本线，
   进一步下跌空间有限，对电池成本改善的边际贡献递减。

### 对投资决策的含义与建议
短期（6个月）：行业景气度仍在高位，建议超配整车龙头（比亚迪、吉利）和智能化标的（德赛西威）。
中期（6-18个月）：关注补贴退坡时点，退坡前3个月建议减配纯电标的，增配插混（受影响较小）。
长期（2年+）：固态电池商业化进度是核心变量，若2027年量产则利好固态路线标的（清陶能源），
否则液态电池龙头（宁德时代）护城河更稳固。
"""

SCENARIO_D = "新能源汽车市场在增长。2024年销量950万辆。政策支持力度大。"

print("=" * 70)
print("AnalysisQualityChecker")
print("=" * 70)
checker = AnalysisQualityChecker(threshold=70.0)
for name, content in [("A-cheat", SCENARIO_A), ("B-typical", SCENARIO_B),
                       ("C-pro", SCENARIO_C), ("D-poor", SCENARIO_D)]:
    s = checker._check_structure(content)
    c = checker._check_caliber_coverage(content)
    ce = checker._check_counter_evidence(content)
    q = checker._check_quantified_decomposition(content)
    r = checker.check({"content": content})
    print(f"{name}: struct={s:.1f} caliber={c:.1f} counter={ce:.1f} quant={q:.1f} => score={r.score:.1f} passed={r.passed}")

print()
print("=" * 70)
print("DataCollectionQualityChecker")
print("=" * 70)
dc = DataCollectionQualityChecker(threshold=70.0)
for name, vol, qs, srcs in [
    ("hardcode50", 30, 50.0, ["gov.cn", "caixin.com", "baidu.com", "sina.com", "gov.cn"]),
    ("actual72", 30, 72.0, ["gov.cn", "caixin.com", "baidu.com", "sina.com", "gov.cn"]),
    ("actual88", 50, 88.0, ["gov.cn", "stats.gov.cn", "caixin.com", "reuters.com", "gov.cn"]),
    ("low50", 10, 50.0, ["blog.com", "weibo.com"]),
]:
    data = {"quality_metadata": {"data_volume": vol, "quality_score": qs, "sources": srcs}}
    r = dc.check(data)
    print(f"{name}: score={r.score:.1f} passed={r.passed}")

print()
print("=" * 70)
print("ReportQualityChecker")
print("=" * 70)
rc = ReportQualityChecker(threshold=80.0)

sec8 = [{"id": f"s{i}", "content": SCENARIO_B[:200], "role": "analysis"} for i in range(8)]
d8 = {"sections": sec8, "findings": [], "execution_logs": []}
r8 = rc.check(d8)
det8 = rc._get_details(d8, {})
print(f"8sec-nofind: comp={det8['completeness']:.1f} cons={det8['cross_chapter_consistency']:.1f} red={det8['data_redundancy']:.1f} prov={det8['finding_provenance']:.1f} => score={r8.score:.1f}")

sec3 = [{"id": f"s{i}", "content": SCENARIO_D, "role": "analysis"} for i in range(3)]
d3 = {"sections": sec3, "findings": [], "execution_logs": []}
r3 = rc.check(d3)
det3 = rc._get_details(d3, {})
print(f"3sec-poor:  comp={det3['completeness']:.1f} cons={det3['cross_chapter_consistency']:.1f} red={det3['data_redundancy']:.1f} prov={det3['finding_provenance']:.1f} => score={r3.score:.1f}")

sec10e = [{"id": f"s{i}", "content": "", "role": "analysis"} for i in range(10)]
d10e = {"sections": sec10e, "findings": [], "execution_logs": []}
r10e = rc.check(d10e)
det10e = rc._get_details(d10e, {})
print(f"10empty:    comp={det10e['completeness']:.1f} cons={det10e['cross_chapter_consistency']:.1f} red={det10e['data_redundancy']:.1f} prov={det10e['finding_provenance']:.1f} => score={r10e.score:.1f}")

print()
print("=" * 70)
print("Caliber Regex Bug")
print("=" * 70)
buggy = r"[A股|港股|美股|GAAP|IFRS]口径"
fixed = r"(?:A股|港股|美股|GAAP|IFRS|纳斯达克|纽交所|深交所)口径"
for s in ["A股口径", "港股口径", "美股口径", "A口径", "G口径", "|口径", "IFRS口径"]:
    bm = bool(re.search(buggy, s))
    fm = bool(re.search(fixed, s))
    tag = " <<< BUG!" if bm != fm else ""
    print(f"  {s}: buggy={bm} fixed={fm}{tag}")

print()
print("=" * 70)
print("Chinese Tokenize Bug")
print("=" * 70)
claim = "核心判断市场增长趋势明显"
split_result = claim.split()
regex_result = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}|\d+\.?\d*", claim)
print(f"  text: {claim}")
print(f"  split() => {split_result}")
print(f"  regex   => {regex_result}")
print(f"  split len>3 => {[w for w in split_result if len(w) > 3]}")
print(f"  regex len>=2 => {[t for t in regex_result if len(t) >= 2]}")
