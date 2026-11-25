# 阻挡摘要法（BlockLift）

阻挡摘要法求解**令牌跳跃下的独立集重构**。核心做法是把局部状态的对外阻挡关系和局部连通性保留下来，在较小的状态图中搜索，再把走法还原成原图上的合法移动。对满足结构条件的实例，摘要用于精确判定可达性。通用分支也用阻挡信息生成候选，但限时搜索可能返回未判定。

## 1. 问题与单步阻挡

给定无向简单图 $G=(V,E)$ 和两个大小同为 $k$ 的独立集 $S,T$，令

$$
\mathcal I_k(G)=\{I\subseteq V:|I|=k,\ E(G[I])=\varnothing\}.
$$

重构图以 $\mathcal I_k(G)$ 为顶点。两个状态相邻，当且仅当各自恰好有一个顶点不在对方中。设 $N(X)=\bigcup_{x\in X}N_G(x)$。从当前状态 $I$ 移走 $u\in I$ 后，剩余集是 $R=I\setminus\{u\}$。合法落点满足

$$
v\notin I,\qquad v\notin N(R).
$$

实现用整数位集存储 $I$ 和邻域。令 $b_I(v)=|N_G(v)\cap I|$。若 $b_I(v)=0$，任何令牌都能跳到 $v$。若 $b_I(v)=1$，必须移开唯一阻挡它的令牌。若 $b_I(v)\ge 2$，一步跳跃无法腾出 $v$。通用束搜索用这两类可行候选推进，搜索宽度和分支限制影响其覆盖率。

## 2. 饱和分块与边界连通摘要

把顶点划分为 $B_1,\dots,B_m$，令 $a_i=\alpha(G[B_i])$。结构分支先核对容量。若 $k=\sum_i a_i$，任一合法状态在块 $B_i$ 恰好占 $a_i$ 个顶点。任何跨块跳跃都会使接收块超过容量，因此只需考虑块内移动。

处理前缀 $P_i=\bigcup_{j\le i}B_j$ 时，前缀配置 $X$ 的对外标签为

$$
\lambda_i(X)=N(X)\cap(V\setminus P_i).
$$

对同一标签 $\lambda$，只收缩该标签诱导的前缀重构图中的**同一连通分量**。两个同标签的配置仍可能无法在标签保持不变时互相到达。商图边保留实际跨分量边作为还原见证。完全枚举的最后一层对外标签为空，端点落入同一商分量恰好表示可达。

合并下一块时，枚举前缀分量 $C$ 和新块独立集 $Y$，只保留 $Y\cap\lambda_i(C)=\varnothing$ 的组合。其新标签为

$$
(\lambda_i(C)\cup N(Y))\cap(V\setminus P_{i+1}).
$$

乘积图的一条边只改变前缀分量或新块配置。固定新块配置时，同一前缀分量内的走法始终与新块兼容，因此可以用内部连接和保存的跨分量边还原商图路径。对某些结构，实现只保留从起点前缀可达的部分。

设 $q_{i-1}$ 是合并前的分量数，$\ell_i$ 是第 $i$ 块的局部配置数。朴素兼容筛选至多检查 $q_{i-1}\ell_i$ 对。给定显式乘积图后，按标签做连通收缩的扫描代价为 $O(|V_{\rm prod}|+|E_{\rm prod}|)$，另计标签和位集运算。块顺序会改变中间状态数。实现试用原序、逆序、较小活跃边界的贪心顺序和按补边数选择的消去顺序。最坏情况下中间状态量仍可能是指数级。 [边界收缩](blocklift/boundary_contraction.py) · [候选块顺序](blocklift/block_order.py)

## 3. 一个空额与一般跨块移动

