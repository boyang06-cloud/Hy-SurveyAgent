# Hy-SurveyAgent 项目设计文档

> **项目性质**：犀牛鸟开源实战任务——Hy3 Application with Custom Evaluation Criteria for Open-ended Tasks  
> **项目名称**：Hy-SurveyAgent  
> **项目定位**：基于 Hy3 构建面向科研人员的 Academic Survey Agent，并设计一套独立、可执行、可验证的开放式 Survey 质量评测体系。  
> **核心原则**：Application 与 Evaluation 分离；Benchmark 作为数据底座而非评测器；通过判别力、一致性、人工一致性及对抗性实验验证评测方法有效性。

---

## 1. 项目概述

### 1.1 项目目标

Hy-SurveyAgent 面向需要快速了解某一研究方向的本科生、研究生和科研人员，提供从研究主题理解、文献组织、论文阅读、Survey 结构规划到 Survey 生成与引用核验的一体化辅助能力。

项目不仅实现一个可运行的 AI Application，还需要针对该场景建立一套自定义质量评估方法，用于回答：

> **什么样的 AI-generated Survey 才算“高质量”？**

进一步通过实验验证：

1. 评估方法是否能够区分不同质量等级的 Survey；
2. 评估方法本身是否具有稳定性；
3. 评估结果是否与人工评价具有较高一致性；
4. 面对篇幅扩张、术语堆砌、引用伪造等 reward hacking 行为时，评估器是否仍能正确判断质量。

最终形成：

```text
真实科研场景
    ↓
Hy-SurveyAgent
    ↓
AI-generated Survey
    ↓
Custom Evaluation System
    ↓
Validation Experiments
    ↓
Failure Mode Analysis
    ↓
完整开源项目
```

---

# 2. 项目范围

## 2.1 Application 范围

Application 负责：

- 理解研究主题；
- 获取并组织相关论文；
- 阅读和抽取论文信息；
- 构建研究主题/方法分类；
- 规划 Survey Outline；
- 综合生成 Survey；
- 对生成内容进行 Citation Verification；
- 输出最终 Survey 与引用/证据结构。

Application 本身不负责：

- 训练或微调模型；
- 构建新的基础模型；
- 将 Human Survey 直接作为 Agent 输入；
- 直接复用第三方 Benchmark 的最终评分作为本项目唯一评测标准。

---

## 2.2 Evaluation 范围

Evaluation 负责评价生成出的 Survey，至少覆盖：

1. Factual Accuracy
2. Citation Grounding
3. Topic Coverage
4. Evidence Completeness
5. Cross-paper Synthesis
6. Research Depth
7. Logical Organization
8. Readability / Information Utility

Evaluation 必须具有明确的操作性判定标准。

---

## 2.3 Validation 范围

Validation 不用于评价模型本身，而用于回答：

> **我们设计的 Evaluation System 是否可靠？**

至少包括：

- Discrimination Validation
- Consistency Validation

建议增加：

- Human Agreement Validation
- Adversarial Robustness Validation

---

# 3. 场景定义

## 3.1 目标用户

主要面向：

- 本科生；
- 研究生；
- 科研初学者；
- 需要快速进入新研究方向的研究人员。

---

## 3.2 用户问题

科研人员面对新的研究主题时，通常需要完成：

```text
确定研究问题
↓
搜索论文
↓
阅读大量论文
↓
建立分类体系
↓
理解不同工作的关系
↓
总结发展脉络
↓
寻找研究空白
↓
形成 Survey / Research Overview
```

这个过程具有：

- 文档数量多；
- 文档长度大；
- 需要跨论文比较；
- 需要进行信息综合；
- 最终输出不存在唯一正确答案。

因此非常适合开放式 LLM Application 与 Custom Evaluation。

---

## 3.3 LLM 的必要性

传统关键词搜索能够解决：

```text
找到论文
```

但难以直接解决：

```text
理解论文
+
比较论文
+
建立方法分类
+
总结研究演化
+
跨论文综合
+
形成完整 Survey
```

Hy-SurveyAgent 的目标不是替代论文阅读，而是压缩研究信息处理成本。

