# When Network Diversity Narrows at Sea: A Cross-Layer View of Internet Service Paths

**Abstract**

The diversity visible in traceroute does not reveal how broadly physical infrastructure supports Internet service paths. A country may reach a service through many network transitions while those paths converge on only a few feasible coastal directions. We study this cross-layer divergence by comparing distributions of observed AS transitions and feasible landing-region corridors over identical path segments. Our analysis covers RIPE Atlas measurements of DNS Roots, applications, and multi-target topology references. Network diversity and physical-corridor diversity often diverge for service-facing paths: some country--service populations combine broad network transitions with concentrated feasible-corridor support, while others remain broad at both layers. This contraction is much less common in multi-target topology measurements, showing that service selection and deployment must be retained when characterizing the user-visible physical footprint. Exposure and physical concentration describe distinct properties. Geography shapes entry into submarine infrastructure; service deployment and target selection shape whether that exposure spreads across coastal directions or concentrates within a few. Multiple network routes can rest on a narrow feasible physical-corridor space, making a cross-layer view essential to evaluating service diversity.

**Keywords:** Internet measurement, submarine cables, traceroute, cross-layer analysis, anycast, path diversity

## I. Introduction

Submarine cables form the physical backbone of the global Internet, carrying nearly all intercontinental traffic and connecting users to services worldwide [1]. Cable disruptions can isolate regions, degrade remote-service access, and redirect paths toward longer or congested alternatives. Internet measurements describe the paths through logical indicators such as routers, Autonomous Systems (ASes), and service replicas.

Logical and physical diversity describe different structures. Paths traversing different routers or ASes may leave a country or region through the same coastal area or converge on the same submarine corridor. Hereafter, country refers to countries or regions. A service can therefore present a broad network-layer path population while its feasible physical support occupies only a few coastal directions. Joint analysis of the application target, observed network path, and physical candidate space reveals whether network-layer diversity is preserved across coastal directions.

Prior work measures user-path involvement with submarine infrastructure [2], associates AS links with cable systems [3, 4, 5], and constructs cross-layer infrastructure maps [6, 7]. Our paired distribution audit compares the network transitions and feasible landing-region corridors of each country-service population. Both distributions are constructed from the same atomic segments.

A landing-region corridor is a direction-independent pair of bounded landing regions connected by at least one active cable candidate. Router locations, cable landing points and lifecycles, and propagation time determine each segment's feasible corridor set. We allocate equal shares of segment observation mass across this set and aggregate them into a candidate-support distribution aligned with the network-transition distribution.

We organize the audit around three research questions:

RQ1 How frequently do country-service paths contain a feasible inter-region submarine corridor?

RQ2 How is observation mass distributed across feasible corridors?

RQ3 Which country-service populations have broad network transition distributions that project onto narrower corridor distributions?

We analyze 490,911 valid traceroutes from 18 public RIPE Atlas measurements covering all 13 DNS Roots, Wikipedia, Reddit, Netflix Assets, and two multi-target topology references. The aligned one-hour snapshot yields 3,291,063 atomic segments. Of these, 2,432,559 are projection-eligible and 124,350 support at least one feasible inter-region corridor. Under the 30-km landing-region abstraction, 42.1% of candidate-bearing segments support multiple corridors.

We compare the distributions within each auditable country-measurement unit. Ordered endpoint-AS pairs form the network distribution, and uniformly allocated segment mass forms the corridor distribution. Top-2 share measures absolute concentration, effective category count measures breadth, and normalized entropy measures support-relative evenness. A common 80% Top-2 threshold supplies a descriptive four-class view.

The 370-unit analysis identifies both contraction and broad support across layers. It contains 222 DNS Root, 53 application, and 95 topology-reference units. Median corridor Top-2 shares are 72.0%, 70.3%, and 30.6%, with effective corridor counts of 3.84, 3.51, and 18.01. Among 275 service-facing units, 81 (29.5%) combine broad network and concentrated corridor distributions, and 158 (57.5%) remain broad at both layers; 4 of 95 topology-reference units enter the first class.

Country-matched comparisons further show lower inter-region candidate exposure for service-facing measurements. Island and archipelagic countries form the highest-exposure group.

This paper makes three contributions. First, it formulates application-aware submarine-cable measurement as a three-layer audit connecting services, network transitions, and feasible physical corridors. Second, it develops a reproducible projection that applies geographic, lifecycle, and propagation feasibility and allocates observation mass uniformly over each segment's corridor set. Third, it measures exposure, concentration, and cross-layer contraction across DNS Roots, applications, and topology references, including geographic and resolution sensitivity analyses.

## II. Background

### A. Network and Submarine-Cable Infrastructure

