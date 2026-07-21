# 核查方法论反思与工具盲区记录

> v5 终版（4 轮 10 次核查收敛，0 差异）。本文档记录方法论反思和工具盲区，**第 5 个盲区是 v5 揭示的最严重盲区**。

## 一、5 个系统性盲区（自我反查遗漏的根因）

### 盲区 1: 范围锚定偏差
**症状**：把"audit 重点 5 个 py"误解为"Top5 P0 所在文件"
**后果**：Top5 第 4 名 `_discover_canonical_files`（CC=45 F 级）所在的 `memory_hook_integrity_manifest.py` **完全在前 30 轮反查范围外**
**修正方法**：全仓 `radon cc -n D` 一次扫完，不要预先锁定文件范围

### 盲区 2: 命令参数漂移
**症状**：audit 用 `radon cc -a -nb -s -j memory_core/ scripts/ memory/ workspace/`，反查时变体多（去 -a、去 -nb、缩路径）
**后果**：每次数字都对不上，浪费 30+ 轮验证
**修正方法**：复制 audit 原命令原路径跑，不要自由发挥

### 盲区 3: AST 扫描方法 bug
**症状**：用 `ast.iter_child_nodes(tree)` 只看直接子节点
**后果**：漏掉 `if dry_run:` 块内、`for` 循环内、`with` 语句内的 `def`
**修正方法**：用 `ast.walk(tree)` 全树递归扫描

### 盲区 4: 工具信任偏差
**症状**：信任 radon cc 报告所有函数
**后果**：radon **不报告 nested function**（19 个完全没出现）
**修正方法**：AST + radon + vulture + grep 多工具交叉验证

### 盲区 5: AST 相似度标准化方法错误（v5 揭示的最严重盲区）

**症状**：v1-v4 全部用 `ast.dump(annotate_fields=True)` 计算相似度，但这是 Python 调试格式不是相似度方法

**具体错误**：
- Python 官方文档明确：annotate_fields=True "makes the code impossible to evaluate"（仅调试用）
- 字段名字符串（`name=`, `args=`, `id=`, `ctx=` 等）在所有 AST 节点都出现
- SequenceMatcher 把重复字段名当成"相似内容"，**任何两个 AST 都会得高分**
- 47/47 pair 全部通过 ≥0.80 阈值，**无判别力**

**具体影响**：
- v1-v4 报告 39-66 真 duplicate pair
- v5 切换到 `annotate_fields=False` + 行业 minimum-size 过滤（≥10 行 OR ≥50 tokens）
- 47 candidate → **10 真 duplicate**（-80%）
- 关键差异：`_classify_truth_ref` M1=0.4452（不是 duplicate），但 M2=0.872（虚高，被字段名字符串推上去）

**行业惯例**（v5 研究确认）：
- PMD CPD：token-based Rabin-Karp，min 100 tokens
- SonarQube：token-based，min 10 lines / 100 tokens
- jscpd：token-based，min 50 tokens
- 学术 Type-3 clone：0.5-0.8 阈值，token/structural 方法
- **没有任何主流工具用 annotate_fields=True**

**修正方法**：
- 用 `ast.dump(annotate_fields=False)`（M1 唯一标准）
- 加 minimum-size 过滤（≥10 行 OR ≥50 tokens）
- 接口镜像（同名不同实现）按 spec 不算 duplicate

---

## 二、双核/三核交叉验证才暴露的遗漏

| 遗漏类型 | 我之前数字 | bailian | kimi | GLM | **v5 终版** |
|---------|----------|---------|------|-----|-----------|
| 真重复对 | 15 | 39 | 65 | 66 | **10**（统一 spec）|
| 真死代码 | 23 | 43 | 42 | 42 | **44**（DOMAIN/RESOURCE 移活 + _sample/_section 补漏）|
| 跨类同名 method | 部分 | 14 | 58 | 12 | **5**（Cluster A 通过 size 过滤）|
| nested function | 11 | 19 | 19 | 19 | **19** |

**bailian vs kimi 数字差异原因**：bailian 把 5 个 class 的 `__init__` C(5,2)=10 对合并算 1 个 cluster；kimi 独立计数。两者核心 cluster 100% 一致，差异在计数粒度。但**两者都用错了标准化方法**（annotate_fields=True），数字虚高，最终被 v5 spec 收敛到 10。

