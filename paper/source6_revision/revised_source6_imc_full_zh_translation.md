# When Does Network Diversity Reflect Physical Diversity?

网络层多样性何时能够反映物理多样性？

## A Cross-Layer Audit of Internet Service Paths

互联网服务路径的跨层审计

Anonymous Author(s) / 匿名作者

本文件与当前 LaTeX 正文逐段对应，每段先列英文原文，再列中文翻译。图表及图表标题省略；公式、正文中的图表引用和引文编号保留。参考文献保留原书目信息。

## Abstract / 摘要

**原文 P001**

Network-layer path diversity is often used as a proxy for the physical diversity supporting Internet services. We present CLASP, a Cross-Layer Audit of Service Paths that compares network-transition and feasible landing-region-corridor distributions over the same traceroute segments. We apply CLASP to 490,911 valid IPv4 traceroutes from 18 public RIPE Atlas measurements covering all 13 DNS Roots, three applications, and two dynamic multi-target topology references, yielding 370 auditable country–measurement units. Under equal-share allocation, 81 of 275 service-facing units have broad network support and concentrated corridor support, while 158 remain broad at both layers; effective category count contracts in 204 units (74.2%). Across units, the Spearman association between network and corridor concentration, termed Layer Agreement, varies by geography. Under projection-score weighting it is 0.632 for 67 island and archipelagic units and 0.001 for 202 coastal-mainland units. The island–coastal difference remains positive under equal-share, projection-score, and Top-1 allocation, at 0.461, 0.631, and 0.715. These results show why auditing physical-corridor diversity requires both measuring within-unit cross-layer differences and examining how concentration rankings correspond across geographic populations.

**译文**

网络层路径多样性经常被用作支撑互联网服务的物理多样性的代理指标。本文提出 CLASP，即服务路径跨层审计（Cross-Layer Audit of Service Paths），在相同的 traceroute 线段上比较网络转换分布与可行登陆区域走廊分布。我们将 CLASP 应用于来自 18 项公开 RIPE Atlas 测量的 490,911 条有效 IPv4 traceroute，覆盖全部 13 个 DNS 根服务、3 个应用和 2 个动态多目标拓扑参考测量，得到 370 个可审计的“国家—测量”单元。在均匀分配下，275 个面向服务单元中有 81 个具有宽广网络支撑和集中走廊支撑，158 个在两个层面都保持宽广；204 个单元（74.2%）的有效类别数收缩。在单元之间，网络集中度与走廊集中度之间的 Spearman 关联——称为 Layer Agreement——随地理分组而变化。投影分数加权下，该关联在 67 个岛屿与群岛单元中为 0.632，在 202 个沿海大陆单元中为 0.001。在均匀分配、投影分数加权和 Top-1 分配下，岛屿与沿海大陆的差值始终为正，分别为 0.461、0.631 和 0.715。这些结果说明，物理走廊多样性审计需要同时测量单元内部的跨层差异，并检查不同地理总体中集中度排序之间的对应关系。

**Keywords / 关键词**

Internet measurement, submarine cables, traceroute, cross-layer analysis, anycast, path diversity

互联网测量、海底光缆、traceroute、跨层分析、anycast、路径多样性

## 1 Introduction / 引言

**原文 P002**

Submarine cables form the physical backbone of the global Internet and carry nearly all intercontinental traffic [1]. For users accessing services across oceans, these cables provide the physical connections underlying end-to-end network paths. Traceroute exposes the network-layer structure of these paths through visible routers and Autonomous System (AS) transitions between sources and service destinations.

**译文**

海底光缆构成全球互联网的物理骨干，并承载几乎全部洲际流量 [1]。对于跨洋访问服务的用户，这些光缆提供了端到端网络路径所依托的物理连接。Traceroute 通过源端与服务目的地之间的可见路由器和自治系统（Autonomous System，AS）转换，呈现这些路径的网络层结构。

**原文 P003**

Failures in this physical infrastructure can isolate regions, degrade remote-service access, and redirect traffic toward longer or congested alternatives. Paths traversing different routers or ASes may nevertheless share a cable or coastal corridor and be affected by the same physical event. Such shared dependencies are not directly visible in traceroute: a service may present many distinct network transitions while its feasible physical support remains concentrated in a few coastal directions. Assessing service-path diversity therefore requires comparing how observations are distributed across network transitions and feasible physical corridors.

**译文**

这些物理基础设施发生故障，可能使地区与外界隔离，降低远程服务的访问质量，并使流量改道至更长或更拥塞的替代路径。经过不同路由器或 AS 的路径仍可能共用同一条光缆或沿海走廊，并受到同一物理事件的影响。这种共享依赖无法直接从 traceroute 中看出：一项服务可能呈现许多不同的网络转换，而其可行物理支撑仍集中在少数沿海方向。因此，评估服务路径多样性，需要比较观测在网络转换与可行物理走廊之间分别如何分布。

**原文 P004**

Cross-layer mapping provides a starting point for this comparison. Internet Atlas, InterTubes, and iGDB connect observed Internet links to long-haul infrastructure; Nautilus associates IP links with candidate submarine cables; Calypso maps routes using cable layouts, network relationships, and inland connectivity; and Xaminer uses cross-layer maps to analyze infrastructure risk [2], [3], [4], [5], [6], [7]. These studies make physical dependencies accessible to measurement and analysis. Building on this capability, we ask whether the diversity visible in a population of service paths reflects how its feasible physical support is distributed.

**译文**

跨层映射为这一比较提供了起点。Internet Atlas、InterTubes 和 iGDB 将观测到的互联网链路与长途基础设施联系起来；Nautilus 将 IP 链路与候选海底光缆相关联；Calypso 使用光缆布局、网络关系和内陆连通性映射路由；Xaminer 则使用跨层地图分析基础设施风险 [2]–[7]。这些研究使物理依赖能够被测量和分析。在这一能力的基础上，本文研究一个服务路径总体中可见的多样性，是否反映其可行物理支撑的分布。

**原文 P005**

Answering this question requires more than counting distinct network transitions or feasible corridors. Different transitions may repeatedly support the same corridors, while a recurring transition may admit several physical candidates. Counts alone do not describe how observations are distributed among those categories. Comparing the two layers therefore requires retaining each segment's network identity and physical candidate set, and aggregating both over the same service-path population.

**译文**

回答这一问题，仅统计不同网络转换或可行走廊的数量还不够。不同转换可能反复支持相同的走廊，而反复出现的同一种转换也可能对应多个物理候选。仅凭数量无法描述观测在这些类别之间如何分布。因此，比较两个层次需要保留每个线段的网络身份和物理候选集合，并在同一个服务路径总体上分别聚合。

**原文 P006**

We present CLASP, a Cross-Layer Audit of Service Paths, to construct this paired comparison. CLASP extracts atomic segments from traceroutes, records their network-transition labels, and identifies feasible landing-region corridors using geographic, cable-lifecycle, and propagation constraints. Each candidate-bearing segment contributes the same total observation mass to both layers; candidate allocation distributes its physical-layer mass among feasible corridors. Aggregating by country and measurement then produces paired distributions while preserving the source-country and measured-target context. This construction compares the organization of a fixed set of observations rather than distributions drawn from different path populations.

**译文**

本文提出 CLASP，即服务路径跨层审计（Cross-Layer Audit of Service Paths），构建这种配对比较。CLASP 从 traceroute 中抽取原子段，记录其网络转换标签，并利用地理、光缆生命周期和传播约束识别可行登陆区域走廊。每个具有候选的线段向两个层次贡献相同的观测权重总量；候选分配规则将其物理层权重分配到可行走廊之间。随后按国家和测量进行聚合，在保留源国家和测量目标背景的同时生成配对分布。这一构造比较的是同一组观测的组织方式，而不是来自不同路径总体的分布。

**原文 P007**

The paired distributions support two complementary analyses. Within a country–measurement unit, we measure changes in concentration and breadth between network transitions and feasible corridors. Across units, we measure whether network concentration preserves the ordering of corridor concentration, using Spearman rank correlation, termed Layer Agreement. These analyses address RQ1, how diversity differs within units, and RQ2, how concentration-rank association varies by geography and candidate allocation. RQ3 examines exposure, absolute corridor breadth, and measurement-family composition as context for these results. Exposure is reported separately because the frequency of encountering a feasible corridor and the distribution of support among corridors describe different properties.

**译文**

配对分布支持两类互补分析。在单个“国家—测量”单元内，本文测量网络转换与可行走廊之间集中度和宽度的变化。在多个单元之间，本文使用 Spearman 秩相关测量网络集中度是否保留走廊集中度的排序，并将这一关联称为 Layer Agreement。这两类分析分别回答 RQ1：单元内的多样性如何不同，以及 RQ2：集中度的秩关联如何随地理分组和候选分配方式变化。RQ3 考察暴露率、绝对走廊宽度及测量家族构成，为上述结果提供背景。暴露率单独报告，因为遇到可行走廊的频率与支撑在走廊之间的分布描述的是不同属性。

**原文 P008**

We apply CLASP to 490,911 valid IPv4 traceroutes from 18 public RIPE Atlas measurements covering all 13 DNS Roots, Wikipedia, Reddit, Netflix Assets, and two dynamic multi-target topology references. The aligned one-hour snapshot yields 370 auditable country–measurement units. The service measurements retain their selected targets, while the multi-target measurements provide a broader-target reference. Equal-share, projection-score, and Top-1 allocation compare how the results depend on distributing observation mass among feasible candidates.

**译文**

本文将 CLASP 应用于来自 18 项公开 RIPE Atlas 测量的 490,911 条有效 IPv4 traceroute，覆盖全部 13 个 DNS 根服务、Wikipedia、Reddit、Netflix Assets，以及两项动态多目标拓扑参考测量。对齐的一小时快照得到 370 个可审计的“国家—测量”单元。服务测量保留各自选定的目标，多目标测量则提供目标范围更广的参考。均匀分配、投影分数加权和 Top-1 分配用于比较：观测权重在可行候选之间的分配方式如何影响结果。

