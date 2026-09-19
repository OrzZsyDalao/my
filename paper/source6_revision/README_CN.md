# Source6 全文修订版

本次交付以 `When_Network_Diversity_Narrows_at_Sea_INFOCOM2027_Source6 (1).zip` 中的英文正文为基准，完成摘要至结论的 75 处段落级修改。没有按九页篇幅压缩，也没有为扩写增加新事实。处理日期：2026-09-12。

## 跨 AI 会话入口

当前 IMC 2027 重构工作的权威文件顺序、主张、已确认决定和待办统一记录在 [AI_HANDOFF.md](AI_HANDOFF.md)。使用新的 AI 会话继续修改前，应先读取该文件和 [IMC2027_STORY_SPEC.md](IMC2027_STORY_SPEC.md)。新的 IMC 初稿已写入独立的 `IMC2027-overleaf.tex` 与 `imc/*.tex`；原 `files/*.tex` 继续保留为 INFOCOM 历史版本。

## IMC 2027 初稿与 Overleaf 包

当前权威完整初稿位于 `revised_source6_imc_full_source/`，它以 `revised_source6.zip` 原文为底稿并整合现有 draft。`revised_source6_imc_full_draft.zip` 可直接上传到 Overleaf；上传后将 `IEEE-conference-template-062824.tex` 设为 Main document，并使用 pdfLaTeX 与 BibTeX。预览文件位于 `output/pdf/revised_source6_imc_full_draft.pdf`。此前的 `IMC2027-overleaf.tex` 保留为精简结构稿，不再作为完整初稿。

逐段中文阅读版为 `revised_source6_imc_full_zh_translation.docx`，同时保留可检索和继续编辑的 `revised_source6_imc_full_zh_translation.md`。中文版本用于通读，不替代英文 LaTeX 权威稿。

2026-09-19 版本在不新增实验的前提下补充了均匀分配结果的国家聚类 bootstrap 与国家标签置换检验，明确了三种分配规则的队列差异，并收紧了 30 km 空间分辨率、单小时快照和地理机制的解释边界。均匀分配的 0.461 组间差值 95% 区间为 [-0.213, 0.902]，双侧 p=0.161，因此论文只报告描述性地理差异，不作显著性判断。复现材料位于 analysis/。
## 先阅读什么

1. [完整英文修订稿](MANUSCRIPT_REVISED.md)：包含摘要、全部章节、公式、表格、原图链接和参考文献。阅读版不替代 LaTeX 排版源文件。
2. [逐处修改说明](REVISION_NOTES_CN.md)：每项列出原文、修订文、为什么修改，以及修改的意义与作用。
3. [需作者确认的位置](REVIEW_LOCATIONS.md)：单独定位证据、逻辑与材料一致性问题。没有将这些问题的推测性答案加入正文。
4. [LaTeX 入口](IEEE-conference-template-062824.tex)：与 `files/`、`figures/`、`refs.bib`、`IEEEtran.cls`、`IEEEtran.bst` 一起构成修订版源文件。

## 本轮如何落实整体大纲

主线为：同一观测总体的网络与走廊比较 → 完整可行集合的观测质量聚合 → 国家与服务之间的分布差异。摘要、引言和结果节开头直接说明研究问题；方法节突出完整候选集合和同总体构造；案例段首先说明其解释的性质，再列数据。

原稿的章节、研究问题、图表和引文出现顺序保持不变。此前大纲建议的结果小节重排和新 RQ 未直接采用，因为本轮要求完整保留编号、研究对象和方法；通过段首主题句及衔接落实论证重点，而不改变这些固定内容。

## 为什么这样修改