---

## 三、元教训

### 教训 1: 反查的盲区来自范围假设而非数据本身
前 30 轮都在确认细节（CC 值、行号、LOC），从没质疑范围本身。

### 教训 2: 多核交叉验证是发现遗漏的可靠方法，但不是终点
bailian + kimi + GLM 三核交叉能发现遗漏，但**三核如果用同样的错误方法（annotate_fields=True），数字仍然虚高**。v5 的统一 spec 才是终点。

### 教训 3: 数字"看起来对"不等于"完整"，更不等于"方法论正确"
27 D+ 数字 100% 准确，但重复对数从 3 → 39 → 65 → 10 的剧烈变化说明：**方法论错误时数字收敛是虚假收敛**。v5 通过统一 spec 才真正收敛。

### 教训 4: 工具盲区必须交叉验证，但工具选型也要交叉验证
- radon cc 漏报 nested function（19 个）→ AST 补救
- vulture 不做"真死/误报"分类（129 条中 85 条是误报）→ grep 补救
- AST dump 相似度 vs 文本相似度有差异 → 多方法补救
- **但 AST dump 的标准化方法本身（True vs False）也要研究行业惯例**（v5 才发现）

### 教训 5: subagent 也会出错，orchestrator 必须核验关键数字和关键方法
- kimi 第一轮用了错误阈值（F≥50 而非 F≥41）
- bailian 在第二轮被 hook 中断两次
- 三核都用 annotate_fields=True，都虚高
- orchestrator 必须核验 subagent 的**方法论选型**，不仅是数字

### 教训 6: 多轮收敛需要明确 spec，否则数字会反复摇摆
v1 → v2 → v3 → v4 数字反复变化（重复对 39 → 65 → 66 → 44 → 10），根因是**没有 spec**。v5 定义统一 spec 后立即收敛到 10。

---

## 四、工具盲区速查表（v5 更新）

| 工具 | 盲区 | 影响 | 交叉验证方法 |
|------|------|------|-------------|
| radon cc | 不报告 nested function | 漏 19 个函数 | ast.walk 全树扫描 |
| radon cc | comprehension if 计数 | CC 值比手算高 1-5 | mccabe 库或手算 decision points |
| vulture | 不做真死/误报分类 | 129 条中 85 条是误报 | grep 全仓引用数 |
| vulture | 对 enum dotted access 盲区 | DOMAIN/RESOURCE 误报 | 手工核查测试引用 |
| **ast.dump(annotate_fields=True)** | **字段名字符串虚高相似度** | **47/47 pair 全通过，无判别力** | **改用 annotate_fields=False** |
| ast.iter_child_nodes | 不递归 | 漏 if/for/with 块内 def | 改用 ast.walk |
| grep -w | 边界情况 | 标准库同名符号干扰 | 加路径过滤 |
| **任何 AST 相似度方法（无 minimum-size）** | **trivial 函数（1-2 行 stub）被判 duplicate** | **Cluster D/E 全是 stub，无实际重复** | **加 ≥10 行 OR ≥50 tokens 过滤** |

---

## 五、v5 终版 canonical spec

### 死代码判定决策树

```
symbol X 真死 ⟺ 满足全部：
1. 生产代码（memory_core/ + scripts/）无实际调用/读取/实例化/访问
   - import 不算、注释不算、docstring 不算、异常消息自引用不算
   - markdown 文档不算、type annotation 不算
2. 测试代码（tests/）无实际调用/读取/实例化/访问
   - import 但不调用不算、注释提及不算
3. 删除该 symbol 后无任何测试失败

任一不满足 → 活
```

### Duplicate 判定决策树

```
pair (A, B) 真 duplicate ⟺ 满足全部：
1. M1 相似度 = ast.dump(annotate_fields=False) + SequenceMatcher.ratio() ≥ 0.80
2. 函数 body ≥10 行 OR ≥50 tokens（minimum-size 过滤）
3. 不是"同名但实现不同"的 dispatcher/coincidental clone（接口镜像不算）

任一不满足 → NOT duplicate
```

**禁用方法**：
- `annotate_fields=True`：Python 调试格式，虚高相似度
- source text difflib：字符级敏感
- token-only：节点类型序列过粗
- 任何"borderline 保留"或"caveat 标注"：违反 0 差异原则