**原文 P009**

The audit identifies service-facing populations whose broad network support accompanies concentrated corridor support, as well as narrowing within populations classified as broad at both layers. Across geographic groups, concentration rankings track more closely among island and archipelagic units than among coastal-mainland units under all three allocation rules. The two findings describe different aspects of the cross-layer relationship: aligned rankings can coexist with within-unit narrowing. Together, they motivate examining physical-corridor distributions alongside network-layer summaries when characterizing service-path diversity.

**译文**

审计识别出网络支撑宽广但走廊支撑集中的面向服务总体，也识别出两个层次均被归类为宽广的总体内部存在的收窄。在地理组之间，三种分配规则下岛屿与群岛单元的集中度排序均比沿海大陆单元更紧密地对应。这两项发现描述跨层关系的不同方面：排序一致可以与单元内部的收窄同时存在。因此，刻画服务路径多样性时，需要结合网络层汇总指标检查物理走廊分布。

**原文 P010**

This paper makes three contributions. First, CLASP constructs paired network-transition and feasible-corridor distributions over identical traceroute segments, separating trace-level exposure from conditional corridor concentration. Second, the audit measures within-unit diversity differences and geographic variation in concentration-rank association, with three candidate-allocation rules providing complementary views of the feasible support. Third, it records measurement IDs, configuration values, mapping states, and pipeline counts so that the reported distributions can be reconstructed and inspected.

**译文**

本文作出三项贡献。第一，CLASP 在完全相同的 traceroute 线段上构建配对的网络转换分布和可行走廊分布，将轨迹层面的暴露率与条件走廊集中度区分开。第二，审计测量单元内部的多样性差异，以及集中度秩关联的地理变化，三种候选分配规则为可行支撑提供互补视角。第三，审计记录测量 ID、配置值、映射状态和流水线计数，使报告的分布能够被重建和检查。

## 2 Background and Related Work / 背景与相关工作

### 2.1 Reading Service Paths at the Network Layer / 从网络层观察服务路径

**原文 P011**

Service paths connect a source network to the instances selected through DNS resolution, replica selection, and routing. Traceroute exposes the visible IP hops along these paths, from which AS transitions can be constructed. Comparing such transitions describes how observations are distributed across network-layer categories. The measurement target and source population remain part of that description: paths toward a selected service and paths toward many changing destinations sample different populations.

**译文**

服务路径通过 DNS 解析、副本选择和路由，将源网络连接到选定的服务实例。Traceroute 显示这些路径上的可见 IP 跳，由此可以构建 AS 转换。比较这些转换，可以描述观测在网络层类别之间的分布。测量目标和源总体仍是这一描述的组成部分：通向选定服务的路径与通向多个不断变化的目标的路径，采样的是不同总体。

**原文 P012**

Prior measurements connect this service perspective to infrastructure. Liu et al. quantify the fraction of popular Web resources reached through the submarine cable network and consider redundancy by weighting criticality using cable and bundle counts [8]. Studies of anycast characterize deployment and network footprints  [9], [10], while other work relates cable infrastructure to AS-level structure [11]. These studies establish complementary views of resource dependence, service deployment, and network organization. Our comparison asks how network-transition diversity corresponds to the distribution of feasible physical support within a measured service-path population.

**译文**

已有测量将这种服务视角与基础设施联系起来。Liu 等人量化热门 Web 资源经由海底光缆网访问的比例，并使用 cable 和 bundle 数量对关键性加权，以考虑冗余 [8]。Anycast 研究刻画部署及其网络足迹 [9]、[10]，另有工作将光缆基础设施与 AS 层结构联系起来 [11]。这些研究分别提供了资源依赖、服务部署和网络组织的互补视角。本文比较的是：在一个被测服务路径总体内，网络转换多样性如何对应可行物理支撑的分布。

**原文 P013**

Physical support is represented here by a landing-region corridor: a direction-independent pair of bounded coastal regions connected by at least one feasible cable candidate. This abstraction lies between exact landing stations, which distinguish nearby facilities, and country-level inventories, which combine separated coastlines. It consolidates nearby candidate systems while retaining distinct coastal entry and exit regions. Different network transitions may support the same corridor, and one transition may admit several corridors. The resulting many-to-many relationship is the basis of the paired comparison; candidate multiplicity records feasible support rather than observed simultaneous use.

**译文**

本文以登陆区域走廊表示物理支撑：它是由至少一条可行光缆候选连接的一对有界沿海区域，并且不区分方向。这一抽象介于精确登陆站与国家层面清单之间：前者区分相邻设施，后者则合并分离的海岸线。走廊抽象合并相邻候选系统，同时保留不同的沿海进入和离开区域。不同网络转换可能支持同一走廊，一种转换也可能对应多个走廊。这种多对多关系构成配对比较的基础；候选的多重性记录可行支撑，而不是已观测到的同时使用。

### 2.2 Mapping Paths onto Submarine Infrastructure / 将路径映射到海底基础设施

**原文 P014**

Event-oriented studies show how submarine infrastructure changes are reflected in observed routing. Bischof et al. characterized Cuba's connectivity before and after ALBA-1 and later formulated the task of connecting Internet observations to the worldwide cable mesh  [12], [13]. Fanou et al. measured routing changes following new cable deployments [14]. For user-facing resources, Liu et al. combine resource discovery, RIPE Atlas traceroutes, geolocation, and propagation feasibility to identify submarine dependence [8]. These approaches link observed paths to the infrastructure on which access may depend.

**译文**

面向事件的研究说明海底基础设施变化如何体现在观测路由中。Bischof 等人刻画了 ALBA-1 建成前后古巴的连接性，随后提出将互联网观测与全球海底光缆网格连接起来的问题 [12]、[13]。Fanou 等人测量新光缆部署后的路由变化 [14]。对于面向用户的资源，Liu 等人结合资源发现、RIPE Atlas traceroute、地理定位和传播可行性识别海缆依赖 [8]。这些方法将观测路径与访问可能依赖的基础设施联系起来。

**原文 P015**

Cross-layer cartography extends this connection through explicit infrastructure mappings. Internet Atlas and InterTubes associate long-haul facilities with observed paths [2], [3], and iGDB integrates facilities, fiber, and network entities into a cross-layer map [4]. Nautilus associates IP links with candidate submarine cables and attaches confidence to each assignment  [5]. Calypso combines cable layouts, network relationships, latency, and inland connectivity to map routes and defines Route Stress over those assignments [6]. Xaminer uses cross-layer maps for disaster-oriented infrastructure analysis  [7]. Measurements of intercontinental links also identify layer-3 links and gateway routers [15].

**译文**

跨层制图通过显式基础设施映射进一步建立这种联系。Internet Atlas 和 InterTubes 将长途设施与观测路径相关联 [2]、[3]，iGDB 将设施、光纤和网络实体整合成跨层地图 [4]。Nautilus 将 IP 链路与候选海底光缆相关联，并为每个关联附加置信度 [5]。Calypso 结合光缆布局、网络关系、时延和内陆连通性映射路由，并在这些关联之上定义 Route Stress [6]。Xaminer 使用跨层地图进行面向灾害的基础设施分析 [7]。洲际链路测量还识别第三层链路和网关路由器 [15]。

**原文 P016**

This body of work supports both infrastructure inference and analyses of dependence or risk. CLASP builds on the projection approach to study a paired distribution question: whether concentration among network transitions corresponds to concentration among feasible coastal corridors over the same observations. The contribution is this comparison, not a claim to recover the exact cable traversed by every path. Keeping feasible candidate sets allows the comparison to retain mapping ambiguity rather than silently treating every assignment as a confirmed traversal.

**译文**

这些工作既支持基础设施推断，也支持依赖或风险分析。CLASP 基于投影方法研究一个配对分布问题：在同一组观测上，网络转换之间的集中度是否对应可行沿海走廊之间的集中度。贡献在于这一比较，而不是声称恢复每条路径实际经过的精确光缆。保留可行候选集合，使比较能够保留映射歧义，而不把每一次关联默认当作已确认的经过关系。

### 2.3 From Mapping to Distribution Measurement / 从映射到分布测量

**原文 P017**

A candidate inventory identifies which physical alternatives are feasible; a distribution describes how repeatedly those alternatives support the observed paths. Two populations can have the same number of feasible corridors yet differ in whether their observation mass is spread across them or concentrated in a few. Likewise, counting network transitions does not reveal whether different transitions repeatedly support the same physical directions. Distribution measurement is needed to distinguish these organizations of support, which an inventory count alone does not describe.

**译文**

候选清单识别哪些物理替代方案可行；分布则描述这些替代方案反复支持观测路径的程度。两个总体可以具有相同数量的可行走廊，但其观测权重可能分散在这些走廊之间，也可能集中于少数走廊。同样，统计网络转换数量并不能说明不同转换是否反复支持相同物理方向。需要通过分布测量区分这些支撑组织方式，而仅凭清单数量无法描述这种区别。

**原文 P018**

The comparison also separates entry into the feasible corridor space from concentration within it. Submarine exposure is the fraction of valid traceroutes containing at least one feasible inter-region corridor. Corridor concentration describes the distribution of observation mass over corridors, conditional on candidate-bearing segments. Frequent exposure can accompany broad or concentrated support; exposure alone does not distinguish them. Reporting these quantities separately preserves their different denominators and avoids interpreting entry frequency as physical breadth.

**译文**

