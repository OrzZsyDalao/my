"""Apply a prose-only revision to the archived Source6 manuscript."""
from pathlib import Path
import json
import re
import difflib
import hashlib
import collections

ROOT = Path(__file__).resolve().parents[1]
changes = []

def edit(file, prefix, replacement, reason, benefit):
    path = ROOT / file
    text = path.read_text(encoding='utf-8')
    blocks = text.split('\n\n')
    matches = [i for i, block in enumerate(blocks) if block.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError((file, prefix, matches))
    i = matches[0]
    before = blocks[i]
    blocks[i] = replacement.strip()
    path.write_text('\n\n'.join(blocks), encoding='utf-8')
    changes.append(dict(id=f'E{len(changes)+1:03}', file=file, before=before,
                        after=replacement.strip(), reason=reason, benefit=benefit))

for path in (ROOT / 'original').rglob('*.tex'):
    target = ROOT / path.relative_to(ROOT / 'original')
    target.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')

edit('IEEE-conference-template-062824.tex', r'\begin{abstract}', r'''
\begin{abstract}
The diversity visible in traceroute does not reveal how broadly physical
infrastructure supports Internet service paths. A country may reach a service
through many network transitions while those paths converge on only a few
feasible coastal directions. We study this cross-layer divergence by comparing
distributions of observed AS transitions and feasible landing-region corridors
over identical path segments. Our analysis covers RIPE Atlas measurements of
DNS Roots, applications, and multi-target topology references. Network
diversity and physical-corridor diversity often diverge for service-facing
paths: some country--service populations combine broad network transitions
with concentrated feasible-corridor support, while others remain broad at both
layers. This contraction is much less common in multi-target topology
measurements, showing that service selection and deployment must be retained
when characterizing the user-visible physical footprint. Exposure and physical
concentration describe distinct properties. Geography shapes entry into
submarine infrastructure; service deployment and target selection shape
whether that exposure spreads across coastal directions or concentrates within
a few. Multiple network routes can rest on a narrow feasible physical-corridor
space, making a cross-layer view essential to evaluating service diversity.
\end{abstract}
''', '摘要首句直接提出研究问题，将方法、发现和意义按证据顺序组织；删除与引言重复的通用背景。', '读者先看到论文要解决的关系问题；保留 may、often、much less common、showing 和原有因果判断，不增加结果数字。')

f = 'files/1-introduction.tex'
edit(f, 'Submarine cables form', r'''
Submarine cables form the physical backbone of the global Internet, carrying
nearly all intercontinental traffic and connecting users to services worldwide
~\cite{telegeography_submarine_map}. Cable disruptions can isolate regions,
degrade remote-service access, and redirect paths toward longer or congested
alternatives. Internet measurements describe the paths through logical
indicators such as routers, Autonomous Systems (ASes), and service replicas.
''', '保留问题背景，将 expose these paths 改为语义更清晰的 describe the paths。', '使网络层观测自然引出下一段的跨层比较，保留 can 的判断强度。')
edit(f, 'Logical and physical diversity', r'''
Logical and physical diversity describe different structures. Paths traversing
different routers or ASes may leave a country or region through the same
coastal area or converge on the same submarine corridor. Hereafter, country
refers to countries or regions. A service can therefore present a broad
network-layer path population while its feasible physical support occupies
only a few coastal directions. Joint analysis of the application target,
observed network path, and physical candidate space reveals whether
network-layer diversity is preserved across coastal directions.
''', '将插入句中的国家与地区定义独立成句，保持原有可能性与推论关系。', '读者可以连续理解不同 AS 与共同沿海方向的关系，不被长括号打断。')
edit(f, 'Prior work measures', r'''
Prior work measures user-path involvement with submarine infrastructure
~\cite{liu2020outofsight}, associates AS links with cable systems
~\cite{ye2023impact,ramanathan2023nautilus,wang2025calypso}, and constructs
cross-layer infrastructure maps~\cite{durairajan2013atlas,anderson2022igdb}.
Our paired distribution audit compares the network transitions and feasible
landing-region corridors of each country-service population. Both
distributions are constructed from the same atomic segments.
''', '保持文献及顺序，将本工作拆成比较对象和总体对齐两个句子。', '贡献落在具体分析动作上，与前人工作的关系更直接。')
edit(f, 'A \\emph{landing-region corridor}', r'''
A \emph{landing-region corridor} is a direction-independent pair of bounded
landing regions connected by at least one active cable candidate. Router
locations, cable landing points and lifecycles, and propagation time determine
each segment's feasible corridor set. We allocate equal shares of segment
observation mass across this set and aggregate them into a candidate-support
distribution aligned with the network-transition distribution.
''', '用主动动词说明均分和聚合步骤，保留走廊定义及全部约束。', '让读者知道论文实际如何构建比较，而非只看到被动的分布描述。')
edit(f, 'We study three questions:', 'We organize the audit around three research questions:', '删除含糊的引导，明确三个 RQ 与审计的关系。', '连接研究问题与后续方法，不改 RQ 编号或对象。')
edit(f, r'\textbf{RQ1}', r'\textbf{RQ1} How frequently do country-service paths contain a feasible inter-region submarine corridor?', '将不完整的陈述句改为研究问题。', '保持原问题的 exposure 对象，语法与功能一致。')
edit(f, r'\textbf{RQ2}', r'\textbf{RQ2} How is observation mass distributed across feasible corridors?', '将问题改为完整疑问句。', '保持 observation mass 与 feasible corridors 的原有关系。')
edit(f, r'\textbf{RQ3}', r'''\textbf{RQ3} Which country-service populations have broad network
transition distributions that project onto narrower corridor distributions?''', '将识别任务改为明确研究问题。', '保留哪些总体收缩的原始范围，不改成普遍收缩或因果解释。')
edit(f, 'We used dataset contains', r'''
We analyze 490,911 valid traceroutes from 18 public RIPE Atlas measurements
covering all 13 DNS Roots, Wikipedia, Reddit, Netflix Assets, and two
multi-target topology references. The aligned one-hour snapshot yields
3,291,063 atomic segments. Of these, 2,432,559 are projection-eligible and
124,350 support at least one feasible inter-region corridor. Under the 30-km
landing-region abstraction, 42.1\% of candidate-bearing segments support
multiple corridors.
''', '修复语法错误，将数据规模与逐层筛选拆开。', '完整保留数字和统计总体，降低读者核对分母的负担。')
edit(f, 'For each auditable country-measurement', r'''
We compare the distributions within each auditable country-measurement unit.
Ordered endpoint-AS pairs form the network distribution, and uniformly
allocated segment mass forms the corridor distribution. Top-2 share measures
absolute concentration, effective category count measures breadth, and
normalized entropy measures support-relative evenness. A common 80\% Top-2
threshold supplies a descriptive four-class view.
''', '段首先说明比较单位，再解释两层构造和指标。', '突出同总体比较，使指标介绍有明确用途。')
edit(f, 'The 370-unit analysis', r'''
The 370-unit analysis identifies both contraction and broad support across
layers. It contains 222 DNS Root, 53 application, and 95 topology-reference
units. Median corridor Top-2 shares are 72.0\%, 70.3\%, and 30.6\%, with
effective corridor counts of 3.84, 3.51, and 18.01. Among 275 service-facing
units, 81 (29.5\%) combine broad network and concentrated corridor
distributions, and 158 (57.5\%) remain broad at both layers; 4 of 95
topology-reference units enter the first class.

Country-matched comparisons further show lower inter-region candidate
exposure for service-facing measurements. Island and archipelagic countries
form the highest-exposure group.
''', '以已有发现作主题句，将跨层结果与 exposure 结果拆为两段。', '每段只处理一种比较，避免不同指标与分母挤在同一长段。')
edit(f, 'This paper makes three contributions.', r'''
This paper makes three contributions. First, it formulates application-aware
submarine-cable measurement as a three-layer audit connecting services,
network transitions, and feasible physical corridors. Second, it develops a
reproducible projection that applies geographic, lifecycle, and propagation
feasibility and allocates observation mass uniformly over each segment's
corridor set. Third, it measures exposure, concentration, and cross-layer
contraction across DNS Roots, applications, and topology references,
including geographic and resolution sensitivity analyses.
''', '将第二项贡献中的步骤写成具体动作，保持三项贡献的内容。', '贡献与实际方法逐项对应，不引入新的创新性或优越性主张。')

f = 'files/2-background.tex'
edit(f, 'Users reach services', r'''
Users reach services through domain names, CDN resources, replicas, and anycast
targets. Traceroute exposes the intervening IP hops and AS transitions. For
geographically separated regions, these logical paths depend on submarine
cables that join coastal landing stations to terrestrial backhaul and visible
ASes. Multiple cables can connect the same coastal regions, and one cable can
serve several landing locations.
''', '调整关系从句，使逻辑路径与海缆连接对象更清楚。', '保留原有 depend on 判断，不增加陆路排除或新的传输机制。')
edit(f, 'The network-to-physical relationship', r'''
The network-to-physical relationship is many-to-many. Different routers or AS
transitions may project onto one landing-region corridor, while a recurring
network transition may support several physical alternatives. We measure the
two distributions over the same observations: network diversity describes
observed logical transitions, and physical diversity describes their supported
corridor distribution.
''', '将原有定义合并为一组平行表述。', '强调同一观测的两种分布，为配对方法铺垫。')
edit(f, 'Landing regions provide', r'''
Landing regions provide a stable geographic unit between exact landing
stations and country-wide cable counts. Exact stations preserve facility
detail but split nearby coastal access points that serve the same direction.
Country-level cable inventories combine distinct coastlines and international
directions. A bounded landing region retains coastal structure, and a corridor
identifies the paired entry-exit direction connecting two such regions.
Parallel cable systems can share one corridor while remaining distinguishable
in the underlying candidate records.
''', '整理尺度比较，删除 therefore 的重复推导语气。', '保留各尺度的功能与原有 can，解释走廊这一分析单位的选择。')
edit(f, 'Countries provide', r'''
Countries provide a shared geographic and external-connectivity context.
Island, coastal, and landlocked geography shapes access to submarine
infrastructure; landing facilities, backhaul, gateways, exchanges, and operator
interconnection shape the paths available to users. Country grouping retains
variation among access networks and upstream providers within that context.
''', '删除 So it is natural to research on country-level 的结论复述。', '直接用分组保留了什么解释分析粒度，不使用主观合理性判断。')
edit(f, 'Event-oriented studies', r'''
Event-oriented studies relate new submarine connectivity to routing changes.
Bischof et al.\ characterized Cuba's connectivity before and after ALBA-1 and
later formulated the task of connecting Internet observations to the worldwide
cable mesh~\cite{bischof2015cuba,bischof2018untangling}. Fanou et al.\ measured
routing changes following new cable deployments~\cite{fanou2020unintended}.
''', '将文献贡献与具体研究对象紧密连接。', '保留文献先后、对象和时间关系，减少宽泛修饰。')
edit(f, 'These two perspectives motivate', r'''
Exposure and concentration describe complementary aspects of service paths.
Exposure counts how frequently a service path enters a feasible submarine
candidate space. Concentration examines the structure of that space after
entry. A country may have high exposure and broad corridor support, or low
exposure with the exposed observations concentrated on a few directions.
''', '段首先点出两项指标的关系，保留高低组合的可能性。', '让指标定义承担动机说明，避免依赖泛指的 two perspectives。')
edit(f, 'Service deployment determines', r'''
Service deployment determines which paths enter these mappings. Anycast
routing, replica placement, and interconnection select service instances and
their network paths~\cite{cicalese2015anycast,devries2017anycast}. We retain
this service-specific path view when projecting physical candidates and
comparing network and corridor distributions over identical atomic segments.
''', '用 retain、project、compare 交代本研究承接的分析步骤。', '比较围绕研究视角推进，不添加 Calypso 2026 的外部事实。')
edit(f, 'The paired construction also aligns', r'''
The paired construction aligns the statistical unit across layers. A network
transition and its corridor support originate from the same atomic segment,
so changes in concentration reflect the projection of a fixed observation
population. Country-service aggregation preserves deployment differences
among equivalent services and geographic differences among their users.
''', '删除 also、then 等不必要衔接，保留原有 so 推论。', '将总体对齐的作用单独说清，不把该作用扩写成误差或偏差保证。')
edit(f, 'Country and service jointly', r'''
Country and service jointly define each observation population. Geographic and
interconnection environments shape source-side options; anycast, replica
selection, and routing choose among them. DNS Roots illustrate this
interaction. Functionally equivalent services operate independent anycast
deployments, so a country may reach different Roots through distinct
instances, AS transitions, and corridors. Distributed applications similarly
localize access in some countries and direct others toward remote
infrastructure.
''', '将 DNS Roots 示例从长句拆为观察对象与解释两句。', '突出为什么研究服务差异，保留 may 和部署解释的原强度。')
edit(f, 'Multi-target topology measurements', r'''
Multi-target topology measurements provide a broader reference population.
Their dynamic destinations sample many network directions during the same
time window. Each service measurement instead retains the destinations
selected for that service. Comparing these families characterizes the
observed footprints of their target-selection and routing processes.
''', '拆分两类测量总体的定义。', '清楚交代比较对象，不新增控制实验或因果识别的含义。')

f = 'files/3-framework.tex'
edit(f, 'The framework combines', r'''
The framework constructs paired network and corridor distributions for each
country-service group. It combines traceroute, probe metadata, IP geolocation
and ASN mappings, AS context, and cable metadata. Figure
~\ref{fig:framework_pipeline} shows the three components in processing order:
path extraction creates atomic hop-pair segments, corridor projection
constructs each segment's feasible landing-region corridor set, and
aggregation forms the paired distributions. Complete traceroutes supply the
exposure denominator.
''', '先交代产出，再给输入和三个处理步骤。', '读者先知道框架用途，再理解流程；保持方法步骤与顺序。')
edit(f, 'The two outputs answer', r'''
The outputs retain the distinction between trace-level exposure and
segment-level distributions. Exposure records whether a path contains at
least one inter-region feasible corridor. The distributions condition on
candidate-bearing observations and compare how their mass is organized across
logical transitions and physical directions.
''', '用两个实际统计层级替代 questions 的泛指。', '分母与比较单位直接可见，避免后文反复解释。')
edit(f, 'Traceroutes are grouped', r'''
We group traceroutes by probe country and measured service to retain the
source-side connectivity context and deployment-specific destination
selection. Hop countries remain segment attributes.
''', '采用主动动词说明分组及目的。', '区分 probe country 和 hop countries，保持原对象。')
edit(f, 'Each traceroute is normalized', r'''
We normalize each traceroute into visible hops with locations, ASNs, and RTTs.
The analysis uses the complete visible sequence. An auxiliary path-entry view
ends at the first appearance of the target ASN.
''', '拆分主要路径范围与辅助范围。', '两个范围不再挤在同一句内，方法顺序保持不变。')
edit(f, 'Successive visible, geolocated', r'''
Successive visible, geolocated hops form atomic segments. Each segment records
endpoint locations, ASNs, countries, positions, RTT difference, and bridged-hop
count. Repeated hops and RTT samples retain their trace identity and ordering.
When timeouts separate two visible hops, the bridged-hop count records the gap
for pipeline accounting.
''', '将片段生成与记录字段分开。', '读者可逐步对应实现，全部字段及超时处理保留。')
edit(f, 'When both endpoint ASNs', r'''
When both endpoint ASNs are available, their ordered pair is the segment's
network-transition label. Segments with one missing endpoint ASN receive an
ordered country-pair fallback label.

Audit eligibility is evaluated over the complete country-service group. It
requires a country-fallback share of at most 30\%, at least 30
candidate-bearing segments, 10 probes, and 3 probe ASNs.
''', '将标签构造与总体审计条件拆段。', '避免把分组阈值误读为单片段或单走廊阈值。')
edit(f, 'Endpoint catchment and landing-region', r'''
Endpoint catchment retrieves landing stations, and landing-region grouping
organizes them into coastal regions. The 50-km catchment retrieves stations
consistent with router geolocation; the 30-km diameter groups the retrieved
stations. Cable lifecycle filtering is applied before region pairs are formed.
''', '用具体功能解释两个空间参数。', '保留所有数值与筛选顺序，使参数的不同角色可直接理解。')
edit(f, 'The corridor is the primary', r'''
The aggregate distribution uses the complete feasible corridor set, with the
corridor as its primary physical unit. Cable candidates and exact landing
pairs remain linked in the outputs. A supplementary ranking uses landing
proximity, propagation consistency, and AS context.
''', '将完整候选集这一主分析步骤提前。', '正面突出研究设计，保持补充排序的地位，不新增最坏情形保证。')
edit(f, 'Thus \\(\\sum', r'''
Thus \(\sum_{c\in\mathcal{C}_s} w_{s,c}=1\): each candidate-bearing segment
contributes equal total observation mass, distributed according to candidate
multiplicity.
''', '用 observation mass 明确 equal influence 的对象。', '直接对应原公式，不把质量分配改写为使用概率。')
edit(f, 'Single- and bounded multi-corridor', r'''
Single- and bounded multi-corridor segments form the physical distribution.
Pipeline accounting retains the other states, and all valid traces form the
exposure denominator.
''', '拆分构成分布与保留分母两个处理动作。', '每句只有一个统计角色，信息完整。')
edit(f, 'This state assignment separates', r'''
Candidate-set size and aggregate concentration describe different levels of
the analysis. A unit may contain many bounded segments yet concentrate after
their uniformly allocated mass repeatedly supports the same corridors.
''', '把已有解释改成观点在前的段落。', '突出单片段多解释与总体集中可以并存，保留 may 的强度。')
edit(f, 'For each probe-country and service group', r'''
For each probe-country and service group, we construct both distributions
from candidate-bearing atomic segments. Counting ordered endpoint-AS labels
gives the network-transition probabilities \(p^{N}\). Summing the corridor
masses in Eq.~\eqref{eq:uniform-mass} and normalizing within the group gives
the corridor probabilities \(p^{C}\).
''', '将同总体构造置于段首，删除段末同义复述。', '明确比较基础，保留变量名和公式引用。')
edit(f, 'To be specific,', r'''
For each auditable country--measurement unit \(u\), let \(S_u\) denote the
candidate-bearing atomic segments and \(\ell(s)\) the label assigned to
segment \(s\). Each distinct segment contributes once to an ordered
network-side label at its available mapping resolution. The probability of
label \(t\) is
''', '删除 To be specific 及与前段重复的分布定义，先定义变量。', '公式前置条件更紧凑，变量和计数规则完整保留。')
edit(f, 'Submarine exposure is computed', r'''
Submarine exposure uses complete valid traceroutes. A traceroute is exposed
when at least one segment has a feasible inter-region corridor. Dividing the
exposed-trace count by all valid traces in the country-service unit gives the
exposure rate.
''', '用计算动作说明分子与分母。', '提高可读性，不改 exposure 定义。')
edit(f, 'Top-2 share emphasizes', r'''
The metrics distinguish dominant-corridor mass from the long tail and support
size. Top-2 share emphasizes leading categories, effective count incorporates
the complete probability vector, and normalized entropy measures evenness
relative to observed support.
''', '将联合使用的作用提前，再解释每项作用。', '指标介绍围绕用途组织，保留原有结论强度。')

f = 'files/4-datasets.tex'
edit(f, 'We combine network-path observations', r'''
All inputs are aligned to July~1, 2026 (UTC). Network-path observations,
IP and AS annotations, and cable lifecycle records therefore describe a
common analysis period. We combine these observations with network and
submarine-cable metadata.
''', '先说明时间对齐，再交代资料组合。', '突出测量设计的共同时间基础，原有 therefore 关系保留。')
edit(f, 'Our network observations comprise', r'''
Our network observations comprise 18 public RIPE Atlas IPv4 traceroute
measurements collected from 00:00 to 01:00 UTC. Thirteen measurements cover
independently operated anycast DNS Root services. Wikipedia, Reddit, and
\texttt{assets.nflxext.com} provide three application-facing observations.
Measurements 5051 and 5151 use dynamic targets as multi-target UDP and ICMP
topology references. Table~\ref{tab:atlas_measurements} summarizes the corpus
after canonical trace-identity deduplication.
''', '平行组织三类测量，消除重复 provide 表述。', '保持全部测量对象、协议、ID 和时间范围。')
edit(f, 'Each record retains', r'''
Each record retains the destination address returned by RIPE Atlas. This
preserves the multi-target structure of the two dynamic-target measurements
and the destination instances selected by service measurements during the
aligned window.
''', '将两种保留行为合并为一个平行句。', '突出原始目的地址保留的作用，不增加实例识别步骤。')
edit(f, 'Table~\\ref{tab:supporting_datasets}', r'''
Table~\ref{tab:supporting_datasets} lists the supporting datasets and versions.
RIPE Atlas probe metadata supplies the probe country and source-network
context~\cite{ripe_atlas}. IPinfo Location and ASN databases annotate visible
hops with geographic and AS information~\cite{ipinfo}.

The Submarine Cable Map provides the cable and landing-point inventory,
including lifecycle and organizational fields
~\cite{telegeography_submarine_map}. The analysis includes systems in service
on the measurement date. CAIDA AS Relationships and the derived owner-AS
associations supply supplementary ranking context
~\cite{caida_as_relationships}. A versioned country taxonomy classifies probe
countries as island or archipelagic, landlocked, or other coastal.
''', '按路径注释数据与基础设施及分析元数据拆段。', '资料与方法作用对应更清楚，引文顺序不变。')

# Results keep float order and all original numeric observations.
f = 'files/5-result.tex'
edit(f, 'We organize the results around', r'''
The results compare network and corridor distributions built from the same
segments and examine how their relationship varies across services and
countries. Exposure measures how often a path enters the feasible inter-region
corridor space. Conditional breadth measures how candidate-bearing
observations are distributed within that space. We first establish these two
properties, then examine their geographic variation and the paired cross-layer
distributions.
''', '结果节开头先提出跨层主问题，再说明保留的结果展开顺序。', '在不改变图表编号的情况下突出主线，读者知道 exposure 的铺垫作用。')
edit(f, 'The processing pipeline begins', r'''
The processing pipeline retains 490,911 valid traceroutes from 707,314 raw
records, yielding 3,291,063 atomic segments. Of the 2,432,559 mappable
segments, 555,119 reach candidate landing points, 171,232 satisfy the corridor
constraints, and 124,350 support inter-region corridors. The final set contains
71,990 single-corridor segments and 52,360 bounded multi-corridor segments.
Under the unit-mass aggregation rule, they form 370 auditable
country-measurement units.
''', '先给有效测量总体，再按处理步骤交代数量。', '保持所有计数与顺序关系，便于核对方法到结果的衔接。')
edit(f, 'The DNS family contains', r'''
DNS exposure has a pronounced upper tail: inter-region candidates appear
infrequently for most countries and recur in a smaller group. The DNS family
contains 945 country-measurement units with at least 30 valid traceroutes,
covering 77 countries. Pooling eligible Root observations within each country
by valid-trace count yields a median exposure of 5.50\% (IQR:
1.10\%-23.04\%; mean: 17.80\%). The difference between the median and mean
reveals this uneven distribution across countries.
''', '将原有分布判断提前，再给样本、聚合规则和统计量。', '核心发现先行，全部强度与数值保留。')
edit(f, 'The three application measurements occupy', r'''
The three application measurements occupy the same low-exposure range.
Median country-measurement exposure is 1.90\% for Wikipedia, 1.96\% for
Reddit, and 1.43\% for Netflix Assets. The multi-target topology references
reach 23.24\% for MSM~5051 and 23.81\% for MSM~5151. Figure
~\ref{fig:result-overview} compares the complete country distributions and
shows this separation.
''', '按测量组平行报告，图引用直接对应比较。', '保留既有分离结论，不添加显著性判断。')
edit(f, 'Country-matched comparisons preserve', r'''
Country-matched comparisons show lower DNS exposure while preserving source
geography and changing the target population. DNS exposure is lower than
MSM~5051 in 70 of 77 shared countries, with a median paired difference of
\(-14.52\) percentage points. It is lower than MSM~5151 in 54 of 59 shared
countries, with a median difference of \(-14.82\) points. The paired direction
holds for 90.9\% and 91.5\% of the shared countries, respectively.

The two protocols therefore reveal the same family ordering: service-facing
targets expose a smaller inter-region path population than the dynamic
multi-target measurements observed from the same countries.
''', '先说明配对比较结果，将数据证据与总体解释分段。', '读者可核对 shared countries 与百分比，原 therefore 推论完整保留。')
edit(f, 'Corridor breadth is measured', r'''
We measure corridor breadth over 222 DNS Root, 53 application, and 95
topology-reference units. Every unit meets the audit thresholds in
Section~\ref{sec:framework_path_segmentation}. Its network and corridor
distributions contain the same candidate-bearing segments. Table
~\ref{tab:family-summary} reports the median concentration and breadth of
each family.
''', '将样本、资格和两层对齐拆成独立句。', '使表格分母及比较基础明确。')
edit(f, 'DNS Roots and applications have median', r'''
DNS Roots and applications occupy narrower corridor spaces than the topology
references. Their median corridor Top-2 shares are 72.0\% and 70.3\%,
compared with 30.6\% for topology references; their effective corridor counts
are 3.84 and 3.51, compared with 18.01. The topology-reference median thus
contains 4.7 times as many effective corridors as DNS and 5.1 times as many as
the applications. Its Top-2 share is 41.4 percentage points below DNS and
39.7 points below the applications.
''', '以原有组间比较作主题句，将两项指标按相同组别顺序报告。', '减少指代追踪，全部比值和差值原样保留。')
edit(f, 'The high-concentration tail follows', r'''
The high-concentration tail follows the same family ordering. The leading two
corridors receive at least 80\% of mass in 83 of 222 DNS units (37.4\%),
16 of 53 application units (30.2\%), and 4 of 95 topology-reference units
(4.2\%). These threshold counts and the family medians describe the
separation at the upper end and center of the concentration distributions,
respectively.
''', '明确阈值计数与中位数分别对应尾部和中心。', '消除泛化复述，保留同一排序判断。')
edit(f, 'The three applications also share', r'''
The three applications reach similar absolute corridor breadth through
different amounts of redistribution from their network-transition
distributions. Wikipedia, Reddit, and Netflix Assets have median corridor
Top-2 shares of 68.3\%, 71.0\%, and 71.6\%, with 4.25, 3.25, and 3.47
effective corridors. Their median Top-2 shifts are 11.0, 25.6, and 23.6
percentage points, respectively. Together, these measurements describe their
shared narrow physical footprint and different cross-layer shifts.
''', '将原段末解释置于段首，数据按相同对象顺序承接。', '突出相近最终宽度与不同变化幅度的区别，保留原结论。')
edit(f, 'Figure~\\ref{fig:corridor-breadth}', r'''
Figure~\ref{fig:corridor-breadth} shows that the family separation extends
across the distributions. The service-facing ECDFs occupy the
higher-concentration range, and their effective-count distributions remain
centered on three to four equally weighted corridors. Top-2 share captures
mass in the dominant directions, while effective count captures breadth across
the full support. Both metrics yield the same family ordering.
''', '将图中观察和指标含义逐句对应。', '读者能用图验证排序，未增加统计检验结论。')
edit(f, 'Normalized entropy adds', r'''
The largest family difference remains the absolute physical breadth reached
after projection. Normalized entropy provides a support-relative view:
median entropy reduction is 0.126 for DNS Roots, 0.164 for applications, and
0.081 for topology references. Service-facing paths repeatedly occupy a
smaller feasible-corridor space, while the multi-target references distribute
observations over many more coastal directions.
''', '提前原有主判断，再介绍辅助指标。', '避免三种指标并列堆叠，保持原有差异解释。')
edit(f, 'Following Liu et al.', r'''
We compare geography at the country level, giving equal weight to countries
represented by different numbers of Root measurements. Following Liu et
al.~\cite{liu2020outofsight}, probe countries are grouped as island or
archipelagic, landlocked, and other coastal. Each country contributes one
pooled DNS exposure observation and the median corridor distribution over its
auditable DNS units.
''', '先说明地理比较的统计单位和权重，再介绍分组及汇总。', '使这一节与国家—测量单位的区别清楚，引文位置顺序不变。')
edit(f, 'Island and archipelagic countries form', r'''
Island and archipelagic countries form the highest-exposure group. Their
median country-pooled DNS exposure is 49.61\% across 9 countries, compared
with 7.88\% for 54 other coastal countries and 1.70\% for 14 landlocked
countries. This ordering describes how frequently observed Root paths enter
an inter-region candidate space.
''', '用 describes 明确排序对应的指标含义。', '保持组别、样本量和原有判断。')
edit(f, 'Conditional corridor breadth follows', r'''
Conditional corridor breadth follows a different ordering. Island and
archipelagic countries have a median Top-2 corridor share of 53.3\% and
5.58 effective corridors. Other coastal countries reach 75.4\% and 3.39.
The two represented landlocked countries reach 80.2\% and 2.51. Figure
~\ref{fig:country-geography} presents both distributions together with the
contributing country counts.
''', '将图的作用写成同时报告分布和样本量。', '保留小样本事实及原有比较，不扩大地理范围。')
edit(f, 'Across the 38 countries', r'''
Across the 38 countries with both pooled exposure and an auditable corridor
summary, more frequent entry into the candidate space tends to accompany
broader conditional support. Exposure and corridor Top-2 share have a
Spearman rank association of \(-0.29\); exposure and effective corridor count
have the corresponding association of 0.30. The country-level ordering thus
follows the geographic group result.
''', '把原有 tends to accompany 判断放到统计量之前。', '保留相关性和趋向语气，没有替换成因果或显著相关。')
edit(f, 'Geography therefore separates', r'''
Geography therefore separates exposure from conditional corridor breadth.
Island and archipelagic countries enter the candidate space more frequently,
yet their candidate-bearing observations span more coastal directions. Other
coastal countries enter less frequently and concentrate more strongly once
exposure occurs. Exposure records the frequency of submarine involvement;
corridor breadth describes the physical directions supporting that
involvement.
''', '用本节实际比较指标替换泛指的 two physical properties。', '段落回扣同一中心，保留 therefore 及组间判断。')
edit(f, 'Figure~\\ref{fig:cross-layer}', r'''
DNS and application units shift upward more strongly than topology references
in the paired network-transition and corridor Top-2 comparison. Figure
~\ref{fig:cross-layer} shows all 370 auditable units. The common 80\% lines
organize the distributions into four descriptive classes, and the diagonal
separates increases in corridor concentration from decreases.
''', '先呈现图中主要观察，再解释图的坐标和分类线。', '图服务于论点，保留四象限和全部数字。')
edit(f, 'Among 275 service-facing units', r'''
Contraction is a recurring service-facing pattern, while broad support at
both layers remains the largest service-facing class. Among 275
service-facing units, 81 (29.5\%) are network-broad/corridor-concentrated,
158 (57.5\%) remain broad at both layers, 18 (6.5\%) are concentrated at
both, and 18 (6.5\%) are network-concentrated/corridor-broad. Four of 95
topology-reference units (4.2\%) enter the contraction class; the other 91
remain broad at both layers.
''', '提前原段结论，再完整列出四类构成。', '收缩与异质性并列呈现，保留原判断强度和所有类别。')
edit(f, 'DNS and applications enter', r'''
DNS and applications enter the contraction class at similar rates but show
different median continuous shifts. The class contains 66 of 222 DNS units
(29.7\%) and 15 of 53 application units (28.3\%). Their median continuous
Top-2 shifts are 11.0 and 21.0 percentage points, respectively. Application
units cross the 80\% boundary at a similar frequency and redistribute more
mass toward their two leading corridors. Continuous shifts also reveal
substantial narrowing within the broad-broad class.
''', '将发生频率与变化幅度的比较合并为主题句。', '显示连续指标与阈值分类的互补价值，原 substantial 判断保留。')
edit(f, 'Across the service-facing population', r'''
Continuous metrics identify redistribution toward fewer leading physical
directions both within and across the threshold classes. Across the
service-facing population, corridor Top-2 share increases in 184 of 275
units (66.9\%), and effective category count contracts in 204 (74.2\%). Of
the 239 units with a broad network distribution, 178 (74.5\%) move upward
in Top-2 share: 81 cross the concentration threshold, while 97 remain broad
at both layers with a median increase of 6.3 percentage points.
''', '将原段末对阈值与连续指标关系的解释移至段首。', '避免把 80% 当作唯一发现，全部数值与对象保留。')
edit(f, 'Three cases illustrate', r'''
Three cases distinguish continuous narrowing, expansion, and changes in
absolute breadth from support-relative evenness.
\textbf{Singapore-Netflix} moves from 32.5\% network Top-2 share to 65.0\%
corridor Top-2 share, while its effective count contracts from 19.86 to
3.41. It exhibits strong continuous narrowing while remaining below the
80\% boundary.

\textbf{New Zealand-Netflix} shows corridor expansion. Its share moves
from 63.6\% to 37.6\%, with effective count expanding from 5.18 to 6.92.

\textbf{Singapore-H-Root} separates absolute breadth from support-relative
evenness. Its share moves from 39.6\% to 50.1\%, and its effective
count contracts from 20.67 to 5.99, while normalized entropy changes only
slightly.
''', '三个案例各成一段，每段先点明所说明的性质。', '读者不必在一个长段中切换三种解释，原数字和 strong、only slightly 保留。')
edit(f, 'Bounded multi-corridor segments account', r'''
Repeated overlap among bounded multi-corridor sets produces the aggregate
distributions in these cases. Bounded multi-corridor segments account for
99.9\% of candidate-bearing observations in Singapore-Netflix, 78.1\% in
New Zealand-Netflix, and 98.2\% in Singapore-H-Root. Under the same
projection and aggregation rules, the cases show contraction, expansion,
and metric-specific change.
''', '将原有候选重叠解释提前，使多候选比例成为解释的证据。', '突出核心叙事；不把已有 produces 进一步升级为经过独立机制验证。')
edit(f, 'Taken together, the four analyses', r'''
Service-facing measurements enter the inter-region candidate space less often
and occupy narrower corridor distributions than the topology references.
Within the service-facing population, country-service units span contraction,
preservation, and expansion. Network diversity and physical-corridor diversity
therefore describe distinct properties of application reachability.
''', '删除 Taken together 与 consistent cross-layer structure 的重复引导。', '保留结果总结的实际内容，减少结论复述。')

f = 'files/6-measurement-scope-and-implications.tex'
edit(f, 'Routing diversity and corridor breadth', r'''
Routing diversity and corridor breadth capture distinct structures relevant
to replica placement, peering, and international connectivity planning. In the
service-facing population, 81 units project broad network alternatives onto
narrow feasible coastal directions, whereas 158 retain distributed support
at both layers. Exposure links service localization and interconnection to
the frequency of inter-region access; concentration links landing-region
diversification to the breadth of physical support. Together, they locate
the country-service populations associated with these structures.
''', '将原段的规划相关性与核心结构合并为主题句，再给证据。', '讨论从已有结果展开，不引入新收益或新干预结果。')
edit(f, 'The paired view also distinguishes', r'''
The paired view distinguishes two intervention points. Deploying a closer
service instance or changing interconnection can reduce exposure by keeping
more paths within a region. Adding access through distinct landing regions
can broaden the corridor distribution of paths that continue to cross regions.
''', '删除 also，保留原两项干预判断。', '让每个动作与结果对应，can 强度不变；证据问题另列，不代改判断。')
edit(f, 'Each segment records one', r'''
The mapping-resolution states retain both single-corridor and bounded
multi-corridor observations. Each segment records one state. At 30~km,
57.9\% of candidate-bearing segments have one corridor and 42.1\% divide
unit mass across a bounded set. Segments with no feasible corridor or
incomplete construction inputs remain separate in pipeline accounting.
Corridor, exact landing-pair, and cable identities remain linked in the
outputs, supporting analysis across physical resolutions.
''', '先交代状态分类保留的两种观测，再说明比例与记录方式。', '以正面方法描述组织范围信息，原有其他状态保留。')
edit(f, 'Uniform allocation gives', r'''
Aggregate concentration combines observation frequency with candidate
overlap. Uniform allocation gives each observed segment one total unit of
influence. Repeated support for the same corridor accumulates across traces,
while segments with several feasible corridors distribute their unit across
that finite set.
''', '将已有聚合性质置于段首，再解释形成过程。', '突出候选重叠主线，不新增模型性质。')
edit(f, 'RIPE Atlas probe density varies', r'''
Reported quantities are observation-weighted over participating probes in the
aligned window; RIPE Atlas probe density varies across countries and
networks. DNS Roots and applications form service-specific populations,
while MSM 5051 and 5151 retain dynamic multi-target populations as topology
references. Anycast observations integrate deployed footprint, BGP selection,
interconnection, and source-network context.
''', '先明确统计量如何构成，再交代覆盖与组别。', '范围信息成为测量定义的一部分，不作重复免责声明。')
edit(f, 'The primary corridor distribution includes', r'''
The primary corridor distribution includes domestic and international
inter-region candidates, with the corresponding label retained per segment.
All measurements cover 00:00-01:00 UTC on July~1, 2026 and align with IP,
AS, cable-lifecycle, and deployment metadata.

Corridor concentration quantifies geographic candidate support. Cable
multiplicity, landing-station redundancy, hazard correlation, rerouting
capacity, and repair processes supply additional operational dimensions.
''', '将纳入范围与指标含义分段。', '每段围绕一个中心，保留全部原有范围及运营维度。')
edit(f, 'The snapshot provides', r'''
The snapshot provides a common temporal basis across all service families.
Repeating the aligned construction at the same country-measurement
granularity can track changes caused by routing, service deployment, or
cable lifecycle events.
''', '将重复构造的粒度靠近动作，缩短长句。', '保留 can 与 caused by，不声称已做纵向分析。')
edit(f, 'The study uses archived', r'''
The study uses archived public RIPE Atlas measurements and infrastructure
metadata and reports aggregate country-measurement statistics. The released
measurement IDs, configuration values, resolution states, pipeline counts,
and scripts reconstruct the primary tables and figures from versioned inputs.
''', '修整语法并保持完整复现清单。', '不新增复现验证承诺；已知对应问题在位置清单中标出。')

f = 'files/7-conclusion.tex'
edit(f, 'We presented an application-aware', r'''
We presented an application-aware cross-layer audit that compares network
transitions and feasible submarine corridors over identical segment
populations. The framework applies geographic, lifecycle, and propagation
feasibility to atomic traceroute segments and distributes each segment's
observation mass uniformly across its feasible corridors.
''', '结论先总结比较对象及配对设计，再简述构造方法。', '回扣全文主问题，保留全部约束与均分步骤。')
edit(f, 'Across 490,911 valid traceroutes', r'''
Across 490,911 valid traceroutes, the 30-km analysis identifies 124,350
inter-region candidate-bearing segments and 370 auditable
country-measurement units. DNS Roots and applications have median effective
corridor counts of 3.84 and 3.51, compared with 18.01 for the multi-target
topology references. Under the descriptive Top-2 threshold, 81 of 275
service-facing units exhibit network-broad/corridor-concentrated structure,
compared with 4 of 95 topology-reference units; 158 service-facing units
remain broad at both layers.

These measurements show that application reachability frequently occupies a
narrower feasible physical-corridor space than its network-transition
representation, with substantial variation across countries and services.
''', '将量化结果与最终结论分段。', '结尾保留原有 frequently 与 substantial，不扩写新的运营效果。')

(ROOT/'editorial/changes.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Applied {len(changes)} paragraph-level revisions.')