Users reach services through domain names, CDN resources, replicas, and anycast targets. Traceroute exposes the intervening IP hops and AS transitions. For geographically separated regions, these logical paths depend on submarine cables that join coastal landing stations to terrestrial backhaul and visible ASes. Multiple cables can connect the same coastal regions, and one cable can serve several landing locations.

The network-to-physical relationship is many-to-many. Different routers or AS transitions may project onto one landing-region corridor, while a recurring network transition may support several physical alternatives. We measure the two distributions over the same observations: network diversity describes observed logical transitions, and physical diversity describes their supported corridor distribution.

Landing regions provide a stable geographic unit between exact landing stations and country-wide cable counts. Exact stations preserve facility detail but split nearby coastal access points that serve the same direction. Country-level cable inventories combine distinct coastlines and international directions. A bounded landing region retains coastal structure, and a corridor identifies the paired entry-exit direction connecting two such regions. Parallel cable systems can share one corridor while remaining distinguishable in the underlying candidate records.

Countries provide a shared geographic and external-connectivity context. Island, coastal, and landlocked geography shapes access to submarine infrastructure; landing facilities, backhaul, gateways, exchanges, and operator interconnection shape the paths available to users. Country grouping retains variation among access networks and upstream providers within that context.

### B. Existing Cross-Layer Measurements

Event-oriented studies relate new submarine connectivity to routing changes. Bischof et al. characterized Cuba's connectivity before and after ALBA-1 and later formulated the task of connecting Internet observations to the worldwide cable mesh [8, 9]. Fanou et al. measured routing changes following new cable deployments [10].

User-oriented work measures submarine involvement in service paths. Liu et al. combine resource discovery, RIPE Atlas traceroutes, geolocation, and propagation feasibility to quantify how users reach Web resources through submarine paths [2]. Routing-oriented work connects cable infrastructure to AS-level structure; Ye et al. infer AS relationships with international cable and landing-station structures and analyze their interaction with routing [3].

Exposure and concentration describe complementary aspects of service paths. Exposure counts how frequently a service path enters a feasible submarine candidate space. Concentration examines the structure of that space after entry. A country may have high exposure and broad corridor support, or low exposure with the exposed observations concentrated on a few directions.

Cross-layer cartography supplies geographic infrastructure representations. Internet Atlas and InterTubes connect long-haul fiber facilities to observed paths [6, 11]; iGDB integrates facilities, fiber, and network entities [7]; measurements of intercontinental links identify layer-3 links and gateway routers [12]. Nautilus associates IP links with candidate cables using traceroute, geolocation, latency, ownership, and cable metadata [4]. Calypso combines cable layouts, network relationships, latency, and country-level paths [5], while Xaminer applies cross-layer maps to configurable infrastructure analyses [13].

Service deployment determines which paths enter these mappings. Anycast routing, replica placement, and interconnection select service instances and their network paths [14, 15]. We retain this service-specific path view when projecting physical candidates and comparing network and corridor distributions over identical atomic segments.

The paired construction aligns the statistical unit across layers. A network transition and its corridor support originate from the same atomic segment, so changes in concentration reflect the projection of a fixed observation population. Country-service aggregation preserves deployment differences among equivalent services and geographic differences among their users.

### C. Country-Service View of Cross-Layer Diversity

Country and service jointly define each observation population. Geographic and interconnection environments shape source-side options; anycast, replica selection, and routing choose among them. DNS Roots illustrate this interaction. Functionally equivalent services operate independent anycast deployments, so a country may reach different Roots through distinct instances, AS transitions, and corridors. Distributed applications similarly localize access in some countries and direct others toward remote infrastructure.

Multi-target topology measurements provide a broader reference population. Their dynamic destinations sample many network directions during the same time window. Each service measurement instead retains the destinations selected for that service. Comparing these families characterizes the observed footprints of their target-selection and routing processes.

Our measurement separates three properties. Submarine exposure is the fraction of valid traceroutes containing an inter-region feasible corridor. Corridor concentration describes how candidate-bearing segment mass is distributed across landing-region corridors. Cross-layer contraction compares that physical distribution with the network transitions formed from the same segments. The framework next derives these quantities; Section IV introduces the aligned path and infrastructure datasets.

## III. Framework

### A. Overview

The framework constructs paired network and corridor distributions for each country-service group. It combines traceroute, probe metadata, IP geolocation and ASN mappings, AS context, and cable metadata. Figure 1 shows the three components in processing order: path extraction creates atomic hop-pair segments, corridor projection constructs each segment's feasible landing-region corridor set, and aggregation forms the paired distributions. Complete traceroutes supply the exposure denominator.

The outputs retain the distinction between trace-level exposure and segment-level distributions. Exposure records whether a path contains at least one inter-region feasible corridor. The distributions condition on candidate-bearing observations and compare how their mass is organized across logical transitions and physical directions.