比较还区分进入可行走廊空间的频率与进入后的集中程度。海底暴露率是至少包含一条可行跨区域走廊的有效 traceroute 比例。走廊集中度描述以具有候选的线段为条件时，观测权重在各条走廊上的分布。频繁暴露既可以伴随宽广支撑，也可以伴随集中支撑；仅凭暴露率无法区分二者。分别报告这些量，能够保留不同的分母，避免将进入频率解释为物理宽度。

**原文 P019**

Country and measurement identity define the population for both layers. Source geography and interconnection retain the origin context; the measurement retains the selected destination or target set. DNS Roots provide functionally equivalent services through independent anycast deployments, while the three applications retain their selected targets. The two dynamic multi-target measurements sample a broader destination population and serve as topology references, not matched controls for service deployment. Keeping these identities prevents changes in the target population from being mistaken for a cross-layer difference.

**译文**

国家和测量身份共同定义两个层次的总体。源地理位置和互联关系保留出发侧背景，测量身份则保留选定的目的地或目标集合。DNS 根服务通过独立的 anycast 部署提供功能等价的服务，三个应用则保留各自选定的目标。两项动态多目标测量采样更广的目的地总体，作为拓扑参考，而不是服务部署的匹配对照。保留这些身份，可避免将目标总体的变化误当作跨层差异。

**原文 P020**

CLASP then aligns the observations within each population. Every candidate-bearing atomic segment supplies a network-transition label and a feasible corridor set. Its unit observation mass is counted once in the network distribution and allocated across its physical candidates before aggregation. The paired distributions therefore compare the organization of the same segment population. Section III defines this construction, and Section IV describes the aligned path and infrastructure inputs.

**译文**

随后，CLASP 在每个总体内部对齐观测。每个具有候选的原子段提供一个网络转换标签和一个可行走廊集合。该线段的一单位观测权重在网络分布中计数一次，在物理层则先分配到候选之间，再进行聚合。因此，配对分布比较的是同一线段总体的组织方式。第 III 节定义这一构造，第 IV 节介绍对齐的路径和基础设施输入。

## 3 CLASP: The Paired Cross-Layer Audit / CLASP：配对跨层审计

### 3.1 Overview / 概述

**原文 P021**

CLASP constructs paired network-transition and feasible-corridor distributions for each country–measurement unit. It combines traceroute, probe metadata, IP geolocation and ASN mappings, AS context, and cable metadata. Figure  1 shows the processing order: path extraction creates atomic hop-pair segments, corridor projection constructs each segment's feasible landing-region corridor set, and aggregation forms the two distributions over the same candidate-bearing segments.

**译文**

CLASP 为每一个“国家—测量”单元构建配对的网络转换分布和可行走廊分布。它结合 traceroute、探针元数据、IP 地理位置和 ASN 映射、AS 背景信息以及光缆元数据。图 1 展示了处理顺序：路径抽取产生原子跳对线段，走廊投影构建每条线段的可行登陆区域走廊集合，聚合步骤则在相同的候选承载线段上形成两个分布。

**原文 P022**

The construction keeps trace-level exposure separate from segment-level concentration. Exposure records whether a valid traceroute contains at least one feasible inter-region corridor. The paired distributions condition on candidate-bearing segments and describe how their observation mass is organized. Because these quantities use different denominators, CLASP reports them separately.

**译文**

这一构造将轨迹层面的暴露率与线段层面的集中度分开。暴露率记录一条有效 traceroute 是否至少包含一条可行的跨区域走廊。配对分布以候选承载线段为条件，描述这些线段的观测质量如何组织。由于这两个量使用不同的分母，CLASP 对它们分别报告。

### 3.2 Path Extraction / 路径抽取

**原文 P023**

We group traceroutes by probe country and measured service. This grouping retains the source-side connectivity context and the destination selection observed for each measurement. Hop countries remain segment attributes rather than grouping keys.

**译文**

我们按照探针国家和被测服务对 traceroute 分组。这一分组保留源端连接性背景，以及每项测量中观测到的目的地选择。跳所在的国家作为线段属性保留，而不作为分组键。

**原文 P024**

Each traceroute is normalized into its complete sequence of visible hops with locations, ASNs, and RTTs. Successive visible, geolocated hops form atomic segments. Each segment records endpoint locations, ASNs, countries, hop positions, RTT difference, and bridged-hop count. Repeated hops and RTT samples retain their trace identity and ordering. When timeouts separate two visible hops, the bridged-hop count records the hidden gap for audit accounting.

**译文**

每条 traceroute 被规整为包含位置、ASN 和 RTT 的完整可见跳序列。相邻的可见且具有地理位置的跳构成原子线段。每条线段记录端点位置、ASN、国家、跳序号、RTT 差和跨越的隐藏跳数。重复出现的跳和 RTT 样本保留其轨迹身份与顺序。当两个可见跳之间存在超时时，跨越的隐藏跳数记录这一不可见间隔，以用于审计计数。

**原文 P025**

When both endpoint ASNs are available, their ordered pair forms the segment's network-transition label. A segment missing one endpoint ASN receives an ordered country-pair fallback label, which is strictly coarser. We record the fallback share for each unit. Audit eligibility requires that share to be at most 30%, together with at least 30 candidate-bearing segments, 10 probes, and 3 probe ASNs. These thresholds remove units whose network labels or observation support are too sparse for the paired summaries; they are quality floors rather than guarantees of representativeness.

**译文**

当两个端点的 ASN 都可用时，它们的有序对构成该线段的网络转换标签。缺少一个端点 ASN 的线段使用有序国家对作为后备标签，这种标签严格地更粗。我们记录每个单元的后备标签比例。审计资格要求这一比例不超过 30%，同时至少包含 30 条候选承载线段、10 个探针和 3 个探针 ASN。这些阈值用于移除网络标签或观测支撑过于稀疏的单元；它们只是质量下限，而不是代表性保证。

### 3.3 Feasible Landing-Region Corridors / 可行登陆区域走廊

**原文 P026**

Landing stations and cable lifecycle. For each segment endpoint, CLASP retrieves landing stations within 50 km and pairs them through cable systems in service on July 1, 2026. The catchment allows endpoint locations to be associated with nearby coastal facilities at the resolution of the geolocation input. Explicit cable path or branch information defines direct landing-point adjacency. When the inventory does not provide that information, the pipeline retains reachability at the metadata's topology resolution and records that provenance state rather than presenting it as an observed cable traversal.

**译文**

**登陆站和光缆生命周期。** 对每条线段的每一个端点，CLASP 检索 50 km 范围内的登陆站，并通过在 2026 年 7 月 1 日处于服务状态的光缆系统对这些登陆站进行配对。该捕获半径允许在线路定位输入的分辨率下，将端点位置与附近的沿海设施关联。明确的光缆路径或分支信息用于定义直接的登陆点邻接关系。当清单不提供这类信息时，流水线按照元数据自身提供的拓扑分辨率保留可达性，并记录这一来源状态，而不把它描述为已观测到的光缆穿越。

**原文 P027**

Landing regions. Landing stations are grouped into regions with maximum pairwise distance 30 km. The diameter merges nearby facilities serving the same coastal direction while retaining separated coastal entry and exit patterns. A landing-region corridor is a direction-independent pair of regions connected by at least one feasible cable candidate. Several cable systems and exact landing pairs may support one corridor. Exact landing-pair, cable, and corridor identities remain linked in the outputs so that the aggregation can be audited at each resolution.

**译文**

**登陆区域。** 登陆站被归并为最大两两距离为 30 km 的区域。该直径将服务于同一沿海方向的相邻设施合并，同时保留彼此分离的沿海进入和离开模式。**登陆区域走廊**是由至少一条可行光缆候选连接的一对区域，并且不区分方向。多条光缆系统和多个精确登陆点对可以支撑同一条走廊。精确登陆点对、光缆和走廊的身份在输出中保持关联，因此可以在每一种分辨率下审计聚合过程。

**原文 P028**

Propagation feasibility. A candidate must satisfy geographic, lifecycle, and propagation constraints. Let $D$ be the great-circle distance between its landing points, $v_f=200$ km/ms the configured effective propagation speed in fiber, $\Delta RTT$ the segment's RTT difference, and $\tau=5$ ms the RTT tolerance. The candidate is propagation-feasible when

**译文**

**传播可行性。** 一个候选必须同时满足地理、生命周期和传播约束。令 D 为候选登陆点之间的大圆距离，v_f = 200 km/ms 为配置的光纤有效传播速度，ΔRTT 为该线段的 RTT 差，τ = 5 ms 为 RTT 容差。当满足式（1）时，该候选在传播上可行：

**原文 P029**

$$
\Delta RTT + \tau \geq \frac{2D}{v_f}.
\tag{1}
$$

**译文**

$$
\Delta RTT + \tau \geq \frac{2D}{v_f}.
\tag{1}
$$

**原文 P030**

The inequality asks whether the observed round-trip increment can accommodate the minimum round-trip propagation time between the landing points. When $\Delta RTT$ is non-positive or inconclusive, CLASP retains the geographic and lifecycle constraints and flags the segment. The 200 km/ms speed and 5 ms tolerance are fixed configuration values in the reported analysis.

**译文**

该不等式检验观测到的往返时延增量能否容纳两个登陆点之间的最小往返传播时间。当 ΔRTT 为非正值或无法判定时，CLASP 保留地理约束和生命周期约束，并对该线段作出标记。200 km/ms 的速度和 5 ms 的容差是所报告分析中的固定配置值。

### 3.4 Candidate Allocation and Observation Mass / 候选分配与观测质量

**原文 P031**

Duplicate cable rows belonging to the same corridor are collapsed within an atomic segment. For a segment $s$ with feasible corridor set $\mathcal{C}_s$, the primary analysis allocates its observation mass using the projection score:

**译文**

在每条原子线段内部，属于同一走廊的重复光缆记录会被合并。对于可行走廊集合为 C_s 的线段 s，主分析使用投影分数分配其观测质量：

**原文 P032**