---

# 4. 总体系统架构

```text
                            User
                              │
                              ↓
                     Research Topic
                              │
                              ↓
                    ┌──────────────────┐
                    │  Task Analyzer   │
                    └────────┬─────────┘
                             ↓
                    ┌──────────────────┐
                    │ Literature       │
                    │ Retriever        │
                    └────────┬─────────┘
                             ↓
                    ┌──────────────────┐
                    │ Paper Reader     │
                    └────────┬─────────┘
                             ↓
                    ┌──────────────────┐
                    │ Knowledge        │
                    │ Organizer        │
                    └────────┬─────────┘
                             ↓
                    ┌──────────────────┐
                    │ Outline Planner  │
                    └────────┬─────────┘
                             ↓
                    ┌──────────────────┐
                    │ Survey Writer    │
                    └────────┬─────────┘
                             ↓
                    ┌──────────────────┐
                    │ Citation         │
                    │ Verifier         │
                    └────────┬─────────┘
                             ↓
                         Final Survey
                             │
             ┌───────────────┴────────────────┐
             ↓                                ↓
      Citation / Evidence               Evaluation
                                           │
                  ┌────────────────────────┼────────────────────┐
                  ↓                        ↓                    ↓
             Rule Checker            Evidence Checker       Hy3 Judge
                  │                        │                    │
                  └────────────────────────┼────────────────────┘
                                           ↓
                                      Score Aggregator
                                           ↓
                                      Final Results
```

---

# 5. 项目总体工作流

## Phase 0：项目初始化

### 目标

建立项目仓库和基础工程规范。

### 任务

- 创建公开 GitHub Repository；
- 项目标明为个人 / 活动作品；
- 建立 README；
- 建立 Python 环境；
- 建立配置文件机制；
- 建立 `.env.example`；
- 禁止 API Key 硬编码；
- 确定 SurveyBench 数据版本；
- 建立实验结果目录；
- 建立统一日志与运行方式。

### 交付物

```text
Repository
README.md
requirements.txt / pyproject.toml
.env.example
configs/
scripts/
docs/
```

---

# 6. Phase 1：Survey 场景与任务定义

## 目标

把“写 Survey”定义成一个明确、可执行的 AI Task。

### 输入定义

推荐：

```text
Research Topic
+
可选研究问题
+
可选论文范围 / 时间范围
```

Benchmark 模式下：

```text
Topic
+
指定 Source Paper Collection
```

### 输出定义

输出结构建议：

```text
1. Introduction
2. Problem Definition
3. Taxonomy
4. Method Overview
5. Comparison
6. Research Evolution
7. Limitations
8. Open Problems
9. Future Directions
10. References
```

### 验收标准

- 输入格式明确；
- 输出结构明确；
- Agent 可独立执行；
- 输出能够进入 Evaluation Pipeline。

---

# 7. Phase 2：Hy-SurveyAgent Application

## 目标

实现可运行的 Survey Agent。

### 核心流程

```text
Task Analysis
    ↓
Literature Retrieval
    ↓
Paper Reading
    ↓
Knowledge Organization
    ↓
Outline Planning
    ↓
Survey Writing
    ↓
Citation Verification
    ↓
Final Output
```

### 交付物

- Application 源码；
- Hy3 Adapter；
- Prompt 模板；
- Agent Pipeline；
- 数据结构；
- CLI / Web Demo；
- 运行说明。

### 验收标准

给定一个标准 Topic + Source Papers 后：

1. Agent 能正常运行；
2. 能产生结构化 Survey；
3. Survey 包含引用；
4. Citation 可以追溯到 Source Papers；
5. 全流程不需要人工介入；
6. 能批量运行 Benchmark。

---

# 8. Phase 3：Evaluation Rubric 设计

## 8.1 评价维度

第一版确定 8 个维度：