**Figure 1. Cross-layer audit framework.**

[Original figure PDF](figures/framework_cross_layer_audit.pdf)

### B. Path Extraction

We group traceroutes by probe country and measured service to retain the source-side connectivity context and deployment-specific destination selection. Hop countries remain segment attributes.

We normalize each traceroute into visible hops with locations, ASNs, and RTTs. The analysis uses the complete visible sequence. An auxiliary path-entry view ends at the first appearance of the target ASN.

Successive visible, geolocated hops form atomic segments. Each segment records endpoint locations, ASNs, countries, positions, RTT difference, and bridged-hop count. Repeated hops and RTT samples retain their trace identity and ordering. When timeouts separate two visible hops, the bridged-hop count records the gap for pipeline accounting.

When both endpoint ASNs are available, their ordered pair is the segment's network-transition label. Segments with one missing endpoint ASN receive an ordered country-pair fallback label.

Audit eligibility is evaluated over the complete country-service group. It requires a country-fallback share of at most 30%, at least 30 candidate-bearing segments, 10 probes, and 3 probe ASNs.

### C. Corridor Projection

**Landing-station and cable candidates.** Landing stations within 50 km of each endpoint are paired through cable systems active on July 1, 2026. Explicit path or branch information defines direct cable segments; unordered landing-point membership defines reachability at the metadata's topology resolution and is recorded in provenance.

Endpoint catchment retrieves landing stations, and landing-region grouping organizes them into coastal regions. The 50-km catchment retrieves stations consistent with router geolocation; the 30-km diameter groups the retrieved stations. Cable lifecycle filtering is applied before region pairs are formed.

**Geographic and delay feasibility.** Let $D$ be the great-circle distance between a candidate landing pair and $v_f=200$ km/ms the effective propagation speed in fiber. A candidate is propagation-feasible when

$$
\Delta RTT + \tau \geq \frac{2D}{v_f},
\tag{1}
$$

where $\Delta RTT$ is the segment RTT difference and $\tau=5$ ms. For non-positive or inconclusive differences, candidates use the geographic and lifecycle constraints and retain an RTT-status flag.

The inequality compares the observed round-trip increment with the minimum round-trip propagation time between landing points. It operates as a feasibility condition alongside endpoint proximity and cable connectivity.

**Diameter-limited landing regions.** Landing stations are grouped into regions with a 30-km maximum pairwise distance. A landing-region corridor is a direction-independent region pair connected by a feasible cable candidate. Multiple cables and exact landing pairs may contribute to one corridor; distinct coastal entry-exit patterns remain separate.

The aggregate distribution uses the complete feasible corridor set, with the corridor as its primary physical unit. Cable candidates and exact landing pairs remain linked in the outputs. A supplementary ranking uses landing proximity, propagation consistency, and AS context.

**Observation mass.** Duplicate cable rows belonging to the same corridor are collapsed within each atomic segment. For a segment (s) with feasible corridor set $\mathcal{C}_s$, the corridor mass is

$$
w_{s,c}=\frac{1}{|\mathcal{C}_s|},
    \qquad c\in\mathcal{C}_s.
\tag{2}
$$

Thus $\sum_{c\in\mathcal{C}_s} w_{s,c}=1$: each candidate-bearing segment contributes equal total observation mass, distributed according to candidate multiplicity.

### D. Measurement Configuration

Table I lists the common configuration.

**Table I. Cross-layer measurement configuration.**

| Parameter | Value |
| --- | --- |
| Endpoint landing catchment radius | 50 km |
| Landing-region maximum diameter | 30 km |
| Fiber propagation speed | 200 km/ms |
| RTT tolerance | 5 ms |
| Same-city threshold | 25 km |
| Cable lifecycle | Active on July 1, 2026 |
| Inconclusive RTT | Retained and flagged |
| Timeout-bridged segment | Retained and flagged |
| Primary path scope | Complete visible sequence |

### E. Physical Mapping Resolution

Table II classifies each segment by input coverage and the size of $\mathcal{C}_s$.

**Table II. Segment-level physical mapping resolution.**

| State | Operational definition |
| --- | --- |
| Single corridor | Feasibility inputs available and $\vert \mathcal{C}_s\vert =1$ |
| Bounded multi-corridor | Feasibility inputs available and $\vert \mathcal{C}_s\vert >1$ |
| No feasible corridor | Feasibility inputs available and $\vert \mathcal{C}_s\vert =0$ |
| Insufficiently resolved | Insufficient location, path-visibility, or metadata fields for stable corridor construction |

Single- and bounded multi-corridor segments form the physical distribution. Pipeline accounting retains the other states, and all valid traces form the exposure denominator.