若 $\sum_i a_i-k=1$，每个状态恰有一个空额块 $B_h$。在第 $h$ 层，只用保持空额位置的块内跳跃构建连通分量。跨块跳跃必须把令牌跳入 $B_h$，空额随后转移到令牌来源块。外层搜索以层内分量为顶点，用真实跨块跳跃作边，并保存层内父指针和跨层边的端点。外层首次到达目标分量可最小化跨块跳跃次数。还原后的总步数另受每层内部走法影响。

更一般的未饱和情况，可用块外邻域并集排除冲突，或直接按公共剩余集搜索。对任一大小为 $k-1$ 的独立集 $R$，它的所有可行扩展 $R\cup\{v\}$ 在重构图中构成一个团。双向搜索每侧只枚举一次同一个 $R$ 的扩展，而无需对每两个扩展单独检查邻接。 [单空额分层](blocklift/single_vacancy.py) · [跨块双向搜索](blocklift/cross_block_search.py) · [剩余集枚举](blocklift/residual_sets.py)

## 4. 路径还原与带权摘要

可达性收缩会隐藏块内距离。还原时按相反顺序展开各层。在给定一层及其抽象轨迹的条件下，若下一步从分量 $C_i$ 跨到 $C_{i+1}$，令当前分量内的位置为 $x$，真实跨边为 $u\to v$。设 $d_{C_i}(x,u)$ 是分量内最短距离，则

$$
F_{i+1}(v)=\min_{\substack{x\in C_i,\ (u,v)\in E_{\rm prod}\\
u\in C_i,\ v\in C_{i+1}}}
\bigl(F_i(x)+d_{C_i}(x,u)+1\bigr).
$$

最后加上到本层目标的分量内距离，再沿记录的选择回溯。实现对每个压缩片段和入口缓存可能的出口及其费用。这个最小化针对**本层给定的抽象轨迹**。原图全局最短还需要额外证明。 [显式还原](blocklift/explicit_lifting.py) · [带权还原](blocklift/weighted_lifting.py)

超长路径用由移动节点和顺序拼接节点组成的有向无环图表示。对每个片段计算四元组 $(P^+,P^-,\Delta,L)$，分别为执行前必须占用的集合、必须为空的集合、占用翻转集合和长度。单步 $u\to v$ 的摘要为

$$
(\{u\},\ \{v\}\cup(N_G(v)\setminus\{u\}),\ \{u,v\},\ 1).
$$

拼接片段时，第二段的前置条件按第一段的 $\Delta$ 反推到初始状态。落在 $\Delta$ 中的顶点交换“占用”与“为空”要求。合并全部要求并检查无冲突，翻转取对称差，长度相加。根片段要求 $P^+\subseteq S$、$P^-\cap S=\varnothing$ 且 $S\triangle\Delta=T$。核验可以按节点和引用遍历，无需逐步展开。显式导出 $L$ 步仍需 $\Omega(L)$ 的输出量。 [压缩见证与验证](blocklift/compressed_witness.py)

## 5. 结构识别与分支

| 分支 | 摘要与求解条件 |
|---|---|
| [闭邻域商图](blocklift/twin_quotient.py) | 按 $N_G[u]=N_G[v]$ 划类。每类内部是团，类间邻接一致。状态只记录占用了哪些类，搜索后还原原始顶点代表并对齐目标。 |
| [SAT 构造投影](blocklift/sat_projection.py) | 识别变量块和约束块后保留变量选择 $x$。对约束块 $Q$，记 $A_Q(x)$ 为配置 $x$ 下可占用的落点。一项变量从 $x$ 翻到 $y$，要求每个受影响的 $Q$ 都满足 $A_Q(x)\cap A_Q(y)\ne\varnothing$。这样约束令牌可以先到两侧都可用的位置，再翻变量。 |
| [鸽笼结构与匹配](blocklift/pigeonhole_matching.py) | 核对图和端点后，将打开中转点所需的配置转成行到列的注入 $\pi$。行数大于列数时不可达。可行时用最小费用匹配最小化 $\sum_i c_{i,\pi(i)}$，其中费用来自行约束换位与列冲突清理。按配置中转再逆序恢复。 |
| [方格奇偶证书](blocklift/compressed_witness.py) | 针对满足证书条件的偶边长方格和相反纯奇偶端点，按 $2\times2$ 分块，用空额 $d=|V|/2-k$ 限制多数占用色的变化。实现核对全图邻接、端点奇偶和 $(\mathrm{side}/2)^2>2d^2$ 等前提。 |
| [皇后图](blocklift/queen_search.py) | 先核对原图确为行、列、两条对角线攻击关系。维护四类占用掩码，移走皇后后枚举空行与空列的交点，筛掉对角线冲突。先找路径，再对窗口改短，必要时完整检查更短步数界。 |
| [通用调度](blocklift/orchestrator.py) | 根据图族与结构检查试用专用分支，配合阻挡束搜索、公共剩余集双向搜索及限时改短。实例名仅用于挑选候选分支。 |