| ID | Dimension | 核心问题 |
|---|---|---|
| D1 | Factual Accuracy | 陈述的事实是否正确 |
| D2 | Citation Grounding | Citation 是否真正支持 Claim |
| D3 | Topic Coverage | 是否覆盖核心研究内容 |
| D4 | Evidence Completeness | 需要证据的 Claim 是否提供证据 |
| D5 | Cross-paper Synthesis | 是否真正进行了跨论文综合 |
| D6 | Research Depth | 是否深入到机制、优缺点和关系 |
| D7 | Logical Organization | 结构与论述逻辑是否合理 |
| D8 | Readability / Utility | 是否便于科研人员理解和使用 |

---

## 8.2 Rubric 统一格式

每个维度必须包含：

```text
Dimension
↓
Evaluation Objective
↓
Metric
↓
Operational Definition
↓
Scoring Rule
↓
Edge Cases
↓
Positive Example
↓
Negative Example
```

禁止使用：

```text
较好
基本符合
比较完整
较为准确
```

必须转换成可操作标准。

---

## 8.3 推荐总分

```text
Factual Accuracy        20%
Citation Grounding      15%
Topic Coverage          15%
Evidence Completeness   10%
Cross-paper Synthesis   15%
Research Depth          10%
Logical Organization    10%
Readability              5%
```

总分：

```text
Final Score ∈ [0,100]
```

---

## 8.4 Hard Failure

针对严重错误设置分数上限。

例如：

```text
严重事实错误
或
明确虚假 Citation
```

触发：

```text
Final Score Cap ≤ 60
```

目的：

防止模型仅凭流畅表达和结构质量掩盖关键事实错误。

---

# 9. Phase 4：Evaluation Dataset 构造

## 9.1 数据底座

使用公开 Survey Benchmark 作为基础数据源。

Benchmark 中提供的：

- Topic；
- Source Papers；
- Human-written Survey；
- Quiz / 相关评测信息；

用于构建本项目的 Dataset。

---

## 9.2 数据使用原则

Human Survey：

```text
只能作为 Reference / Gold Information
```

不能：

```text
Human Survey
↓
Prompt
↓
Hy-SurveyAgent
```

否则可能出现 Evaluation Leakage。

---

## 9.3 数据集结构

```text
benchmark/
├── source/
├── references/
├── quizzes/
├── normal/
├── hard/
├── negative/
└── adversarial/
```

---

## 9.4 样本类型

### Normal

正常研究主题。

### Hard

例如：

- 论文数量较多；
- 方法类别相似；
- 论文关系复杂；
- 容易发生概念混淆；
- 存在大量相近术语。

### Negative

例如：

- 不相关论文；
- 信息缺失；
- 无法支持某结论的材料；
- 边界问题。

### Adversarial

包括：

- Length Inflation；
- Terminology Inflation；
- Citation Injection；
- Reference Flooding；
- Structure Gaming。

---

# 10. Phase 5：Evaluation Pipeline 实现

## 总体架构

```text
Generated Survey
       │
       ├───────────────┐
       ↓               ↓
Rule Checker      Claim Extraction
                         ↓
                  Evidence Checker
                         │
                         ↓
                    Hy3 Judge
                         │
                         ↓
                   Score Aggregator
                         ↓
                  Evaluation Result
```

---

## 10.1 Rule Checker

处理确定性问题：

- 格式；
- 引用格式；
- Section；
- Citation 数量；
- 重复内容；
- 必要字段；
- 输出长度等。

---

## 10.2 Claim / Evidence Checker

处理：

```text
Claim
↓
Citation
↓
Source Paper
↓
Evidence
```

核心目标：

判断 Claim 是否真正得到 Source Paper 支持。

---

## 10.3 Hy3 Judge

用于：

- Synthesis；
- Depth；
- Logic；
- Readability；
- 部分 Coverage。

Judge 必须严格按照预先定义的 Rubric 输出，不允许自由发挥评分标准。

---

## 10.4 Score Aggregator

统一：

```text
Dimension Scores
↓
Weighting
↓
Hard Failure Detection
↓
Final Score
```

最终输出：

```json
{
  "total_score": 82.4,
  "dimensions": {
    "accuracy": 86,
    "citation_grounding": 78,
    "coverage": 85,
    "evidence_completeness": 80,
    "synthesis": 82,
    "depth": 79,
    "organization": 90,
    "readability": 88
  },
  "hard_failure": false
}
```