Candidate-set size and aggregate concentration describe different levels of the analysis. A unit may contain many bounded segments yet concentrate after their uniformly allocated mass repeatedly supports the same corridors.

### F. Distribution Aggregation

For each probe-country and service group, we construct both distributions from candidate-bearing atomic segments. Counting ordered endpoint-AS labels gives the network-transition probabilities $p^{N}$. Summing the corridor masses in Eq. (2) and normalizing within the group gives the corridor probabilities $p^{C}$.

For each auditable country--measurement unit $u$, let $S_u$ denote the candidate-bearing atomic segments and $\ell(s)$ the label assigned to segment $s$. Each distinct segment contributes once to an ordered network-side label at its available mapping resolution. The probability of label $t$ is

$$

p_u^{N}(t)= \frac{\sum_{s\in S_u}\mathbf{1}[\ell(s)=t]} {|S_u|}.

$$

Direction is preserved throughout the aggregation. We summarize the distribution using its Top-2 share, defined as the combined probability of the two most frequent network-side labels. Higher values indicate that the observed network-side structure is concentrated in fewer dominant labels.

Submarine exposure uses complete valid traceroutes. A traceroute is exposed when at least one segment has a feasible inter-region corridor. Dividing the exposed-trace count by all valid traces in the country-service unit gives the exposure rate.

Three metrics summarize each distribution. Top-2 share is the sum of the two largest probabilities. The effective category count is $\exp[-\sum_i p_i\log p_i]$ and measures breadth on the scale of an equally weighted category count. Normalized entropy divides Shannon entropy by log support size. Network-to-corridor differences are computed within each unit.

The metrics distinguish dominant-corridor mass from the long tail and support size. Top-2 share emphasizes leading categories, effective count incorporates the complete probability vector, and normalized entropy measures evenness relative to observed support.

A common 80% Top-2 threshold supplies four descriptive classes: broad at both layers, concentrated at both, network-broad/corridor-concentrated, and the reverse. Continuous Top-2 shifts, effective counts, and normalized entropy accompany the classification.

## IV. Datasets

All inputs are aligned to July 1, 2026 (UTC). Network-path observations, IP and AS annotations, and cable lifecycle records therefore describe a common analysis period. We combine these observations with network and submarine-cable metadata.

### A. RIPE Atlas Measurements

Our network observations comprise 18 public RIPE Atlas IPv4 traceroute measurements collected from 00:00 to 01:00 UTC. Thirteen measurements cover independently operated anycast DNS Root services. Wikipedia, Reddit, and assets.nflxext.com provide three application-facing observations. Measurements 5051 and 5151 use dynamic targets as multi-target UDP and ICMP topology references. Table III summarizes the corpus after canonical trace-identity deduplication.

**Table III. RIPE Atlas measurement corpus.**

| Group | Target | MSM ID(s) | Raw | Valid |
| --- | --- | --- | --- | --- |
| DNS Roots | A-M Root | 5009, 5010, 5011, 5012, 5013, 5004, 5014, 5015, 5005, 5016, 5001, 5008, 5006 | 534,276 | 317,873 |
| Applications | Wikipedia; Reddit; Netflix Assets | 86710103; 176906957; 176517335 | 115,596 | 115,596 |
| Topology references | IPv4 UDP; IPv4 ICMP | 5051; 5151 | 57,442 | 57,442 |
| Total | 18 measurements | - | 707,314 | 490,911 |

Each record retains the destination address returned by RIPE Atlas. This preserves the multi-target structure of the two dynamic-target measurements and the destination instances selected by service measurements during the aligned window.

### B. Supporting Datasets

Table IV lists the supporting datasets and versions. RIPE Atlas probe metadata supplies the probe country and source-network context [16]. IPinfo Location and ASN databases annotate visible hops with geographic and AS information [17].

The Submarine Cable Map provides the cable and landing-point inventory, including lifecycle and organizational fields [1]. The analysis includes systems in service on the measurement date. CAIDA AS Relationships and the derived owner-AS associations supply supplementary ranking context [18]. A versioned country taxonomy classifies probe countries as island or archipelagic, landlocked, or other coastal.

**Table IV. Supporting datasets.**

| Dataset | Version | Content |
| --- | --- | --- |
| RIPE Atlas probe metadata | 2026-07-01 | Probe country and source ASN |
| IPinfo Location MMDB | 2026-07-01 | Hop geolocation |
| IPinfo ASN MMDB | 2026-07-01 | IP-AS mapping |
| Submarine Cable Map | 2026-07-01 | 694 cables; 1,916 landing points |
| CAIDA AS Relationships | 2026-07-01 release | AS relationships |
| Owner-AS mapping | 2026-07-01 inputs | Owner-AS associations |
| Country geography taxonomy | 2026-07-01 | Operational geography classes |