| 修改类型 | 原文阅读负担 | 本次处理 | 改进作用 |
| --- | --- | --- | --- |
| 观点前置 | 数据堆叠后才交代含义 | 将原段已有结论移到段首 | 读者先知道要核对的发现，再读取证据 |
| 一段一个意思 | 规模、分组、阈值和结果混在一起 | 分开方法定义、统计总体和解释 | 降低分母及比较对象的混淆 |
| 主动具体动词 | 被动结构使步骤不清楚 | 使用 compare、construct、allocate、record、measure | 操作与产出可对应 |
| 案例拆段 | 三个案例在长段中频繁切换 | 每个案例先点明已有性质，再给数值 | 连续收缩、扩张与指标差异更容易区分 |
| 合并复述 | 段末重复段首或前段定义 | 保留一次完整解释，删除无信息量引导 | 论证推进更直接 |
| 正文与审阅分开 | 编辑意见可能改变作者判断 | 原强度留在正文，问题另列 | 审阅透明，同时不擅自修补结论 |

## 保留与检查

- 所有 LaTeX 文件的数字 token 多重集合与原稿一致：包括重复出现的数值，未新增或删除。
- 所有内联数学、展示数学和 equation 环境内容及顺序与原稿一致。
- 所有 figure/table 环境内容及顺序与原稿一致；图像文件未修改。
- 所有引文调用内容和顺序、标签顺序、引用目标及章节标题顺序与原稿一致。
- 原有研究对象、日期、单位、方法和 may/can 等判断强度进行了逐段核对。词面自动检查不替代语义判断。
- `refs.bib`、模板文件及图像与原压缩包进行哈希核对。
- 没有新增实验、数据、文献或机制。Calypso 保留原稿的 2025 年引用及事实。

静态检查结果见 [preservation_audit.json](editorial/preservation_audit.json)。逐行差异见 [revision.diff](editorial/revision.diff)。原始正文快照保留在 `original/`，用于比较，不是独立排版工程。

## 排版与打包

`revised_source6.zip` 包含修订后的 LaTeX 入口、全部章节、原图、参考文献和模板，可导入 LaTeX 编辑环境。选择 `IEEE-conference-template-062824.tex` 为主文件，使用 pdfLaTeX 与 BibTeX。

本机没有系统 LaTeX 发行版，已在 `.local-tools/` 内置 Tectonic 0.17.0 及其缓存，用于本地排版核对。当前已编译出 10 页 PDF，无报错、无未定义引用、无 overfull 溢出。

```powershell
powershell -NoProfile -File compile.ps1            # 生成 build/IEEE-conference-template-062824.pdf
powershell -NoProfile -File compile.ps1 -Preview   # 同时输出逐页 PNG 到 build/preview/
powershell -NoProfile -File compile.ps1 -Offline   # 只用本地缓存，不访问网络
powershell -NoProfile -File compile.ps1 -AsShipped # 完全按压缩包原样编译，不加字体 shim
```

脚本先把入口、`files/`、`figures/`、`refs.bib` 与模板暂存到 `build/src/` 再编译，交付的源文件保持与压缩包逐字节一致。

默认编译会在暂存副本中加入 `\usepackage[T1]{fontenc}`。原因是 Tectonic 的字体包缺少 `TUptm.fd`，IEEEtran 在 Unicode 编码下会静默回退到 Latin Modern，并丢失全部粗体与斜体（标题、章节标题、Abstract、Index Terms、RQ 标签都会变成常规字重）。加上 T1 编码后 Times 的常规／粗体／斜体／粗斜体四种字形都能正确解析。用 `-AsShipped` 可复现回退效果作为对照。该 shim 只作用于本机 Tectonic 预览流程；排版后的 PDF 与源文件本身无关，正式的 pdfLaTeX 目标环境不受影响。

正式投稿前仍应在目标环境编译并检查分页及浮动体位置。

## 重建本次编辑记录

在仓库根目录执行：

```text
python paper/source6_revision/editorial/revise.py
python paper/source6_revision/editorial/package_review.py
```

第一步会根据原始快照重建本轮修订；后续人工编辑前应注意保留修改。第二步执行静态检查并生成阅读稿、对照记录和位置清单。