---

# 11. Phase 6：Validation Experiments

## Experiment 1：Discrimination Validation

构造：

```text
Good
Medium
Bad
```

Evaluator 应满足：

```text
Score(Good)
>
Score(Medium)
>
Score(Bad)
```

### 指标

推荐：

- Spearman Rank Correlation；
- Kendall Rank Correlation；
- Pairwise Accuracy。

---

# 12. Experiment 2：Consistency Validation

同一输出重复评估多次。

例如：

```text
Run 1 → 82.1
Run 2 → 82.8
Run 3 → 82.3
Run 4 → 81.9
Run 5 → 82.4
```

计算：

- Mean；
- Standard Deviation；
- Coefficient of Variation。

---

# 13. Experiment 3：Human Agreement

抽取部分样本，由人工进行评价。

人工评价：

```text
Accuracy
Coverage
Citation
Synthesis
Overall
```

然后比较：

```text
Human Score
      ↕
Evaluator Score
```

推荐：

- Spearman Correlation；
- Pearson Correlation；
- MAE。

---

# 14. Experiment 4：Adversarial Robustness

针对同一基础 Survey 构造：

```text
Original
Length Inflation
Terminology Inflation
Citation Injection
Reference Flooding
Structure Gaming
```

检查：

```text
无真实质量提升
        ↓
Score 不应显著提升
```

尤其关注：

```text
Citation Attack
→ Citation Grounding 应下降

Length Attack
→ Readability / Utility 不应因为篇幅增加而上升

Terminology Attack
→ Research Depth 不应被虚假术语显著抬高
```

---

# 15. Phase 7：完整 Benchmark Evaluation

对最终 Benchmark 全量执行：

```text
Dataset
↓
Hy-SurveyAgent
↓
Generated Surveys
↓
Evaluator
↓
Results
```

输出：

```text
results/
├── full_results.csv
├── dimension_scores.csv
├── summary.json
└── figures/
```

---

# 16. Phase 8：Baseline 对比

建议至少加入：

### Baseline A

单次 Hy3 Prompt：

```text
Topic + Papers
↓
Hy3
↓
Survey
```

### Baseline B

简单 sequential pipeline：

```text
Summarize Papers
↓
Generate Survey
```

### Proposed

```text
Task Analysis
→ Retrieval
→ Reading
→ Organization
→ Planning
→ Writing
→ Citation Verification
```

比较：

```text
Accuracy
Coverage
Citation
Synthesis
Depth
Overall
```

目的：

验证 Agent workflow 是否比简单 prompting 有实际价值。

---

# 17. Phase 9：Failure Mode Analysis

选择典型：

- High-score Cases；
- Low-score Cases；
- Borderline Cases；
- Adversarial Cases。

分析：

```text
Input
↓
Generated Output
↓
Evaluator Score
↓
Error
↓
Root Cause
↓
Failure Mode
```

建议总结：

### Failure Mode 1

Factual Hallucination

### Failure Mode 2

Citation Mismatch

### Failure Mode 3

Coverage Omission

### Failure Mode 4

Shallow Synthesis

### Failure Mode 5

Incorrect Taxonomy

### Failure Mode 6

Overconfident Conclusion

### Failure Mode 7

Terminology Surface Matching

### Failure Mode 8

Verbose but Low-information Writing

---

# 18. Phase 10：能力边界分析

最终回答：

```text
Hy-SurveyAgent 擅长什么？
```

例如：

- 单论文事实抽取；
- 基础方法归纳；
- 研究方向分类；
- 结构化生成。

以及：

```text
Hy-SurveyAgent 不擅长什么？
```

例如：

- 跨论文深层比较；
- 复杂证据链；
- 细粒度 Citation Grounding；
- 隐含研究假设识别；
- 新颖研究空白判断。

---

# 19. Phase 11：文档与开源收尾

## 必须交付

```text
README.md
Application Source Code
Environment Configuration
Evaluation Dataset / Dataset Preparation Script
Evaluation Method Document
Evaluation Script
Validation Experiment
Full Results
Analysis Report
Demo Video / GIF
```