## V. Results

The results compare network and corridor distributions built from the same segments and examine how their relationship varies across services and countries. Exposure measures how often a path enters the feasible inter-region corridor space. Conditional breadth measures how candidate-bearing observations are distributed within that space. We first establish these two properties, then examine their geographic variation and the paired cross-layer distributions.

The processing pipeline retains 490,911 valid traceroutes from 707,314 raw records, yielding 3,291,063 atomic segments. Of the 2,432,559 mappable segments, 555,119 reach candidate landing points, 171,232 satisfy the corridor constraints, and 124,350 support inter-region corridors. The final set contains 71,990 single-corridor segments and 52,360 bounded multi-corridor segments. Under the unit-mass aggregation rule, they form 370 auditable country-measurement units.

### A. Service-Facing Paths Show Lower Candidate Exposure

DNS exposure has a pronounced upper tail: inter-region candidates appear infrequently for most countries and recur in a smaller group. The DNS family contains 945 country-measurement units with at least 30 valid traceroutes, covering 77 countries. Pooling eligible Root observations within each country by valid-trace count yields a median exposure of 5.50% (IQR: 1.10%-23.04%; mean: 17.80%). The difference between the median and mean reveals this uneven distribution across countries.

The three application measurements occupy the same low-exposure range. Median country-measurement exposure is 1.90% for Wikipedia, 1.96% for Reddit, and 1.43% for Netflix Assets. The multi-target topology references reach 23.24% for MSM 5051 and 23.81% for MSM 5151. Figure 2 compares the complete country distributions and shows this separation.

Country-matched comparisons show lower DNS exposure while preserving source geography and changing the target population. DNS exposure is lower than MSM 5051 in 70 of 77 shared countries, with a median paired difference of $-14.52$ percentage points. It is lower than MSM 5151 in 54 of 59 shared countries, with a median difference of $-14.82$ points. The paired direction holds for 90.9% and 91.5% of the shared countries, respectively.

The two protocols therefore reveal the same family ordering: service-facing targets expose a smaller inter-region path population than the dynamic multi-target measurements observed from the same countries.

**Figure 2. Inter-region candidate exposure.**

[(a) Original figure PDF](figures/fig_result_overview_distribution.pdf)

[(b) Original figure PDF](figures/fig_result_overview_paired.pdf)

### B. Service-Facing Observations Occupy Narrower Corridor Spaces

We measure corridor breadth over 222 DNS Root, 53 application, and 95 topology-reference units. Every unit meets the audit thresholds in Section III.B. Its network and corridor distributions contain the same candidate-bearing segments. Table V reports the median concentration and breadth of each family.

**Table V. Network-transition and corridor distributions.**

| Family | Units | Net. Top-2 | Corr. Top-2 | $\Delta$Top-2 | Eff. network | Eff. corridor |
| --- | --- | --- | --- | --- | --- | --- |
| DNS Roots | 222 | 53.1% | 72.0% | +11.0 pp | 7.45 | 3.84 |
| Applications | 53 | 45.2% | 70.3% | +21.0 pp | 9.89 | 3.51 |
| Topology references | 95 | 27.3% | 30.6% | +2.7 pp | 24.34 | 18.01 |

DNS Roots and applications occupy narrower corridor spaces than the topology references. Their median corridor Top-2 shares are 72.0% and 70.3%, compared with 30.6% for topology references; their effective corridor counts are 3.84 and 3.51, compared with 18.01. The topology-reference median thus contains 4.7 times as many effective corridors as DNS and 5.1 times as many as the applications. Its Top-2 share is 41.4 percentage points below DNS and 39.7 points below the applications.

The high-concentration tail follows the same family ordering. The leading two corridors receive at least 80% of mass in 83 of 222 DNS units (37.4%), 16 of 53 application units (30.2%), and 4 of 95 topology-reference units (4.2%). These threshold counts and the family medians describe the separation at the upper end and center of the concentration distributions, respectively.

The three applications reach similar absolute corridor breadth through different amounts of redistribution from their network-transition distributions. Wikipedia, Reddit, and Netflix Assets have median corridor Top-2 shares of 68.3%, 71.0%, and 71.6%, with 4.25, 3.25, and 3.47 effective corridors. Their median Top-2 shifts are 11.0, 25.6, and 23.6 percentage points, respectively. Together, these measurements describe their shared narrow physical footprint and different cross-layer shifts.

Figure 3 shows that the family separation extends across the distributions. The service-facing ECDFs occupy the higher-concentration range, and their effective-count distributions remain centered on three to four equally weighted corridors. Top-2 share captures mass in the dominant directions, while effective count captures breadth across the full support. Both metrics yield the same family ordering.

**Figure 3. Corridor concentration and breadth by measurement family.**

