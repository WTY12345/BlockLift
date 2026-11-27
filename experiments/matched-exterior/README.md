# BlockLift 审稿复核包 / Review artifact

[![简体中文](https://img.shields.io/badge/%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-%E5%BD%93%E5%89%8D-246C9B)](README.md) · [![English](https://img.shields.io/badge/English-Read%20in%20English-555555)](README.en.md)

The archive contains the full independent CoRe run used in §6.2 and the raw matched-exterior measurements used in §6.4. The verification and benchmark scripts use the Python standard library. Figure generation uses Matplotlib. Reference runs used Python 3.14.2 on Windows 11 with an Intel Core Ultra 9 275HX. Run commands from this directory.

## 重算论文表格 / Rebuild the tables

以下命令直接读取随附数据，无需联网。两份原始 CoRe 输入的 SHA-256 记录在汇总中。计算得到的文件写入新建的 checked 目录。

~~~text
python -X utf8 core_reproduction_table.py --run data/reproduced-core-693.jsonl --references data/public-reference.csv --audit data/audit-summary.json --output-dir checked
python -X utf8 summarize_matched.py --original data/matched-original.jsonl --same-objective data/matched-core-only.jsonl --large-cap data/matched-large-cap.jsonl --output checked/matched-summary.json
~~~

§6.2 的 693 例来自同一份第二轮独立运行 JSONL。公开参照 CSV 提供每例的公开最佳、作者精确参照及端点下界。生成表按例给出见证形式、总长度、公开比较结果、最短性证据类别与求解时限。期望汇总为 490 个显式见证、137 个压缩见证、66 个不可达，在 575 个有公开步数的实例上得到 6 短、563 平、6 长。

§6.4 主比较的数据为 matched-core-only.jsonl。每例含隐式算法与同目标 A* 的三轮耗时中位数、完成状态、已生成配置数、路径长度和另行测量的峰值 Python 分配。matched-original.jsonl 保留含第二目标的先前对照。matched-large-cap.jsonl 记录两个难例在更高预算下的补充测量。

At 20,000 and 200,000 discovered states, the core-only baseline completes 37 and 38 of 40 cases within the one-second budget. In the targeted follow-up with five seconds and one million states, it completes the 1,024-pair detour in all three runs and reaches the state cap on the 256-pair locked control. The allocation-profiling runs for these two cases reach their separate timeout, so their recorded memory peaks describe partial searches.

## 重绘图 4 / Regenerate Fig. 4

在已安装 Matplotlib 的 Python 环境运行下列命令。脚本只读随附的同目标和高预算日志，生成 PDF 和 EPS。实线与虚线只连接完成数据，叉号表示触限时的停止时间，空心方块表示放宽预算后的完成时间。

~~~text
python -X utf8 plot_matched_scaling.py --output Fig4
~~~

## 独立核验 CoRe 路径和不可达结论 / Replay the CoRe witnesses

~~~text
python -X utf8 download_benchmark.py
python -X utf8 verify_paper_witnesses.py
~~~

下载脚本固定使用上游提交 df807b6b6ea66b7ec37a5371c58967eecc5ce762。已有同版本输入时，可以跳过下载，在核验命令后加上 --inputs 与数据目录。核验器重放显式路径及压缩见证，核验方格和鸽笼证书，并在一个小图上重新穷尽搜索。原始求解程序固定为 BlockLift 提交 428f21983f234cc6cd16c948471fb68dcb2235ef。

## 重跑定理 4 实验 / Rerun the matched-exterior experiments

~~~text
python -X utf8 matched_core_only.py --seconds 1 --repeats 3 --caps 20000 200000 --output matched-core-only-rerun.jsonl
python -X utf8 matched_core_only.py --seconds 5 --caps 1000000 --select frozen:256 detour:1024 --output matched-large-cap-rerun.jsonl
python -X utf8 matched_exterior_experiment.py --output matched-original-rerun.jsonl
~~~

实验脚本自行生成固定种子的实例。计时不含逐步重放，计数上限与提前结束原因保存在日志中。不同机器上的耗时、内存及接近截止时间的完成数可能不同。建议使用新输出文件名来重跑。