---

## README 必须包含

```text
1. Project Introduction
2. Motivation
3. Architecture
4. Features
5. Environment
6. Installation
7. Configuration
8. API Key Configuration
9. Quick Start
10. Benchmark Preparation
11. Evaluation
12. Validation Experiments
13. Results
14. Failure Analysis
15. Limitations
16. License
17. Attribution
```

---

# 20. 推荐 Repository Structure

```text
Hy-SurveyAgent/
│
├── app/
│   ├── analyzer/
│   ├── retriever/
│   ├── reader/
│   ├── organizer/
│   ├── planner/
│   ├── writer/
│   └── citation_verifier/
│
├── evaluator/
│   ├── rubric/
│   ├── rules/
│   ├── claims/
│   ├── evidence/
│   ├── judge/
│   └── aggregator/
│
├── benchmark/
│   ├── source/
│   ├── references/
│   ├── quizzes/
│   ├── hard/
│   ├── negative/
│   └── adversarial/
│
├── experiments/
│   ├── discrimination/
│   ├── consistency/
│   ├── human_agreement/
│   └── adversarial/
│
├── results/
│
├── scripts/
│   ├── run_agent.py
│   ├── run_eval.py
│   ├── run_validation.py
│   └── prepare_benchmark.py
│
├── configs/
│   └── config.example.yaml
│
├── docs/
│   ├── project_design.md
│   ├── application_development.md
│   ├── evaluation_method.md
│   ├── benchmark.md
│   └── validation.md
│
├── demo/
├── .env.example
├── README.md
├── pyproject.toml
└── LICENSE
```

---

# 21. 项目最终验收标准

## Application

- [ ] Hy3 正常调用
- [ ] Survey Pipeline 完整
- [ ] Citation 能追溯
- [ ] 无人工介入即可运行
- [ ] 支持 Benchmark 批量运行

## Evaluation

- [ ] ≥5 个评价维度
- [ ] 每个维度有明确判定标准
- [ ] 自动/半自动评分
- [ ] 输出结构化结果
- [ ] 支持单 Case 与 Batch Evaluation

## Dataset

- [ ] 使用公开 Benchmark 数据底座
- [ ] 数据版本固定
- [ ] 来源说明明确
- [ ] 包含 Hard Cases
- [ ] 包含 Negative Cases
- [ ] 包含 Adversarial Cases

## Validation

- [ ] Discrimination
- [ ] Consistency
- [ ] Human Agreement
- [ ] Adversarial Robustness

## Final Delivery

- [ ] GitHub Public Repository
- [ ] README
- [ ] 环境配置
- [ ] Evaluation Materials
- [ ] Validation Results
- [ ] Analysis Report
- [ ] Demo Video / GIF
- [ ] API Key 不进入仓库
- [ ] 明确个人 / 活动作品属性

---

# 22. 项目最终叙事

最终项目形成如下闭环：

```text
真实科研需求
      ↓
Hy-SurveyAgent
      ↓
AI-generated Survey
      ↓
Custom Multi-dimensional Evaluator
      ↓
Evaluator Validation
      ↓
Full Benchmark Evaluation
      ↓
Failure Mode Analysis
      ↓
Capability Boundary
```

项目核心贡献不是单纯“生成 Survey”，而是：

> **构建一个能够完成学术调研任务的 Hy3 Agent，并建立一套针对开放式 Survey 产物的、证据驱动的、多维度且经过实验验证的评价体系。**

---

# 23. 项目里程碑

| Milestone | 完成内容 |
|---|---|
| M1 | 场景与 Benchmark 数据方案确定 |
| M2 | Hy-SurveyAgent MVP |
| M3 | Citation Verification |
| M4 | Evaluation Rubric V1 |
| M5 | Evaluation Pipeline |
| M6 | Benchmark Dataset V1 |
| M7 | Discrimination + Consistency |
| M8 | Human + Adversarial Validation |
| M9 | Full Evaluation |
| M10 | Failure Analysis |
| M11 | README / Demo / Open Source |