[(a) Original figure PDF](figures/fig_corridor_concentration_ecdf.pdf)

[(b) Original figure PDF](figures/fig_effective_count_comparison.pdf)

The largest family difference remains the absolute physical breadth reached after projection. Normalized entropy provides a support-relative view: median entropy reduction is 0.126 for DNS Roots, 0.164 for applications, and 0.081 for topology references. Service-facing paths repeatedly occupy a smaller feasible-corridor space, while the multi-target references distribute observations over many more coastal directions.

### C. Geography Separates Exposure from Concentration

We compare geography at the country level, giving equal weight to countries represented by different numbers of Root measurements. Following Liu et al. [2], probe countries are grouped as island or archipelagic, landlocked, and other coastal. Each country contributes one pooled DNS exposure observation and the median corridor distribution over its auditable DNS units.

Island and archipelagic countries form the highest-exposure group. Their median country-pooled DNS exposure is 49.61% across 9 countries, compared with 7.88% for 54 other coastal countries and 1.70% for 14 landlocked countries. This ordering describes how frequently observed Root paths enter an inter-region candidate space.

Conditional corridor breadth follows a different ordering. Island and archipelagic countries have a median Top-2 corridor share of 53.3% and 5.58 effective corridors. Other coastal countries reach 75.4% and 3.39. The two represented landlocked countries reach 80.2% and 2.51. Figure 4 presents both distributions together with the contributing country counts.

Across the 38 countries with both pooled exposure and an auditable corridor summary, more frequent entry into the candidate space tends to accompany broader conditional support. Exposure and corridor Top-2 share have a Spearman rank association of $-0.29$; exposure and effective corridor count have the corresponding association of 0.30. The country-level ordering thus follows the geographic group result.

**Figure 4. DNS exposure and corridor concentration by geography.**

[Original figure PDF](figures/fig_country_geography_30km.pdf)

Geography therefore separates exposure from conditional corridor breadth. Island and archipelagic countries enter the candidate space more frequently, yet their candidate-bearing observations span more coastal directions. Other coastal countries enter less frequently and concentrate more strongly once exposure occurs. Exposure records the frequency of submarine involvement; corridor breadth describes the physical directions supporting that involvement.

### D. Cross-Layer Contraction Is Heterogeneous

DNS and application units shift upward more strongly than topology references in the paired network-transition and corridor Top-2 comparison. Figure 5 shows all 370 auditable units. The common 80% lines organize the distributions into four descriptive classes, and the diagonal separates increases in corridor concentration from decreases.

**Figure 5. Network-transition and corridor Top-2 shares.**

[Original figure PDF](figures/fig_cross_layer_distribution.pdf)

Contraction is a recurring service-facing pattern, while broad support at both layers remains the largest service-facing class. Among 275 service-facing units, 81 (29.5%) are network-broad/corridor-concentrated, 158 (57.5%) remain broad at both layers, 18 (6.5%) are concentrated at both, and 18 (6.5%) are network-concentrated/corridor-broad. Four of 95 topology-reference units (4.2%) enter the contraction class; the other 91 remain broad at both layers.

DNS and applications enter the contraction class at similar rates but show different median continuous shifts. The class contains 66 of 222 DNS units (29.7%) and 15 of 53 application units (28.3%). Their median continuous Top-2 shifts are 11.0 and 21.0 percentage points, respectively. Application units cross the 80% boundary at a similar frequency and redistribute more mass toward their two leading corridors. Continuous shifts also reveal substantial narrowing within the broad-broad class.

Continuous metrics identify redistribution toward fewer leading physical directions both within and across the threshold classes. Across the service-facing population, corridor Top-2 share increases in 184 of 275 units (66.9%), and effective category count contracts in 204 (74.2%). Of the 239 units with a broad network distribution, 178 (74.5%) move upward in Top-2 share: 81 cross the concentration threshold, while 97 remain broad at both layers with a median increase of 6.3 percentage points.

Three cases distinguish continuous narrowing, expansion, and changes in absolute breadth from support-relative evenness. Singapore-Netflix moves from 32.5% network Top-2 share to 65.0% corridor Top-2 share, while its effective count contracts from 19.86 to 3.41. It exhibits strong continuous narrowing while remaining below the 80% boundary.

New Zealand-Netflix shows corridor expansion. Its share moves from 63.6% to 37.6%, with effective count expanding from 5.18 to 6.92.

Singapore-H-Root separates absolute breadth from support-relative evenness. Its share moves from 39.6% to 50.1%, and its effective count contracts from 20.67 to 5.99, while normalized entropy changes only slightly.

