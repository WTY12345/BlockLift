# 阻挡摘要法与 CoRe 官方及四篇论文的对照

逐例比较来自同一轮 CoRe 693 例统一预算实验。步数列以公开记录为参照。

## 官方及四篇论文逐例对照

| 公开来源 | 可比范围 | 公开路径数 | 阻挡摘要法覆盖 | 更短 / 等长 / 更长 |
|---|---|---:|---:|---:|
| CoRe 官方逐例最佳 | 693 例清单；汇总已归档的 2022/2023 赛道 | 568 | 568 | 6 / 555 / 7 |
| SRIP 主配置（KR 2026） | 693 例，v47-d1-d2 | 477 | 477 | 0 / 477 / 0 |
| Scalable Hard Instances（SEA 2024） | 105 例输入及日志对齐；三种求解器逐例取最佳 | 98 | 98 | 0 / 98 / 0 |
| ZDD 最短重构框架（CPAIOR 2023） | 论文长时实验中可精确对齐的 sp019 | 1 | 1 | 0 / 1 / 0 |
| 改进 ASP 编码（JSAI 2025） | 表 3 无提示配置，共 20 例，含 2 项不可达 | 18 | 18 | 0 / 18 / 0 |
| 全来源公开最佳并集 | 官方、作者 CSV 与以上可核验的论文记录 | 575 | 575 | 6 / 562 / 7 |


官方逐例最佳取所有已归档赛道的最短可执行路径，允许不同实例来自不同配置。它是逐例参考，不能当作一个统一预算的求解器。四篇论文有不同评估范围，表中只对齐能逐例核验的路径。公开步数比对与全局最短性证明分列。

## 论文实验的补充口径

- **SRIP，KR 2026。** 论文主配置在 693 例上报告 477 个最短解；阻挡摘要法达到全部 477 个长度。作者另有 7 个 SRIP 配置。[论文](https://proceedings.kr.org/2026/72/) · [作者 CSV](https://github.com/TakehideSoh/KR2026/blob/main/benchmark/all_results.csv)
- **Scalable Hard Instances，SEA 2024。** 105 个同输入且有日志的实例上，SAT、ZDD 与 recon 分别有 90、37、33 条验证路径。论文行采用三者逐例并集，避免重复计数。[论文](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SEA.2024.26) · [作者日志](https://github.com/TakehideSoh/Scalable-Hard-ISR/tree/8eef0ef8fec53beed2e3ccf7f1e24b0337fb1e3f/logs)
- **ZDD 最短重构框架，CPAIOR 2023。** 可逐例对齐的代表是 sp019，双方都交付 5,767,157 步。原论文报 151,567 CPU 秒。[论文实验节](https://arxiv.org/html/2207.13959#S5)
- **改进 ASP 编码，JSAI 2025。** 论文的最佳配置在 369 例中判定 240 例，含可达与不可达。表 3 可核验的 18 条路径和两项不可达都在 阻挡摘要法结果中得到同样结论。[论文](https://www.jstage.jst.go.jp/article/pjsai/JSAI2025/0/JSAI2025_4R1OS1302/_article/-char/en)
- **官方成绩。** 2023 总体组和单引擎组采用各赛道评分。这里从逐例答卷取路径长度，用于与阻挡摘要法对齐。[2022 官方成绩](https://core-challenge.github.io/2022result/) · [2023 官方成绩](https://core-challenge.github.io/2023result/)

本次求解覆盖全部 575 条已核对的公开可达记录，并为另外 52 例交付合法路径。各公开来源的硬件、时限和输出方式不同，表格比较的是逐例覆盖和路径长度。

[统一预算实验](core-693.md) · [逐例结果表](../results/core-693-per-instance.csv)