$$
w_{s,c}= \frac{\sigma_{s,c}} {\sum_{c'\in\mathcal{C}_s}\sigma_{s,c'}}, \qquad \sum_{c\in\mathcal{C}_s}w_{s,c}=1,
\tag{2}
$$

**译文**

$$
w_{s,c}= \frac{\sigma_{s,c}} {\sum_{c'\in\mathcal{C}_s}\sigma_{s,c'}}, \qquad \sum_{c\in\mathcal{C}_s}w_{s,c}=1,
\tag{2}
$$

**原文 P033**

where $\sigma_{s,c}$ sums the evidence-support scores of the cable candidates assigned to corridor $c$. The implementation forms each candidate score as the product of landing-proximity support, AS-economic support, RTT support, and a latency penalty. Landing-proximity support decreases with the distances from the two hop endpoints to their candidate landing points. AS-economic support uses endpoint-AS membership in cable-owner AS sets and relationships or owner-group reachability in the AS graph. RTT support compares the observed increment with the propagation lower bound and applies a penalty to highly inflated short-path increments; inconclusive increments receive neutral RTT factors. The candidate scores are summed by corridor and normalized as in Eq. (2), so every candidate-bearing segment contributes one unit of mass.

**译文**

其中，σ_{s,c} 对分配到走廊 c 的光缆候选证据支持分数求和。实现将每个候选分数计算为登陆点邻近支持度、AS-economic 支持度、RTT 支持度与时延惩罚因子的乘积。登陆点邻近支持度随两个跳端点到相应候选登陆点的距离增大而降低。AS-economic 支持度使用端点 AS 是否属于光缆所有者 AS 集合，以及 AS 图中的关系或所有者组可达性。RTT 支持度比较观测增量与传播下界，并对短路径中高度膨胀的增量施加惩罚；无法判定的增量使用中性的 RTT 因子。候选分数按走廊求和，再按照式（2）归一化，因此每条候选承载线段贡献一个单位的质量。

**原文 P034**

Projection-score weighting retains the relative evidence used to rank feasible candidates and is the primary allocation for Layer Agreement. These weights express relative support within a candidate set. Endpoint-AS information contributes both to network-transition labels and to candidate ranking, which makes the equal-share comparison particularly useful: equal sharing assigns $w_{s,c}=1/|\mathcal{C}_s|$ to each feasible corridor without using the score magnitudes. Top-1 allocation places all mass on the highest-scoring corridor. Together, the three rules compare equal support, graded support, and a single preferred candidate over the feasible sets.

**译文**

投影分数加权保留对可行候选进行排序所用的相对证据，是 Layer Agreement 的主要分配口径。这些权重表达候选集合内部的相对支持度。端点 AS 信息同时参与网络转换标签构造和候选排序，因此均匀分配比较尤其有用：均匀分配向每个可行走廊赋予 w_{s,c}=1/|C_s|，不使用分数大小。Top-1 分配把全部质量放到得分最高的走廊。三种规则共同比较可行集合上的等量支持、分级支持和单个首选候选。

### 3.5 Mapping Resolution and Pipeline Accounting / 映射分辨率与流水线计数

**原文 P035**

Table I classifies each segment by input coverage and the size of its feasible corridor set. Single-and bounded multi-corridor segments form the physical distribution. Segments with no feasible corridor or insufficient inputs remain in pipeline accounting, and every valid traceroute remains in the exposure denominator.

**译文**

表 1 根据输入覆盖情况和可行走廊集合大小，对每条线段进行分类。单走廊线段和有界多走廊线段构成物理分布。没有可行走廊或输入不足的线段仍保留在流水线计数中，每一条有效 traceroute 仍保留在暴露率分母中。

**原文 P036**

Candidate-set size and aggregate concentration describe different levels. A unit may contain many bounded multi-corridor segments yet concentrate after their allocated mass repeatedly supports the same corridors. CLASP therefore retains the resolution state instead of using candidate multiplicity as a substitute for distribution breadth.

**译文**

候选集合大小与聚合集中度描述分析的不同层次。一个单元可能包含许多有界多走廊线段，但如果分配后的质量反复支持同一批走廊，聚合后仍会表现为集中。因此，CLASP 保留分辨率状态，而不使用候选数量代替分布宽度。

### 3.6 Paired Distributions / 配对分布

**原文 P037**

For an auditable country–measurement unit $u$, let $S_u$ denote its candidate-bearing atomic segments and $\ell(s)$ the ordered network label of segment $s$. The network-transition probability of label $t$ is

**译文**

对于一个可审计的“国家—测量”单元 u，令 S_u 表示其中的候选承载原子线段，ℓ(s) 表示线段 s 的有序网络标签。标签 t 的网络转换概率为：

**原文 P038**

$$
p_u^{N}(t)= \frac{\sum_{s\in S_u}\mathbf{1}[\ell(s)=t]} {|S_u|}.
\tag{3}
$$

**译文**

$$
p_u^{N}(t)= \frac{\sum_{s\in S_u}\mathbf{1}[\ell(s)=t]} {|S_u|}.
\tag{3}
$$

**原文 P039**

The corridor distribution sums the masses in Eq. (2) for each corridor and normalizes within the same $S_u$. Before normalization, both distributions have total mass $|S_u|$. Their difference therefore describes how the same candidate-bearing observations are organized at the two layers, not a comparison between different trace populations. Direction is preserved for network transitions; the physical corridor is direction-independent because it represents a coastal connection rather than forwarding order.

**译文**

走廊分布对式（2）中每一条走廊的质量求和，并在相同的 S_u 内归一化。归一化以前，两个分布的总质量均为 |S_u|。因此，它们之间的差异描述的是同一批候选承载观测如何在两个层面上组织，而不是对不同轨迹总体进行比较。网络转换始终保留方向；物理走廊不区分方向，因为它表示沿海连接关系，而不是转发顺序。

**原文 P040**

Submarine exposure uses the complete valid-trace population. A traceroute is exposed when at least one of its segments has a feasible inter-region corridor. The number of exposed traces divided by all valid traces in the unit gives the exposure rate. This denominator differs intentionally from $|S_u|$, which conditions the distributions on candidate-bearing segments.

**译文**

海底暴露率使用完整的有效轨迹总体。如果一条 traceroute 至少有一个线段具有可行的跨区域走廊，则该 traceroute 被视为暴露。单元中暴露轨迹数除以全部有效轨迹数，得到暴露率。这个分母有意区别于 |S_u|，后者以候选承载线段为条件构建分布。

### 3.7 Distribution Summaries and Layer Agreement / 分布汇总指标与 Layer Agreement

**原文 P041**

Three metrics summarize each distribution. Top-2 share is the sum of the two largest probabilities and records mass in the dominant categories. Effective category count is $\exp[-\sum_i p_i\log p_i]$ and reports breadth on the scale of an equally weighted category count. Normalized entropy divides Shannon entropy by the logarithm of observed support size and measures evenness relative to that support. Network-to-corridor differences are computed within each unit.

**译文**

每个分布使用三个指标进行汇总。Top-2 占比是两个最大概率之和，用于记录主导类别中的质量。有效类别数为 exp[-Σ_i p_i log p_i]，以等权类别数量的尺度报告分布宽度。归一化熵将 Shannon 熵除以观测支撑大小的对数，用于测量相对于该支撑的均匀程度。网络到走廊的差值在每个单元内部计算。

**原文 P042**

Layer Agreement is the Spearman rank association, across a reported set of units, between network Top-2 share and corridor Top-2 share. A coefficient approaching +1 indicates closely aligned concentration rankings; a coefficient near zero indicates little monotonic rank association, and a negative coefficient indicates opposing rankings. This comparison concerns ordering across units. Within-unit Top-2 differences and effective category counts separately measure how concentration and breadth change across layers. A group can therefore exhibit aligned rankings alongside substantial within-unit narrowing. We report Layer Agreement by measurement family, geography, and candidate-allocation rule.

**译文**

Layer Agreement 是在所报告的单元集合中，网络 Top-2 占比与走廊 Top-2 占比之间的 Spearman 秩关联。接近 +1 的系数表示集中度排序紧密一致；接近 0 表示单调秩关联很弱；负系数表示排序趋向相反。这一比较关注单元之间的排序。单元内部的 Top-2 差值和有效类别数则分别测量集中度和宽度在两个层面之间如何变化。因此，一个分组可以同时表现出一致的排序和明显的单元内收窄。本文按测量家族、地理分组和候选分配规则报告 Layer Agreement。

**原文 P043**

For the frozen equal-share result, we quantify geographic uncertainty at the level where geography is assigned. A cluster-bootstrap replicate samples countries with replacement within each geographic group and carries every country–measurement unit from each sampled country together. We use 50,000 replicates and report percentile intervals. A separate two-sided reference test permutes the geographic labels of whole countries 100,000 times while retaining the observed number of countries in each group. Both procedures use seed 20260919. This country-clustered analysis is applied to the frozen equal-share unit table; projection-score and Top-1 results provide the allocation-robustness comparison.

**译文**

对于冻结的均匀分配结果，我们在地理类别的赋值层级上量化地理不确定性。每次 cluster bootstrap 在每个地理组内有放回地抽取国家，并将被抽中每个国家的全部“国家—测量”单元共同纳入。本文使用 50,000 次重复并报告百分位区间。另一个双侧参考检验在保留每组观测国家数量的同时，对整个国家的地理标签进行 100,000 次置换。两个过程都使用随机种子 20260919。这项按国家聚类的分析应用于冻结的均匀分配逐单元表；投影分数加权和 Top-1 结果用于比较候选分配稳健性。

**原文 P044**

A common 80% Top-2 threshold supplies four descriptive classes: broad at both layers, concentrated at both, network-broad/corridor-concentrated, and network-concentrated/corridor-broad. Continuous Top-2 shifts, effective counts, and normalized entropy accompany the classes so that threshold crossings do not replace the underlying distributions.