Repeated overlap among bounded multi-corridor sets produces the aggregate distributions in these cases. Bounded multi-corridor segments account for 99.9% of candidate-bearing observations in Singapore-Netflix, 78.1% in New Zealand-Netflix, and 98.2% in Singapore-H-Root. Under the same projection and aggregation rules, the cases show contraction, expansion, and metric-specific change.

Service-facing measurements enter the inter-region candidate space less often and occupy narrower corridor distributions than the topology references. Within the service-facing population, country-service units span contraction, preservation, and expansion. Network diversity and physical-corridor diversity therefore describe distinct properties of application reachability.

## VI. Measurement Scope and Implications

### A. Resilience and Infrastructure Implications

Routing diversity and corridor breadth capture distinct structures relevant to replica placement, peering, and international connectivity planning. In the service-facing population, 81 units project broad network alternatives onto narrow feasible coastal directions, whereas 158 retain distributed support at both layers. Exposure links service localization and interconnection to the frequency of inter-region access; concentration links landing-region diversification to the breadth of physical support. Together, they locate the country-service populations associated with these structures.

The paired view distinguishes two intervention points. Deploying a closer service instance or changing interconnection can reduce exposure by keeping more paths within a region. Adding access through distinct landing regions can broaden the corridor distribution of paths that continue to cross regions.

### B. Physical Mapping Resolution

The mapping-resolution states retain both single-corridor and bounded multi-corridor observations. Each segment records one state. At 30 km, 57.9% of candidate-bearing segments have one corridor and 42.1% divide unit mass across a bounded set. Segments with no feasible corridor or incomplete construction inputs remain separate in pipeline accounting. Corridor, exact landing-pair, and cable identities remain linked in the outputs, supporting analysis across physical resolutions.

Aggregate concentration combines observation frequency with candidate overlap. Uniform allocation gives each observed segment one total unit of influence. Repeated support for the same corridor accumulates across traces, while segments with several feasible corridors distribute their unit across that finite set.

### C. Landing-Region Resolution Sensitivity

To assess resolution sensitivity, we vary maximum landing-region diameter over 10, 20, 30, 40, and 50 km while holding the 50-km endpoint catchment and 5-ms RTT tolerance fixed. Exact landing-pair and cable candidate sets are identical on baseline-shared segments (mean Jaccard 1.0), isolating corridor grouping resolution.

The single-corridor share is 46.2%, 47.4%, and 54.8% at 10-30 km, rising to 90.1% and 94.8% at 40-50 km. Shared-cohort Top-2 share follows the same transition: 53.6%, 62.8%, and 64.4%, then 81.6% and 84.9%. From 30 to 40 km, these measures increase by 35.3 and 17.2 percentage points as spatial aggregation merges candidate support into fewer corridors. The 10-30-km settings preserve a fine-grained coastal view; the 40-50-km settings form larger regions and concentrate the same landing-pair support.

**Figure 6. Landing-region diameter sensitivity.**

[Original figure PDF](figures/fig_sensitivity_diameter.pdf)

### D. Measurement Scope

Reported quantities are observation-weighted over participating probes in the aligned window; RIPE Atlas probe density varies across countries and networks. DNS Roots and applications form service-specific populations, while MSM 5051 and 5151 retain dynamic multi-target populations as topology references. Anycast observations integrate deployed footprint, BGP selection, interconnection, and source-network context.

The primary corridor distribution includes domestic and international inter-region candidates, with the corresponding label retained per segment. All measurements cover 00:00-01:00 UTC on July 1, 2026 and align with IP, AS, cable-lifecycle, and deployment metadata.

Corridor concentration quantifies geographic candidate support. Cable multiplicity, landing-station redundancy, hazard correlation, rerouting capacity, and repair processes supply additional operational dimensions.

The snapshot provides a common temporal basis across all service families. Repeating the aligned construction at the same country-measurement granularity can track changes caused by routing, service deployment, or cable lifecycle events.

### E. Ethics and Reproducibility

The study uses archived public RIPE Atlas measurements and infrastructure metadata and reports aggregate country-measurement statistics. The released measurement IDs, configuration values, resolution states, pipeline counts, and scripts reconstruct the primary tables and figures from versioned inputs.

## VII. Conclusion

We presented an application-aware cross-layer audit that compares network transitions and feasible submarine corridors over identical segment populations. The framework applies geographic, lifecycle, and propagation feasibility to atomic traceroute segments and distributes each segment's observation mass uniformly across its feasible corridors.

Across 490,911 valid traceroutes, the 30-km analysis identifies 124,350 inter-region candidate-bearing segments and 370 auditable country-measurement units. DNS Roots and applications have median effective corridor counts of 3.84 and 3.51, compared with 18.01 for the multi-target topology references. Under the descriptive Top-2 threshold, 81 of 275 service-facing units exhibit network-broad/corridor-concentrated structure, compared with 4 of 95 topology-reference units; 158 service-facing units remain broad at both layers.

