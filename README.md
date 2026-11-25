# 阻挡摘要法（BlockLift）

阻挡摘要法用于求解**令牌跳跃下的独立集重构**。给定一张无向图，以及大小相同的起点和目标独立集，每一步把一个令牌从当前顶点移到一个空顶点，移动后仍须保持独立。我们要判断能否到达目标，并在可达时给出一条尽可能短的合法路径。

## 方法思想

**块内有很多种令牌摆法，块外真正关心的是这些摆法会阻挡哪些落点，以及块内能否在需要时切换摆法。** 比如，目标顶点与某个块相邻时，跨块决策要知道这个顶点当前是否被堵住，以及块内能否通过一串合法移动腾出它。

1. **提取阻挡摘要。** 在适用的图结构中分块，记录对外阻挡关系、块内连通性，以及恢复合法移动所需的信息。
2. **搜索相容的摘要。** 在摘要层寻找能够衔接的局部变化。对于重复的链式结构，可用带权摘要比较恢复后的移动步数。对于缺少可利用结构的输入，使用通用搜索。
3. **还原并验证路径。** 将摘要层的选择还原到原图，检查每步是否合法、最终能否到达目标。长路径也可用可验证的压缩见证表示。

## 快速上手

参考环境为 Windows、Python 3.14.2、NumPy 2.4.3 和 SciPy 1.18.1。以下命令在仓库根目录运行。求解在本地完成，无需模型或 API 密钥。

    python -m pip install -r requirements.txt
    python -X utf8 "正式实验/78_最终求解器.py" examples/tiny.col examples/tiny.dat --output example-result.json
    python -X utf8 "正式实验/78_最终求解器.py" examples/tiny.col examples/tiny.dat --verify example-result.json

示例的解为一步。图文件用 DIMACS 风格的 `p` 和 `e` 行，端点文件用 `s` 和 `t` 行，顶点从 1 编号。可用 `--moves-out moves.txt` 导出经验证的逐步移动，用 `--family generic` 对自定义图选用通用策略。

## 复现 CoRe 693 例实验

    python -X utf8 download_benchmark.py
    python -X utf8 run_benchmark.py --seconds 15 --output reproduction.jsonl

下载脚本从固定提交获取清单所需的输入，预留约 300 MB。批量脚本直接解压并运行原始实验源码包。中断后，用相同预算和输出文件重跑即可续跑。 [数据来源](https://github.com/TakehideSoh/KR2026/tree/df807b6b6ea66b7ec37a5371c58967eecc5ce762/benchmark) · [固定实验源码包](artifacts/BlockLift-v2.zip)

源码包 SHA-256 为 `9d6371b3045c18f7641c62cd165d2b80fca6860c6ed74459f24b020d79348fa0`。15 秒是程序内搜索预算，解析输入和验证见证单独计时。原始运行有 5 例在 15 秒后返回，最晚为 15.584 秒。设备不同可能影响耗时和限时搜索结果。

| 参考实验结果 | 实例数 |
|---|---:|
| 找到并验证合法路径 | 627 |
| 证明不可达 | 66 |
| 未判定或运行错误 | 0 |

## 实验记录

- [693 例逐例结果与见证](results/blocklift-v2-15s.jsonl) · [逐例对照表](results/blocklift-v2-per-instance.csv)
- [与 CoRe 官方记录及四篇论文的对比](reports/comparison.md)
- [统一预算实验报告](reports/frozen-v2.md) · [七例取消总时限的补充记录](reports/seven-uncapped.md)

复现命令对应统一预算的 693 例实验。累计最佳对照还使用了历次搜索和七例复跑留下的记录。