对 SAT 投影，给定变量路线 $x_0,\dots,x_t$，约束块每一步的可选落点是 $A_Q(x_i)\cap A_Q(x_{i+1})$。块内的动态规划递推为 $D_{i+1}(v)=\min_u(D_i(u)+[u\ne v])$，另计首尾为匹配指定端点所需的移动。给定路线的恢复代价为 $O(t\sum_Q |Q|^2)$。若完整投影分量是一棵树，必经变量轨迹唯一。实现据此把必须的变量翻转与约束块最少移动合成最短性证明。 [SAT 投影及恢复](blocklift/sat_projection.py)

## 6. 合法性、最短性和预算

- `found` 表示已交付并验证原图路径，可另用 `--verify` 复核。
- `unreachable` 来自满足结构前提的证书，或完成搜索后证明端点不连通。搜索预算耗尽、节点超限等返回未判定类结果。
- 路径的通用下界是 $|T\setminus S|$，因为每步最多加入一个缺失的目标顶点。达到此下界时可证明最短。皇后图限长搜索使用 $h(I)=|T\setminus I|$ 剪枝，只有完整核验排除所有更短路径时才据此认证。特定结构也可给出独立下界。对照公开最佳长度与证明全局最短分别记录。 [命令行验证](blocklift/cli.py) · [限长搜索](blocklift/queen_refinement.py)

## 7. 运行与复现

参考环境为 Windows、Python 3.14.2、NumPy 2.4.3 和 SciPy 1.18.1。下列命令在仓库根目录运行，求解无需模型或 API 密钥。

```bash
python -m pip install -r requirements.txt
python -X utf8 -m blocklift examples/tiny.col examples/tiny.dat --output example-result.json
python -X utf8 -m blocklift examples/tiny.col examples/tiny.dat --verify example-result.json
```

小例子的解为一步。图文件用 DIMACS 风格的 `p` 和 `e` 行，端点用 `s` 和 `t` 行，顶点从 1 编号。`--family generic` 可用于自定义图，`--moves-out moves.txt` 可导出逐步验证的移动列表，`--quality` 尝试继续改短。

```bash
python -X utf8 download_benchmark.py
python -X utf8 run_benchmark.py --seconds 15 --output reproduction.jsonl
```

准备约 300 MB 的磁盘空间。下载脚本会解压上游以 gzip 发布的最大皇后图。用相同源码、预算及输出文件可续跑。15 秒是程序内搜索预算，输入及验证另计。参考实验在 CoRe 693 例上交付 627 条合法路径并证明 66 例不可达。设备性能会影响限时搜索。仓库附带原始逐例见证及参照结果。 [固定提交的数据来源](https://github.com/TakehideSoh/KR2026/tree/df807b6b6ea66b7ec37a5371c58967eecc5ce762/benchmark) · [693 例实验报告](reports/core-693.md) · [公开方法对照](reports/comparison.md) · [七例补充实验](reports/seven-uncapped.md)