These measurements show that application reachability frequently occupies a narrower feasible physical-corridor space than its network-transition representation, with substantial variation across countries and services.

## VIII. Use of AI Disclosure

OpenAI ChatGPT and Codex assisted with code development, plotting scripts and language revision. Their contribution was limited to these tasks, and the authors validated the outputs against the source data and analysis results.

## References

[1] TeleGeography. Submarine Cable Map. 2026. https://www.submarinecablemap.com/.

[2] Liu, Shucheng and Bischof, Zachary S and Madan, Ishaan and Chan, Peter K and Bustamante, Fabián E. Out of sight, not out of mind: A user-view on the criticality of the submarine cable network. Proceedings of the ACM Internet Measurement Conference. 2020. 194–200.

[3] Ye, Honglin and Wang, Shuai and Li, Dan. Impact of International Submarine Cable on Internet Routing. IEEE INFOCOM 2023-IEEE Conference on Computer Communications. 2023. 1–10.

[4] Ramanathan, Alagappan and Abdu Jyothi, Sangeetha. Nautilus: A Framework for Cross-Layer Cartography of Submarine Cables and IP Links. Abstracts of the 2024 ACM SIGMETRICS/IFIP PERFORMANCE Joint International Conference on Measurement and Modeling of Computer Systems. 2024. 101–102.

[5] Wang, Caleb and Zhang, Ying and Dong, Qianli and Carisimo, Esteban and Durairajan, Ramakrishnan and Bustamante, Fabián E. Threading the Ocean: Mapping Digital Routes Across Submarine Cables using Calypso. Proceedings of the ACM SIGCOMM 2025 Conference. 2025. 1260–1262.

[6] Durairajan, Ramakrishnan and Ghosh, Subhadip and Tang, Xin and Barford, Paul and Eriksson, Brian. Internet atlas: A geographic database of the internet. Proceedings of the 5th ACM workshop on HotPlanet. 2013. 15–20.

[7] Anderson, Scott and Salamatian, Loqman and Bischof, Zachary S and Dainotti, Alberto and Barford, Paul. iGDB: connecting the physical and logical layers of the internet. Proceedings of the 22nd ACM Internet Measurement Conference. 2022. 433–448.

[8] Bischof, Zachary S and Rula, John P and Bustamante, Fabián E. In and out of cuba: Characterizing cuba's connectivity. Proceedings of the 2015 Internet Measurement Conference. 2015. 487–493.

[9] Bischof, Zachary S and Fontugne, Romain and Bustamante, Fabián E. Untangling the world-wide mesh of undersea cables. Proceedings of the 17th ACM workshop on hot topics in networks. 2018. 78–84.

[10] Fanou, Rodérick and Huffaker, Bradley and Mok, Ricky and Claffy, Kimberly C. Unintended consequences: Effects of submarine cable deployment on Internet routing. International Conference on Passive and Active Network Measurement. 2020. 211–227.

[11] Durairajan, Ramakrishnan and Barford, Paul and Sommers, Joel and Willinger, Walter. InterTubes: A study of the US long-haul fiber-optic infrastructure. Proceedings of the 2015 ACM conference on special interest group on data communication. 2015. 565–578.

[12] Carisimo, Esteban and Wang, Caleb J and Weaver, Mia and Bustamante, Fabián E and Barford, Paul. A hop away from everywhere: A view of the intercontinental long-haul infrastructure. Proceedings of the ACM on Measurement and Analysis of Computing Systems. 2023. 1–26.

[13] Ramanathan, Alagappan and Sankaran, Rishika and Abdu Jyothi, Sangeetha. Xaminer: An Internet Cross-Layer Resilience Analysis Tool. Proceedings of the ACM on Measurement and Analysis of Computing Systems. 2024. 1–37.

[14] Cicalese, Danilo and Augé, Jordan and Joumblatt, Diana and Friedman, Timur and Rossi, Dario. Characterizing IPv4 anycast adoption and deployment. Proceedings of the 11th ACM Conference on Emerging Networking Experiments and Technologies. 2015. 1–13.

[15] De Vries, Wouter B and de O. Schmidt, Ricardo and Hardaker, Wes and Heidemann, John and de Boer, Pieter-Tjerk and Pras, Aiko. Broad and load-aware anycast mapping with verfploeter. Proceedings of the 2017 Internet Measurement Conference. 2017. 477–488.

[16] RIPE NCC. RIPE Atlas. 2026. https://atlas.ripe.net/.

[17] IPinfo. IP Geolocation and ASN Databases. 2026. https://ipinfo.io/.

[18] CAIDA. AS Relationships Dataset. 2026. https://www.caida.org/catalog/datasets/as-relationships/.