**译文**

统一的 80% Top-2 阈值形成四个描述性类别：两个层面都宽广、两个层面都集中、网络宽广但走廊集中，以及网络集中但走廊宽广。连续的 Top-2 变化、有效类别数和归一化熵与这些类别同时报告，从而避免让阈值跨越取代对底层分布的分析。

## 4 Datasets / 数据集

**原文 P045**

All inputs are aligned to July 1, 2026 (UTC). Network-path observations, IP and AS annotations, and cable lifecycle records therefore describe a common analysis period. We combine these observations with network and submarine-cable metadata.

**译文**

所有输入均与 2026 年 7 月 1 日（UTC）对齐。因此，网络路径观测、IP 与 AS 注释以及光缆生命周期记录描述同一分析时段。本文将这些观测与网络元数据和海底光缆元数据结合起来。

### 4.1 RIPE Atlas Measurements / RIPE Atlas 测量

**原文 P046**

Our network observations comprise 18 public RIPE Atlas IPv4 traceroute measurements collected from 00:00 to 01:00 UTC. Thirteen measurements cover independently operated anycast DNS Root services. Wikipedia, Reddit, and assets.nflxext.com provide three application-facing observations. Measurements 5051 and 5151 use dynamic targets as multi-target UDP and ICMP topology references. Table III summarizes the corpus after canonical trace-identity deduplication.

**译文**

网络观测包含在 00:00–01:00 UTC 收集的 18 项公开 RIPE Atlas IPv4 traceroute 测量。13 项测量覆盖独立运行的 anycast DNS 根服务。Wikipedia、Reddit 和 `assets.nflxext.com` 提供 3 项面向应用的观测。测量 5051 和 5151 使用动态目标，分别作为多目标 UDP 和 ICMP 拓扑参考。表 3 汇总了按照规范轨迹身份完成去重后的语料。

**原文 P047**

Each record retains the destination address returned by RIPE Atlas. This preserves the multi-target structure of the two dynamic-target measurements and the destination instances selected by service measurements during the aligned window.

**译文**

每条记录保留 RIPE Atlas 返回的目的地址。这既保留了两项动态目标测量的多目标结构，也保留了对齐时间窗口内服务测量所选择的目的实例。

**原文 P048**

The measurement families do not form a controlled comparison. The two dynamic-target measurements sample many destinations during the window, whereas each service measurement retains the destinations selected for that service. We use the former as topology references and describe differences between the observed populations; we do not attribute those differences to service deployment or target selection.

**译文**

不同测量家族不构成受控比较。两项动态目标测量在该时间窗口内采样多个目的地，而每项服务测量保留为该服务选择的目的地。本文将前者作为拓扑参考，并描述观测总体之间的差异；我们不把这些差异归因于服务部署或目标选择。

### 4.2 Supporting Datasets / 支撑数据集

**原文 P049**

Table IV lists the supporting datasets and versions. RIPE Atlas probe metadata supplies the probe country and source-network context [16]. IPinfo Location and ASN databases annotate visible hops with geographic and AS information [17].

**译文**

表 4 列出了支撑数据集及版本。RIPE Atlas 探针元数据提供探针国家和源网络背景 [16]。IPinfo Location 和 ASN 数据库为可见跳添加地理信息和 AS 信息 [17]。

**原文 P050**

The Submarine Cable Map provides the cable and landing-point inventory, including lifecycle and organizational fields  [1]. The analysis includes systems in service on the measurement date. CAIDA AS Relationships and the derived owner-AS associations supply supplementary ranking context  [18]. A versioned country taxonomy classifies probe countries as island or archipelagic, landlocked, or other coastal.

**译文**

Submarine Cable Map 提供光缆与登陆点清单，包括生命周期字段和组织字段 [1]。分析纳入在测量日期处于服务状态的光缆系统。CAIDA AS Relationships 和由此得到的所有者 AS 关联提供辅助排序背景 [18]。一个带版本的国家分类体系把探针国家分为岛屿或群岛、内陆以及其他沿海地区。

## 5 Results / 结果

**原文 P051**

The paired audit reveals cross-layer differences within country–measurement units and geographic variation in the association between their concentration rankings. We first quantify within-unit changes, then compare Layer Agreement across geographic groups and candidate-allocation rules. Exposure, absolute corridor breadth, and measurement-family summaries provide context for these results.

**译文**

配对审计揭示“国家—测量”单元内部的跨层差异，以及集中度排序关联的地理变化。本文先量化单元内部的变化，再比较不同地理分组和候选分配规则下的 Layer Agreement。暴露率、绝对走廊宽度和测量家族汇总为这些结果提供背景。

**原文 P052**

