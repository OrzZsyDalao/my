# 需作者确认的位置

本清单与修订正文分开。原稿数字、方法和判断强度按要求保留；此处仅定位材料对应、逻辑或证据问题，不把未提供事实写入论文。

## Q01 · IEEE-conference-template-062824.tex:36

**定位片段：** `showing that service selection`

摘要由测量组差异推至 service selection and deployment must be retained，并以 shapes 描述 deployment/target selection 的作用。现有比较的目标总体不同；这些因果或必要性措辞的证据强度需作者确认。原判断保留。

## Q02 · files/2-background.tex:9

**定位片段：** `these logical paths depend`

对 geographically separated regions 的路径统一使用 depend on submarine cables。该句范围与是否存在其他物理连接解释之间的关系未在本段说明；原句判断保留。

## Q03 · files/3-framework.tex:69

**定位片段：** `A candidate is`

Geographic and delay feasibility 使用相邻可见 hop 的 RTT 差作候选可行性条件。正文未在此给出该差分对应物理往返传播下界的条件或验证；公式及判断原样保留。

## Q04 · files/3-framework.tex:198

**定位片段：** `Direction is preserved throughout`

这里的 Direction is preserved throughout the aggregation 与前文 direction-independent corridor 可能产生歧义。所在段讨论 network-side distribution，但 throughout 的指代范围需作者确认；未改写。

## Q05 · files/5-result.tex:38

**定位片段：** `Country-matched comparisons show`

国家匹配保留了源国家，但测量目标总体发生变化。此处与摘要、讨论中的部署解释如何对应，需要作者确认；本轮未增加探针或目标层面的控制事实。

## Q06 · files/5-result.tex:197

**定位片段：** `Contraction is a recurring`

四类结果使用论文的 Top-2=80% 分类。与仓库 paper_primary_units.csv 逐行比较，28 行分类标签不同，连续字段一致；仓库分类函数使用混合分级。81 个收缩单位相同，其他类别不同。正文原有四类计数全部保留。

## Q07 · files/5-result.tex:236

**定位片段：** `Repeated overlap among bounded`

原文使用 produces 将候选重叠与案例聚合分布连接。本轮只将该句提前；未补充独立的重叠分解、机制检验或最坏情形证明。

## Q08 · files/6-measurement-scope-and-implications.tex:16

**定位片段：** `The paired view distinguishes`

关于部署更近实例、改变互联、增加不同登陆区域接入的两项 can 判断属于原稿的干预含义。本轮未增加实际干预实验或效果数据，原强度保留。

## Q09 · files/6-measurement-scope-and-implications.tex:41

**定位片段：** `To assess resolution sensitivity`

原稿称 mean Jaccard 1.0 隔离 corridor grouping resolution。仓库敏感性结果在直径变化时，进入主要分布的片段数及审计单位数也变化；且该结果来自 A-Root 子集。原段与数字原样保留，未替作者修正其解释。

## Q10 · files/6-measurement-scope-and-implications.tex:47

**定位片段：** `The single-corridor share is`

原稿按 10–30 km 顺序列出 46.2%、47.4%、54.8%。仓库敏感性 CSV 的 10 km 与 20 km 对应值顺序相反。正文没有交换或改写这些数字，供作者确认来源版本。

## Q11 · files/4-datasets.tex:4

**定位片段：** `All inputs are aligned`

原稿将全部辅助数据表述为与 July 1, 2026 对齐。当前材料中的版本标签与实际文件获取时间、有效期和完整来源链需要一一对应；本轮未替作者增加来源事实。

## Q12 · files/6-measurement-scope-and-implications.tex:90

**定位片段：** `The released`

原文说发布材料 reconstruct 主表与图。仓库记录存在部分阶段提交 unknown、生成时工作树 dirty 及分类不一致。这里只定位复现表述的对应位置；不将本轮文本静态核对写成全流程复现。

## Q13 · files/2-background.tex:66

**定位片段：** `Calypso combines`

此处及 refs.bib 仍为 wang2025calypso。遵守本轮不新增文献与保留引文编号的要求，未替换成 2026 长文，也未加入其新功能或验证结果。