The processing pipeline retains 490,911 valid traceroutes from 707,314 raw records and yields 3,291,063 atomic segments. Of 2,432,559 mappable segments, 555,119 reach candidate landing points, 171,232 satisfy the corridor constraints, and 124,350 support at least one feasible inter-region corridor. The equal-share audit records 71,990 single-corridor and 52,360 bounded multi-corridor segments. After the eligibility filters in Section  \mbox  {III-B, the analysis contains 370 auditable country–measurement units: 222 DNS Root, 53 application, and 95 topology-reference units.

**译文**

处理流水线从 707,314 条原始记录中保留 490,911 条有效 traceroute，并产生 3,291,063 条原子线段。在 2,432,559 条可映射线段中，555,119 条到达候选登陆点，171,232 条满足走廊约束，124,350 条至少支持一条跨区域走廊。均匀分配审计记录了 71,990 条单走廊线段和 52,360 条有界多走廊线段。经过第 3.2 节的资格筛选后，分析包含 370 个可审计的“国家—测量”单元：222 个 DNS 根单元、53 个应用单元和 95 个拓扑参考单元。

### 5.1 Network and Corridor Diversity Differ within Units / 单元内部的网络多样性与走廊多样性差异

**原文 P053**

Under equal-share allocation, the 80% Top-2 threshold identifies four service-facing cross-layer outcomes (Fig. 5). Among 275 service-facing units, 81 (29.5%) are network-broad/corridor-concentrated, 158 (57.5%) remain broad at both layers, 18 (6.5%) are concentrated at both, and 18 (6.5%) are network-concentrated/corridor-broad. Four of 95 topology-reference units (4.2%) enter the first class; the other 91 remain broad at both layers. The 81 units in the first class directly identify populations whose broad network support accompanies concentrated feasible-corridor support.

**译文**

在均匀分配下，80% Top-2 阈值识别出四种面向服务的跨层结果（图 5）。275 个面向服务单元中，81 个（29.5%）属于“网络宽广、走廊集中”，158 个（57.5%）在两个层面都保持宽广，18 个（6.5%）在两个层面都集中，18 个（6.5%）属于“网络集中、走廊宽广”。95 个拓扑参考单元中有 4 个（4.2%）进入第一类，其余 91 个在两个层面都保持宽广。第一类中的 81 个单元直接识别出宽广网络支撑伴随集中可行走廊支撑的总体。

**原文 P054**

Continuous measures reveal narrowing within as well as across concentration classes. Across all service-facing units, corridor Top-2 share increases in 184 of 275 (66.9%), and effective category count contracts in 204 (74.2%). Of 239 units with a broad network distribution, 178 (74.5%) move upward in Top-2 share: 81 cross the threshold, while 97 remain broad at both layers with a median increase of 6.3 percentage points. Thus, remaining in the broad–broad class can coexist with an increase in concentration. DNS Roots and applications enter the network-broad/corridor-concentrated class at similar rates: 66 of 222 DNS units (29.7%) and 15 of 53 application units (28.3%). Their median continuous Top-2 shifts are 11.0 and 21.0 percentage points.

**译文**

连续指标揭示集中度类别内部以及跨类别的收窄。在全部面向服务单元中，275 个单元里有 184 个（66.9%）的走廊 Top-2 占比增加，204 个（74.2%）的有效类别数收缩。在 239 个网络分布宽广的单元中，178 个（74.5%）的 Top-2 占比上移：81 个跨过阈值，97 个仍在两个层面保持宽广，后者的增幅中位数为 6.3 个百分点。因此，保持 broad–broad 类别可以与集中度增加同时存在。DNS 根和应用进入“网络宽广、走廊集中”类别的比例相近：222 个 DNS 单元中有 66 个（29.7%），53 个应用单元中有 15 个（28.3%）。它们的连续 Top-2 变化中位数分别为 11.0 和 21.0 个百分点。

**原文 P055**

Three existing cases distinguish continuous narrowing, expansion, and changes in absolute breadth from support-relative evenness. Singapore–Netflix moves from 32.5% network Top-2 share to 65.0% corridor Top-2 share, while its effective count contracts from 19.86 to 3.41. The continuous measures capture this substantial narrowing within the broad–broad class. New Zealand–Netflix moves from 63.6% to 37.6%, with effective count expanding from 5.18 to 6.92. Singapore–H-Root moves from 39.6% to 50.1%, and its effective count contracts from 20.67 to 5.99 while normalized entropy changes only slightly.

**译文**

三个现有案例分别展示连续收窄、扩张，以及绝对宽度变化与相对支撑均匀度变化之间的区别。**Singapore–Netflix** 的网络 Top-2 占比从 32.5% 变为走廊 Top-2 占比 65.0%，有效类别数从 19.86 收缩到 3.41。连续指标捕捉到 broad–broad 类别内部的这一明显收窄。**New Zealand–Netflix** 从 63.6% 变为 37.6%，有效类别数从 5.18 扩张到 6.92。**Singapore–H-Root** 从 39.6% 变为 50.1%，有效类别数从 20.67 收缩到 5.99，而归一化熵只发生轻微变化。

**原文 P056**

Bounded multi-corridor segments account for 99.9%, 78.1%, and 98.2% of candidate-bearing observations in these three cases. Repeated overlap among the bounded sets produces different aggregate distributions under the same projection and aggregation rules. Together, the cases and four-class counts establish cross-layer heterogeneity and show why the audit reports both continuous measures and categorical outcomes.

**译文**

在这三个案例中，有界多走廊线段分别占候选承载观测的 99.9%、78.1% 和 98.2%。在相同的投影和聚合规则下，有界集合之间反复出现的重叠会产生不同的聚合分布。这些案例和四类计数共同确立了跨层异质性，并说明审计为何需要同时报告连续指标和分类结果。

### 5.2 Layer Agreement Differs by Geography / Layer Agreement 的地理差异

**原文 P057**

Within-unit differences raise a second question: does network concentration at least preserve the ordering of corridor concentration across units? Under projection-score weighting, Layer Agreement is 0.632 across 67 island and archipelagic service-facing units and 0.001 across 202 coastal-mainland units (Table V). These units represent 10 and 28 countries, respectively, and the observed coefficient difference is 0.631. The island and archipelagic group exhibits a stronger positive concentration-rank association, while the coastal-mainland group exhibits almost no monotonic rank association. Landlocked units form a separate geographic category.

**译文**

单元内部的差异引出第二个问题：网络集中度能否至少保留不同单元之间的走廊集中度排序？投影分数加权下，67 个岛屿与群岛地区面向服务单元的 Layer Agreement 为 0.632，202 个沿海大陆单元为 0.001（表 5）。这些单元分别来自 10 个和 28 个国家，观测到的系数差为 0.631。岛屿与群岛组表现出更强的集中度正秩关联，而沿海大陆组几乎没有单调秩关联。内陆单元构成单独的地理类别。

### 5.3 Geographic Ordering across Candidate Allocations / 不同候选分配下的地理排序

**原文 P058**

The geographic contrast retains the same direction under all three candidate-allocation rules. As allocation moves from equal shares to projection-score weighting and then Top-1, the island coefficient increases from 0.380 to 0.632 and 0.820, while the coastal-mainland coefficient changes from -0.081 to 0.001 and 0.105. The between-group difference consequently increases from 0.461 to 0.631 and 0.715. The equal-share result contains three additional coastal-mainland DNS units relative to the projection-score and Top-1 comparisons. Across these allocation-specific cohorts, the island coefficient exceeds the coastal-mainland coefficient under equal, graded, and Top-1 support. Equal sharing preserves this ordering while assigning corridor mass independently of score magnitudes.

**译文**

三种候选分配规则下，地理差异保持相同方向。当分配方式从均匀分配转为投影分数加权，再转为 Top-1 时，岛屿系数从 0.380 增加到 0.632 和 0.820，沿海大陆系数从 -0.081 变为 0.001 和 0.105。因此，组间差值从 0.461 增加到 0.631 和 0.715。相较于投影分数加权和 Top-1 比较，均匀分配结果多包含 3 个沿海大陆 DNS 单元。在这些分配规则对应的队列中，等量支持、分级支持和 Top-1 支持下的岛屿系数均高于沿海大陆系数。均匀分配在不依据分数大小分配走廊质量时，仍保留这一排序。

**原文 P059**

The reproducible equal-share result supports a country-level uncertainty check. Its 67 island and archipelagic units represent 10 countries, and its 205 coastal-mainland units represent 30 countries. Country-cluster bootstrap 95% intervals are [-0.203, 0.760] for the island coefficient, [-0.284, 0.238] for the coastal-mainland coefficient, and [-0.213, 0.902] for their 0.461 difference. A two-sided country-label permutation gives $p=0.161$. The wide interval for the difference includes zero. This check quantifies uncertainty across 10 island and 30 coastal country clusters; the three allocation rules separately compare the observed ordering under alternative candidate-mass assignments.

**译文**

可复现的均匀分配结果支持国家层面的不确定性检验。67 个岛屿与群岛单元来自 10 个国家，205 个沿海大陆单元来自 30 个国家。按国家聚类的 bootstrap 95% 区间分别为：岛屿系数 [-0.203, 0.760]，沿海大陆系数 [-0.284, 0.238]，二者 0.461 差值 [-0.213, 0.902]。双侧国家标签置换检验得到 p=0.161。差值的宽区间包含 0。该检验量化 10 个岛屿国家簇与 30 个沿海国家簇之间的不确定性；三种分配规则则另行比较不同候选质量分配方式下观测到的排序。

### 5.4 Inter-Region Candidate Exposure / 跨区域候选暴露率

**原文 P060**

Inter-region candidates occur infrequently for most service-facing populations. The DNS family contains 945 country–measurement units with at least 30 valid traceroutes across 77 countries. Pooling eligible Root observations within each country by valid-trace count yields median DNS exposure of 5.50% (IQR 1.10–23.04%; mean 17.80%). The difference between the median and mean records a pronounced upper tail across countries.

**译文**

对于大多数面向服务的总体，跨区域候选出现频率较低。DNS 家族包含 945 个至少拥有 30 条有效 traceroute 的“国家—测量”单元，覆盖 77 个国家。按照有效轨迹数在每个国家内部汇集符合条件的根服务观测，得到 DNS 暴露率中位数 5.50%（四分位距 1.10%–23.04%；均值 17.80%）。中位数与均值之间的差异说明，各国分布存在明显的高值长尾。

**原文 P061**

The three application measurements occupy the same low-exposure range. Median country–measurement exposure is 1.90% for Wikipedia, 1.96% for Reddit, and 1.43% for Netflix Assets. The dynamic multi-target topology references reach 23.24% for MSM 5051 and 23.81% for MSM 5151. These figures describe how often paths in each observed population contain a feasible inter-region corridor; they do not describe concentration after entry.

**译文**

三个应用测量处于相同的低暴露率范围。“国家—测量”暴露率中位数分别为：Wikipedia 1.90%、Reddit 1.96%、Netflix Assets 1.43%。动态多目标拓扑参考的结果分别为：MSM 5051 为 23.24%，MSM 5151 为 23.81%。这些数值描述每一个观测总体中的路径包含可行跨区域走廊的频率，而不描述进入候选空间以后的集中度。

**原文 P062**

Country-matched comparisons describe exposure differences between service and topology-reference populations with the same source-country identity. DNS exposure is lower than MSM 5051 in 70 of 77 shared countries, with a median paired difference of -14.52 percentage points. It is lower than MSM 5151 in 54 of 59 shared countries, with a median difference of -14.82 points. The paired direction holds for 90.9% and 91.5% of shared countries, respectively (Fig. 2).

**译文**

国家匹配比较描述源国家身份相同的服务总体与拓扑参考总体之间的暴露率差异。在 77 个共同国家中，有 70 个国家的 DNS 暴露率低于 MSM 5051，配对差值中位数为 -14.52 个百分点。在 59 个共同国家中，有 54 个国家的 DNS 暴露率低于 MSM 5151，差值中位数为 -14.82 个百分点。配对方向分别在 90.9% 和 91.5% 的共同国家中成立（图 2）。

### 5.5 Absolute Exposure and Breadth by Geography / 地理分组的绝对暴露率与宽度

**原文 P063**

The geographic groups also differ in how often DNS paths enter the candidate space. Giving each country equal weight, island and archipelagic countries have median country-pooled DNS exposure of 49.61% across 9 countries, compared with 7.88% for 54 other coastal countries and 1.70% for 14 landlocked countries. These values record how frequently each geographic group enters the feasible-corridor candidate space.

**译文**

不同地理分组进入 DNS 候选空间的频率也不同。当每个国家获得相同权重时，9 个岛屿与群岛国家的国家汇总 DNS 暴露率中位数为 49.61%，54 个其他沿海国家为 7.88%，14 个内陆国家为 1.70%。这些数值记录每个地理组进入可行走廊候选空间的频率。

**原文 P064**

Conditional equal-share corridor breadth follows a different ordering. Island and archipelagic countries have median corridor Top-2 share of 53.3% and 5.58 effective corridors. Other coastal countries reach 75.4% and 3.39. The two represented landlocked countries reach 80.2% and 2.51. Across 38 countries with both pooled exposure and an auditable corridor summary, exposure has Spearman association -0.29 with corridor Top-2 share and 0.30 with effective corridor count. These quantities show that frequent entry and conditional concentration are not interchangeable.

**译文**

以均匀分配计算的条件走廊宽度呈现另一种排序。岛屿与群岛国家的走廊 Top-2 占比中位数为 53.3%，有效走廊数为 5.58。其他沿海国家分别为 75.4% 和 3.39。两个有可审计结果的内陆国家分别为 80.2% 和 2.51。在同时具有汇总暴露率和可审计走廊汇总结果的 38 个国家中，暴露率与走廊 Top-2 占比之间的 Spearman 关联为 -0.29，与有效走廊数之间的关联为 0.30。这些量说明，频繁进入候选空间和进入后的条件集中度不能相互替代。

### 5.6 Layer Agreement within Measurement Families / 测量家族内部的 Layer Agreement

**原文 P065**

Family-level coefficients are substantially smaller than the island and archipelagic coefficient. Table VI reports Layer Agreement within each observed measurement family. Under projection-score weighting, the coefficient is 0.176 for 219 DNS units, 0.229 for 53 application units, and 0.012 for 95 topology-reference units. Equal-share and Top-1 allocation change all three coefficients, with the largest change occurring for DNS Roots. The equal-share audit contains 222 DNS units, whereas the family allocation comparison contains 219; the tables retain these allocation-specific counts.

**译文**

家族层面的系数明显小于岛屿与群岛组的系数。表 6 报告每一个观测测量家族内部的 Layer Agreement。在投影分数加权下，219 个 DNS 单元的系数为 0.176，53 个应用单元为 0.229，95 个拓扑参考单元为 0.012。均匀分配和 Top-1 分配会改变全部三个系数，其中 DNS 根的变化最大。均匀分配审计包含 222 个 DNS 单元，而家族分配比较包含 219 个；表格保留这些分配规则特定的单元数。

**原文 P066**

Absolute equal-share corridor breadth also differs among the observed families. Table VII reports network and corridor medians. DNS Roots and applications have median corridor Top-2 shares of 72.0% and 70.3%, compared with 30.6% for topology references. Their median effective corridor counts are 3.84 and 3.51, compared with 18.01. The two topology-reference measurements deliberately sample broader target populations, providing a breadth reference for the service-facing distributions.

**译文**

观测测量家族之间，以均匀分配计算的绝对走廊宽度也不同。表 7 报告网络分布和走廊分布的中位数。DNS 根和应用的走廊 Top-2 占比中位数分别为 72.0% 和 70.3%，拓扑参考为 30.6%。它们的有效走廊数中位数分别为 3.84、3.51 和 18.01。两项拓扑参考测量有意采样更宽的目标总体，为面向服务分布提供宽度参照。

**原文 P067**

The high-concentration tail follows the same descriptive family ordering. The leading two corridors receive at least 80% of mass in 83 of 222 DNS units (37.4%), 16 of 53 application units (30.2%), and 4 of 95 topology-reference units (4.2%). Wikipedia, Reddit, and Netflix Assets have median corridor Top-2 shares of 68.3%, 71.0%, and 71.6%, with 4.25, 3.25, and 3.47 effective corridors. Their median Top-2 shifts are 11.0, 25.6, and 23.6 percentage points, respectively.

**译文**

高集中度尾部遵循相同的描述性家族排序。两个主导走廊获得至少 80% 质量的情况分别出现在：222 个 DNS 单元中的 83 个（37.4%）、53 个应用单元中的 16 个（30.2%），以及 95 个拓扑参考单元中的 4 个（4.2%）。Wikipedia、Reddit 和 Netflix Assets 的走廊 Top-2 占比中位数分别为 68.3%、71.0% 和 71.6%，有效走廊数分别为 4.25、3.25 和 3.47。它们的 Top-2 变化中位数分别为 11.0、25.6 和 23.6 个百分点。

**原文 P068**

Normalized entropy supplies a support-relative view. Median entropy reduction is 0.126 for DNS Roots, 0.164 for applications, and 0.081 for topology references. The family summaries therefore agree on observed absolute breadth and concentration, while the Layer Agreement coefficients show that within-family rankings remain weak and allocation-sensitive.

**译文**

归一化熵提供了相对于支撑大小的视角。DNS 根、应用和拓扑参考的熵减少中位数分别为 0.126、0.164 和 0.081。因此，在观测到的绝对宽度和集中度方面，家族汇总结果相互一致；Layer Agreement 系数则表明，家族内部的排序关联仍然较弱，并且对分配规则敏感。

## 6 Robustness, Scope, and Implications / 稳健性、范围与含义

**原文 P069**

Section \mbox  {V-C reports the geographic ordering under three candidate-allocation rules and the country-clustered equal-share uncertainty check. This section examines the A-Root landing-region resolution sweep, states the measurement population, and discusses what within-unit differences and geographic rank associations imply for diversity audits.

**译文**

第 5.3 节报告了三种候选分配规则下的地理排序，以及均匀分配下按国家聚类的不确定性检验。本节考察 A-Root 登陆区域分辨率扫描，说明测量总体，并讨论单元内部差异和地理分组秩关联对多样性审计的含义。

### 6.1 Landing-Region Resolution / 登陆区域分辨率

**原文 P070**

The A-Root landing-region analysis varies maximum diameter over 10, 20, 30, 40, and 50 km while holding the endpoint catchment at 50 km and the RTT tolerance at 5 ms. Table VIII and Fig. 6 report the auditable-unit count, single-corridor share, and median Top-2 share. Exact landing-pair and cable candidate sets have mean Jaccard 1.0 on segments shared with the 30-km baseline. The sweep records changes in region grouping, the candidate-bearing population, and auditable-unit counts within A-Root.

**译文**

A-Root 登陆区域分析在保持端点捕获半径为 50 km、RTT 容差为 5 ms 的情况下，将最大直径设置为 10、20、30、40 和 50 km。表 8 和图 6 报告可审计单元数、单走廊占比和 Top-2 占比中位数。对于与 30 km 基线共享的线段，精确登陆点对和光缆候选集合的平均 Jaccard 为 1.0。该扫描记录 A-Root 内部的区域分组、候选承载总体和可审计单元数量变化。

**原文 P071**

The sweep shows a clear resolution transition. The 10–30-km settings retain a finer coastal partition, whereas single-corridor share rises to 90.1% and 94.8% at 40 and 50 km and median Top-2 share reaches 81.6% and 84.9%. We use 30 km because it remains on the fine side of this observed transition while consolidating nearby facilities; 40–50 km merge substantially more candidate support into single corridors. The A-Root check therefore supplies an empirical basis for the reporting resolution within the tested A-Root subset and an operational basis for the 30-km setting used throughout the audit.

**译文**

该扫描显示出清楚的分辨率转折。10–30 km 设置保留较细的沿海划分；在 40 km 和 50 km 下，单走廊占比分别增加到 90.1% 和 94.8%，Top-2 占比中位数分别达到 81.6% 和 84.9%。本文选择 30 km，是因为它在合并相邻设施的同时仍位于观测转折的细粒度一侧；40–50 km 会把明显更多的候选支撑合并到单条走廊中。因此，A-Root 检验为该子集中的报告分辨率提供了经验依据，并为全文采用 30 km 设置提供操作性依据。

### 6.2 Dependence on Geolocation and Candidate Construction / 对地理定位与候选构造的依赖

**原文 P072**

Every projection begins with IPinfo hop geolocation and the fixed 50-km endpoint catchment. Geographic, lifecycle, and propagation constraints then construct the feasible candidate set. Cable lifecycle filtering aligns the inventory with July 1, 2026; a recorded inventory refresh changed 222 of 694 cable records, including 26 planned-flag changes and 47 revised service dates. The output retains exact landing-pair, cable, corridor, and mapping-resolution identities, making each projected distribution traceable to its geolocation and inventory inputs.

**译文**

每一次投影都从 IPinfo 跳点地理定位和固定的 50 km 端点捕获半径开始，随后通过地理、生命周期和传播约束构建可行候选集合。光缆生命周期筛选将清单与 2026 年 7 月 1 日对齐；一次已记录的清单刷新改变了 694 条光缆记录中的 222 条，其中包括 26 条规划标志变化和 47 条服务日期修订。输出保留精确登陆点对、光缆、走廊和映射分辨率身份，使每个投影分布都可追溯到其地理定位和清单输入。

### 6.3 Snapshot and Population Scope / 快照与总体范围

**原文 P073**

All 18 measurements cover 00:00–01:00 UTC on July 1, 2026, and the supporting datasets are aligned to the measurement date. This common observation window supports cross-sectional comparisons among services and geographic groups. The reported distributions describe the paths observed during that interval.

**译文**

全部 18 项测量覆盖 2026 年 7 月 1 日 00:00–01:00 UTC，支撑数据集与测量日期对齐。这一公共观测窗口支持不同服务和地理分组之间的横截面比较。所报告的分布描述该时间区间内观测到的路径。

**原文 P074**

Reported quantities are observation-weighted over participating RIPE Atlas probes and therefore represent the probes and source ASNs present in each country–measurement population. The eligibility thresholds of 10 probes and 3 probe ASNs remove sparse units from the paired analysis.

**译文**

报告的量按照参与测量的 RIPE Atlas 探针观测加权，因此代表每个“国家—测量”总体中出现的探针和源 ASN。至少 10 个探针和 3 个探针 ASN 的资格阈值用于从配对分析中移除稀疏单元。

**原文 P075**

The service measurements retain their selected instances, while the dynamic multi-target references deliberately sample many destinations during the same window. The reference distributions therefore provide a broader-target context for the service-facing populations. Anycast observations jointly reflect deployed footprint, BGP selection, interconnection, and source-network context.

**译文**

服务测量保留各自选定的实例，而动态多目标参考在同一时间窗口内有意采样多个目的地。因此，参考分布为面向服务的总体提供更宽目标范围的背景。Anycast 观测共同反映已经部署的足迹、BGP 选择、互连关系和源网络背景。

### 6.4 Implications for Diversity Measurement / 对多样性测量的含义

**原文 P076**

The audit separates within-unit diversity differences from the association between rankings across units. The first comparison locates populations where broad network support accompanies concentrated corridor support or where effective breadth narrows within a concentration class. Layer Agreement then measures how closely network and corridor concentration rankings track within a geographic population. Stronger rank association can coexist with substantial within-unit differences, so both measurements are needed to interpret a network-layer diversity summary.

**译文**

审计区分单元内部的多样性差异与单元之间的排序关联。前一种比较定位宽广网络支撑伴随集中走廊支撑的总体，以及同一集中度类别内部有效宽度收窄的总体。Layer Agreement 随后测量同一个地理总体内网络集中度与走廊集中度排序的跟踪程度。较强的秩关联可以与明显的单元内部差异同时存在，因此需要结合两种测量解释网络层多样性汇总。

**原文 P077**

The DNS country-level summaries put the geographic rank contrast in context. Island and archipelagic countries have a lower median corridor Top-2 share than other coastal countries (53.3% versus 75.4%) and a higher median effective corridor count (5.58 versus 3.39). Thus, the observed DNS country-level medians show broader corridor support for the island group. Across 38 countries with both exposure and corridor summaries, exposure has Spearman associations of -0.29 with corridor Top-2 share and 0.30 with effective corridor count. These statistics describe entry frequency and conditional breadth at the country level, complementing the service-facing unit-level Layer Agreement comparison.

**译文**

DNS 国家层面的汇总为地理秩关联差异提供背景。岛屿与群岛国家的走廊 Top-2 占比中位数低于其他沿海国家（53.3% 对 75.4%），有效走廊数中位数更高（5.58 对 3.39）。因此，观测到的 DNS 国家层面中位数显示，岛屿组具有更宽广的走廊支撑。在同时具有暴露率和走廊汇总的 38 个国家中，暴露率与走廊 Top-2 占比的 Spearman 关联为 -0.29，与有效走廊数的关联为 0.30。这些统计量描述国家层面的进入频率和条件宽度，为面向服务的单元层面 Layer Agreement 比较提供补充。

**原文 P078**

A possible explanation for the geographic contrast is that maritime access and network organization impose partly shared constraints on concentration rankings for island and archipelagic sources. In coastal-mainland settings, terrestrial routing, domestic backhaul, and interconnection may allow network concentration to vary more independently of feasible submarine corridors. This is a mechanism hypothesis; the present comparisons measure the geographic association. Distinguishing these explanations would require evidence linking the relevant access and routing structures to individual country–measurement outcomes.

**译文**

地理差异的一种可能解释是，海上接入与网络组织对岛屿和群岛来源的集中度排序施加了部分共同约束。在沿海大陆环境中，陆地路由、国内回传和互连关系可能使网络集中度相对于可行海底走廊更加独立地变化。这是一个机制假设；当前比较测量的是地理关联。区分这些解释需要将相关接入与路由结构同各个“国家—测量”结果联系起来的证据。

**原文 P079**

For diversity audits, the unit-level results provide concrete inspection targets: 81 service-facing populations have broad network support but concentrated corridor support, and the continuous summaries identify additional narrowing among the 158 populations classified as broad at both layers. The geographic comparison adds context to interpreting network-layer rankings: they track corridor concentration more closely in the observed island and archipelagic group than in the coastal-mainland group. Together, these results support checking physical-corridor concentration alongside network diversity when evaluating service paths.

**译文**

对于多样性审计，单元层面结果提供具体的检查对象：81 个面向服务总体具有宽广网络支撑但集中的走廊支撑；连续汇总还识别了被归为两个层面都宽广的 158 个总体中的进一步收窄。地理比较为解释网络层排序增加背景：在观测到的岛屿与群岛组中，这些排序比在沿海大陆组中更紧密地跟踪走廊集中度。两类结果共同支持在评估服务路径时，将物理走廊集中度与网络多样性一起检查。

**原文 P080**

Corridor concentration can be combined with cable multiplicity within a corridor, landing-station redundancy, shared terrestrial backhaul, correlated hazards, available rerouting capacity, and repair processes in a broader resilience assessment. CLASP supplies the cross-layer concentration component and preserves the exact candidate identities needed for that follow-on analysis.

**译文**

在更广泛的韧性评估中，可以把走廊集中度与一条走廊内部的光缆数量、登陆站冗余、共享陆地回传、相关灾害、可用改道能力和修复过程结合。CLASP 提供其中的跨层集中度组成，并保留后续分析所需的精确候选身份。

### 6.5 Ethics and Reproducibility / 伦理与可复现性

**原文 P081**

The study uses archived public RIPE Atlas measurements and infrastructure metadata and reports aggregate country–measurement statistics. It does not target individual users or report individual probe addresses. Candidate assignments are feasible hypotheses and should not be interpreted as disclosure of an operator's actual cable use.

**译文**

本研究使用已归档的公开 RIPE Atlas 测量和基础设施元数据，并报告聚合的“国家—测量”统计。研究不以个体用户为目标，也不报告单个探针地址。候选关联是可行性假设，不应被解释为披露运营商实际使用的光缆。

**原文 P082**

The released measurement IDs, configuration values, mapping-resolution states, pipeline counts, and scripts reconstruct the primary tables and figures from versioned inputs. The paper's 80% four-class rule is the primary descriptive classification; the repository's tier-based auxiliary classification uses a different rule and must remain separately named in the artifact.

**译文**

公开的测量 ID、配置值、映射分辨率状态、流水线计数和脚本，可以根据带版本的输入重建主要表格和图。论文中的 80% 四类规则是主要描述性分类；仓库中的分层辅助分类使用不同规则，在测量产物中必须使用不同名称。

## 7 Conclusion / 结论

**原文 P083**

CLASP compares network-transition and feasible-corridor distributions over the same traceroute segments. In the aligned one-hour RIPE Atlas snapshot, 81 of 275 service-facing units have broad network support and concentrated corridor support under equal-share allocation, while effective category count contracts in 204 units (74.2%). Across units, projection-score Layer Agreement is 0.632 for 67 island and archipelagic units and 0.001 for 202 coastal-mainland units. The geographic ordering persists under equal-share and Top-1 allocation, with between-group differences of 0.461, 0.631, and 0.715 across the three rules. Network-layer diversity audits therefore need to examine both within-unit physical-corridor concentration and the geographic variation in cross-layer rank association.

**译文**

CLASP 在相同的 traceroute 线段上比较网络转换分布与可行走廊分布。在对齐的一小时 RIPE Atlas 快照中，均匀分配下，275 个面向服务单元中有 81 个具有宽广网络支撑和集中走廊支撑，204 个单元（74.2%）的有效类别数收缩。在单元之间，投影分数加权下的 Layer Agreement 在 67 个岛屿与群岛单元中为 0.632，在 202 个沿海大陆单元中为 0.001。均匀分配和 Top-1 分配下的地理排序保持不变，三种规则对应的组间差值分别为 0.461、0.631 和 0.715。因此，网络层多样性审计需要同时检查单元内部的物理走廊集中度，以及跨层秩关联的地理变化。

## 8 Use of AI Disclosure / AI 使用披露

**原文 P084**

OpenAI ChatGPT and Codex assisted with code development, plotting scripts and language revision. Their contribution was limited to these tasks, and the authors validated the outputs against the source data and analysis results.

**译文**

OpenAI ChatGPT 和 Codex 协助完成代码开发、绘图脚本和语言修订。它们的贡献仅限于这些任务，作者依据源数据和分析结果验证了输出。

## References / 参考文献

[1] TeleGeography, “Submarine Cable Map,” 2026. https://www.submarinecablemap.com/

[2] R. Durairajan, S. Ghosh, X. Tang, P. Barford, and B. Eriksson, “Internet Atlas: A geographic database of the Internet,” Proceedings of the 5th ACM Workshop on HotPlanet, 2013, pp. 15–20.

[3] R. Durairajan, P. Barford, J. Sommers, and W. Willinger, “InterTubes: A study of the US long-haul fiber-optic infrastructure,” Proceedings of ACM SIGCOMM, 2015, pp. 565–578.

[4] S. Anderson, L. Salamatian, Z. S. Bischof, A. Dainotti, and P. Barford, “iGDB: Connecting the physical and logical layers of the Internet,” Proceedings of ACM IMC, 2022, pp. 433–448.

[5] A. Ramanathan and S. Abdu Jyothi, “Nautilus: A framework for cross-layer cartography of submarine cables and IP links,” pp. 101–102, 2024.

[6] C. Wang, Y. Zhang, Q. Dong, E. Carisimo, R. Durairajan, and F. E. Bustamante, “Threading the ocean: Mapping digital routes across submarine cables using Calypso,” Proceedings of ACM SIGCOMM, 2025, pp. 1260–1262.

[7] A. Ramanathan, R. Sankaran, and S. Abdu Jyothi, “Xaminer: An Internet cross-layer resilience analysis tool,” Proceedings of the ACM on Measurement and Analysis of Computing Systems, vol. 8, no. 1, pp. 1–37, 2024.

[8] S. Liu, Z. S. Bischof, I. Madan, P. K. Chan, and F. E. Bustamante, “Out of sight, not out of mind: A user-view on the criticality of the submarine cable network,” Proceedings of ACM IMC, 2020, pp. 194–200.

[9] D. Cicalese, J. Augé, D. Joumblatt, T. Friedman, and D. Rossi, “Characterizing IPv4 anycast adoption and deployment,” Proceedings of CoNEXT, 2015, pp. 1–13.

[10] W. B. De Vries, R. de O. Schmidt, W. Hardaker, J. Heidemann, P.-T. de Boer, and A. Pras, “Broad and load-aware anycast mapping with Verfploeter,” Proceedings of ACM IMC, 2017, pp. 477–488.

[11] H. Ye, S. Wang, and D. Li, “Impact of international submarine cable on Internet routing,” IEEE INFOCOM, 2023, pp. 1–10.

[12] Z. S. Bischof, J. P. Rula, and F. E. Bustamante, “In and out of Cuba: Characterizing Cuba’s connectivity,” Proceedings of ACM IMC, 2015, pp. 487–493.

[13] Z. S. Bischof, R. Fontugne, and F. E. Bustamante, “Untangling the world-wide mesh of undersea cables,” Proceedings of ACM HotNets, 2018, pp. 78–84.

[14] R. Fanou, B. Huffaker, R. Mok, and K. C. Claffy, “Unintended consequences: Effects of submarine cable deployment on Internet routing,” Passive and Active Network Measurement, 2020, pp. 211–227.

[15] E. Carisimo, C. J. Wang, M. Weaver, F. E. Bustamante, and P. Barford, “A hop away from everywhere: A view of the intercontinental long-haul infrastructure,” Proceedings of the ACM on Measurement and Analysis of Computing Systems, vol. 7, no. 3, pp. 1–26, 2023.

[16] RIPE NCC, “RIPE Atlas,” 2026. https://atlas.ripe.net/

[17] IPinfo, “IP geolocation and ASN databases,” 2026. https://ipinfo.io/

[18] CAIDA, “AS relationships dataset,” 2026. https://www.caida.org/catalog/datasets/as-relationships/
