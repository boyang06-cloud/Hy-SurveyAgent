# Hy-SurveyAgent Application 开发文档

> **项目名称**：Hy-SurveyAgent  
> **模块类型**：Hy3-based Academic Survey Agent  
> **目标**：构建一个能够自主完成“研究主题理解 → 文献组织 → 论文阅读 → Survey 规划 → Survey 生成 → Citation Verification”的 Agent Application。  
> **开发原则**：模块化、可替换、可批量运行、可评测、可追溯。

---

# 1. 开发目标

Hy-SurveyAgent 不采用单一 Prompt 完成 Survey Generation，而采用多阶段 Agent Workflow。

目标 Pipeline：

```text
Input
 ↓
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
Final Survey
```

每一步均产生结构化中间结果，下一阶段只消费必要信息。

---

# 2. Application 输入输出

## 2.1 输入

标准输入：

```yaml
topic: "Vision-Language Models for Autonomous Driving"

research_questions:
  - "How have VLMs been applied to autonomous driving?"
  - "What are the main methodological categories?"

paper_ids:
  - paper_001
  - paper_002
  - paper_003

time_range:
  start: 2020
  end: 2026

output_style: "academic_survey"
```

Benchmark 模式下：

```text
Topic
+
固定 Source Paper Set
```

---

# 3. 输出

最终输出：

```text
Survey
├── Introduction
├── Problem Definition
├── Taxonomy
├── Method Comparison
├── Research Evolution
├── Limitations
├── Open Problems
├── Future Directions
└── References
```

同时输出机器可读取的：

```json
{
  "survey_markdown": "...",
  "citations": [...],
  "source_papers": [...],
  "outline": {...},
  "claims": [...],
  "verification": {...}
}
```

---

# 4. 总体架构

```text
                           ┌──────────────┐
                           │     User     │
                           └──────┬───────┘
                                  ↓
                       ┌────────────────────┐
                       │   Task Analyzer    │
                       └─────────┬──────────┘
                                 ↓
                       ┌────────────────────┐
                       │ Literature Manager │
                       └─────────┬──────────┘
                                 ↓
                       ┌────────────────────┐
                       │    Paper Reader    │
                       └─────────┬──────────┘
                                 ↓
                       ┌────────────────────┐
                       │ Knowledge Organizer│
                       └─────────┬──────────┘
                                 ↓
                       ┌────────────────────┐
                       │  Outline Planner   │
                       └─────────┬──────────┘
                                 ↓
                       ┌────────────────────┐
                       │   Survey Writer    │
                       └─────────┬──────────┘
                                 ↓
                       ┌────────────────────┐
                       │ Citation Verifier  │
                       └─────────┬──────────┘
                                 ↓
                           Final Survey
```

---

# 5. Agent 设计原则

## 5.1 不做“大一统 Agent”

不要：

```text
User
 ↓
一个巨大 Prompt
 ↓
Survey
```

而采用：

```text
多个职责明确的 Agent / Module
```

原因：

1. 每一步责任单一；
2. 中间结果可检查；
3. 可以单独测试；
4. 方便定位失败；
5. 可以对比 Agent Workflow 与 Baseline；
6. 更适合后续 Evaluation。

---

# 6. Agent 角色定义

## 6.1 Task Analyzer

### 职责

将自然语言 Research Topic 转换成结构化任务。

### 输入

```text
Research Topic
Research Questions
Constraints
```

### 输出

```json
{
  "topic": "...",
  "subtopics": [...],
  "key_concepts": [...],
  "expected_sections": [...],
  "retrieval_queries": [...]
}
```

### 要求

不负责 Survey 写作。

---

# 7. Literature Manager

## 职责

负责论文集合管理。

包括：

```text
Paper Retrieval
Paper Deduplication
Paper Filtering
Metadata Normalization
```

### 输入

```text
TaskSpec
```

### 输出

```json
{
  "papers": [
    {
      "paper_id": "...",
      "title": "...",
      "authors": [...],
      "year": 2025,
      "abstract": "...",
      "content": "..."
    }
  ]
}
```

---

# 8. Benchmark Mode

为了保证实验可复现，Benchmark 模式下禁止让线上检索结果影响数据一致性。

推荐：

```text
SurveyBench Topic
      ↓
固定 Source Papers
      ↓
Agent
```

而不是：

```text
SurveyBench Topic
      ↓
实时搜索 Internet
      ↓
随机获得不同论文
```

这样每次实验输入完全一致。

---

# 9. Paper Reader

## 职责

将论文转换成统一结构的 Research Representation。

对于每篇 Paper 提取：

```text
Paper Metadata
Problem
Motivation
Method
Architecture
Dataset
Experiment
Result
Advantage
Limitation
Key Claims
```

结构示例：

```json
{
  "paper_id": "P001",
  "problem": "...",
  "method": "...",
  "key_idea": "...",
  "advantages": [...],
  "limitations": [...],
  "experiments": [...],
  "claims": [...]
}
```

---

# 10. 为什么需要 Paper Reader

不要让 Survey Writer 直接阅读所有论文。

错误方式：

```text
50 Papers
    ↓
Huge Prompt
    ↓
Survey
```

问题：

- Context 过大；
- 信息组织能力差；
- 难以控制；
- 难以调试；
- 难以定位信息来源。

正确：

```text
Paper
 ↓
Structured Representation
 ↓
Knowledge Base
 ↓
Survey Planner
```

---

# 11. Knowledge Organizer

## 职责

负责跨论文建立研究领域知识结构。

核心任务：

```text
Paper → Topic
Paper → Method
Paper → Problem
Paper → Dataset
Paper → Relation
```

例如：

```text
Method
├── CNN-based
├── Transformer-based
├── Diffusion-based
└── Agent-based
```

以及：

```text
Paper A
    ├── extends → Paper B
    ├── compares → Paper C
    └── solves → Problem X
```

---

# 12. Knowledge Representation

推荐使用：

```json
{
  "topics": [...],
  "methods": [...],
  "papers": [...],
  "relations": [
    {
      "source": "P001",
      "relation": "extends",
      "target": "P002"
    }
  ]
}
```

第一版不需要真正建立 Graph Database。

使用：

```text
Python objects / JSON
```

即可。

---

# 13. Outline Planner

## 职责

根据 Knowledge Representation 生成 Survey Outline。

输出：

```json
{
  "sections": [
    {
      "title": "Introduction",
      "purpose": "...",
      "papers": ["P001", "P004"]
    },
    {
      "title": "Method Taxonomy",
      "purpose": "...",
      "papers": ["P001", "P002", "P003"]
    }
  ]
}
```

关键要求：

每个 Section 必须明确：

```text
Purpose
+
Relevant Papers
+
Key Claims
```

这样 Writer 不会无约束地写作。

---

# 14. Survey Writer

## 职责

根据：

```text
TaskSpec
+
Knowledge Representation
+
Outline
+
Paper Evidence
```

生成最终 Survey。

Writer 不允许自行发明不存在的 Paper / Citation。

---

# 15. Citation 格式

统一采用：

```text
[1]
[2]
[3]
```

并维护：

```json
{
  "citation_id": "[1]",
  "paper_id": "P001",
  "title": "...",
  "source": "..."
}
```

---

# 16. Claim Tracking

这是整个 Application 非常重要的设计。

Survey Writer 产生：

```text
Claim
+
Citation
```

系统同步建立：

```json
{
  "claim_id": "C001",
  "text": "Method X improves...",
  "citations": ["P001"]
}
```

最终得到：

```text
Survey
   ↓
Claims
   ↓
Citations
   ↓
Source Papers
```

这为后续 Evaluation 提供天然接口。

---

# 17. Citation Verifier

## 职责

验证：

> Survey 中的 Claim 是否被对应论文支持。

Pipeline：

```text
Survey
 ↓
Claim Extraction
 ↓
Citation Mapping
 ↓
Source Evidence Retrieval
 ↓
Evidence Comparison
 ↓
Verification Result
```

输出：

```json
{
  "claim_id": "C001",
  "citation": "P001",
  "support": true,
  "evidence": "...",
  "confidence": 0.92
}
```

---

# 18. Citation Verification 不等于 Citation Formatting

必须区分：

### Citation Formatting

检查：

```text
有没有 [1]
格式对不对
Reference 是否存在
```

### Citation Grounding

检查：

```text
Claim
↓
Citation
↓
Paper
↓
Evidence
```

第二种才是真正有价值的。

---

# 19. Hy3 Adapter

Application 不应把 Hy3 SDK 调用散落在各 Agent 中。

建立统一：

```text
app/model/hy3_adapter.py
```

统一接口：

```python
class LLMProvider:
    def generate(
        self,
        messages,
        model,
        temperature,
        max_tokens,
    ): ...
```

各 Agent 只调用：

```python
llm.generate(...)
```

而不直接调用具体 Hy3 SDK。

---

# 20. 为什么需要 Adapter

这样未来可以比较：

```text
Hy3
vs
Baseline Model
```

而不用修改 Agent Pipeline。

最终结构：

```text
Agent
 ↓
LLMProvider
 ↓
Hy3Adapter
 ↓
Hy3
```

---

# 21. Prompt 管理

不要把 Prompt 写死在 Python 代码中。

推荐：

```text
app/prompts/
├── task_analyzer.md
├── paper_reader.md
├── organizer.md
├── planner.md
├── writer.md
└── citation_verifier.md
```

每一个 Prompt 包含：

```text
Role
Input Schema
Output Schema
Rules
Few-shot Examples
Failure Constraints
```

---

# 22. 强制结构化输出

Agent 不建议直接返回自由文本。

例如 Task Analyzer：

```json
{
  "subtopics": [],
  "key_concepts": [],
  "queries": []
}
```

Paper Reader：

```json
{
  "problem": "",
  "method": "",
  "advantages": [],
  "limitations": [],
  "claims": []
}
```

Outline Planner：

```json
{
  "sections": []
}
```

好处：

- 更容易验证；
- 更容易串联；
- 更容易保存；
- 更容易 Debug；
- 更方便 Evaluation。

---

# 23. Execution State

建议整个 Agent 使用统一 State：

```python
class SurveyState:
    task_spec
    papers
    paper_analyses
    knowledge_base
    outline
    draft
    claims
    citation_map
    verification
    final_survey
```

整个流程：

```text
State
 ↓
Analyzer
 ↓
State
 ↓
Reader
 ↓
State
 ↓
Organizer
 ↓
State
 ...
```

---

# 24. Failure Handling

每个 Stage 必须有：

```text
Input Validation
Timeout
Retry
Fallback
Error Logging
```

例如 Paper Reader 失败：

```text
Paper Reader
 ↓
Error
 ↓
Retry
 ↓
仍失败
 ↓
Mark Paper Unavailable
 ↓
Continue
```

不能因为单篇论文失败导致整个任务崩溃。

---

# 25. Context 管理

不要让每个 Agent 都携带完整上下文。

推荐：

```text
Task Analyzer
→ TaskSpec

Paper Reader
→ PaperAnalysis

Organizer
→ KnowledgeBase

Planner
→ Outline

Writer
→ Relevant Evidence + Outline
```

实现：

> **按阶段传递最小必要 Context。**

---

# 26. 推荐的 Application Runtime

第一版不需要复杂 Agent Framework。

推荐：

```text
Python
+
AsyncIO
+
Typed Data Model
+
Hy3 Adapter
```

Pipeline：

```python
task = analyze_task(input)

papers = retrieve_papers(task)

analyses = await read_papers(papers)

knowledge = organize(analyses)

outline = plan_outline(task, knowledge)

draft = write_survey(task, knowledge, outline)

verification = verify_citations(draft, papers)

result = finalize(draft, verification)
```

---

# 27. 并行化设计

论文阅读是最适合并行的：

```text
                 Paper Reader
              /      |       \
          Paper A  Paper B  Paper C
              \      |       /
               Knowledge Base
```

使用：

```python
asyncio.gather(...)
```

而不是：

```text
Paper A
↓
Paper B
↓
Paper C
```

这样可以显著降低总执行时间。

---

# 28. Application MVP

第一版只实现：

```text
Input Topic
      ↓
Fixed Source Papers
      ↓
Paper Reader
      ↓
Knowledge Organizer
      ↓
Outline Planner
      ↓
Survey Writer
      ↓
Citation Verifier
      ↓
Final Survey
```

暂时不加入：

- Long-term Memory；
- Multi-user；
- Complex Web UI；
- Persistent Vector DB；
- 多模型自动路由；
- 复杂自主循环。

---

# 29. V1 Application

在 MVP 成功后增加：

```text
Dynamic Retrieval
+
Parallel Reading
+
Better Citation Verification
+
Interactive Review
+
Evaluation Integration
```

最终：

```text
Research Topic
 ↓
Retrieve
 ↓
Read
 ↓
Organize
 ↓
Plan
 ↓
Write
 ↓
Verify
 ↓
Evaluate
```

---

# 30. Evaluation Interface

Application 和 Evaluation 之间必须有稳定接口。

Application 最终输出：

```json
{
  "task": {...},
  "papers": [...],
  "survey": "...",
  "claims": [...],
  "citations": [...],
  "evidence_map": [...]
}
```

Evaluation 只消费这个结果：

```text
Application Output
        ↓
Evaluation
```

这样可以做到：

```text
更换 Evaluator
而无需修改 Agent
```

---

# 31. Logging

每个 Stage 保存：

```text
task_id
stage
input
output
latency
token_usage
error
timestamp
```

目录：

```text
runs/
└── <task_id>/
    ├── task.json
    ├── papers.json
    ├── analyses.json
    ├── knowledge.json
    ├── outline.json
    ├── draft.md
    ├── claims.json
    ├── verification.json
    └── final.md
```

这对于最终 Failure Analysis 非常重要。

---

# 32. 测试策略

## Unit Test

分别测试：

- Task Analyzer；
- Paper Parser；
- Citation Parser；
- Claim Extractor；
- Score Aggregator。

---

## Integration Test

测试：

```text
Topic
↓
Agent
↓
Survey
↓
Verification
```

---

## Evaluation Test

测试：

```text
Known Good
Known Bad
```

Evaluator 是否得到预期排序。

---

# 33. Benchmark Test

固定：

```text
Topic
+
Source Papers
```

反复运行：

```text
Agent
```

记录：

```text
Latency
Cost
Output
Evaluation Score
```

---

# 34. Baseline Interface

为了后续实验，统一：

```python
class SurveyGenerator:
    def generate(
        self,
        topic,
        papers,
    ): ...
```

实现：

```text
SimplePromptGenerator
SequentialGenerator
HySurveyAgent
```

然后：

```text
Benchmark
↓
Generator Interface
↓
不同实现
↓
统一 Evaluator
```

---

# 35. 推荐目录

```text
app/
│
├── core/
│   ├── state.py
│   ├── types.py
│   └── pipeline.py
│
├── agents/
│   ├── task_analyzer.py
│   ├── paper_reader.py
│   ├── organizer.py
│   ├── planner.py
│   ├── writer.py
│   └── citation_verifier.py
│
├── retrieval/
│   ├── retriever.py
│   └── benchmark_loader.py
│
├── model/
│   ├── provider.py
│   └── hy3_adapter.py
│
├── prompts/
│   ├── task_analyzer.md
│   ├── paper_reader.md
│   ├── organizer.md
│   ├── planner.md
│   ├── writer.md
│   └── citation_verifier.md
│
├── io/
│   ├── loader.py
│   └── exporter.py
│
└── main.py
```

---

# 36. Application 开发顺序

不要一次性开发全部 Agent。

推荐：

## Step 1

先完成：

```text
Hy3 Adapter
+
Paper Loader
+
Simple Writer
```

跑通：

```text
Topic + Papers
→ Survey
```

---

## Step 2

增加：

```text
Paper Reader
```

变成：

```text
Topic
↓
Paper Analysis
↓
Survey
```

---

## Step 3

增加：

```text
Knowledge Organizer
+
Outline Planner
```

形成真正的 Agent Workflow。

---

## Step 4

增加：

```text
Citation Verifier
```

形成：

```text
Generate
+
Verify
```

---

## Step 5

接入 Evaluation：

```text
Application
↓
Evaluation
```

---

## Step 6

接入 Benchmark Batch Runner：

```text
20 Topics
↓
20 Agent Runs
↓
20 Surveys
↓
Evaluation
↓
Results
```

---

# 37. Application 最终验收标准

## Functional

- [ ] 能输入 Topic；
- [ ] 能加载 Source Papers；
- [ ] 能调用 Hy3；
- [ ] 能完成多阶段 Agent Workflow；
- [ ] 能生成 Survey；
- [ ] 能生成 References；
- [ ] Citation 可追溯；
- [ ] 能输出结构化结果。

## Engineering

- [ ] Hy3 调用集中在 Adapter；
- [ ] Prompt 与业务逻辑分离；
- [ ] Agent 输出结构化；
- [ ] State 可持久化；
- [ ] 支持重试；
- [ ] 支持日志；
- [ ] 支持 Batch Execution。

## Reproducibility

- [ ] Benchmark 输入固定；
- [ ] 模型配置记录；
- [ ] Prompt 版本记录；
- [ ] 运行参数记录；
- [ ] 最终结果可复现。

---

# 38. 最终 Application Pipeline

```text
┌─────────────────────┐
│      Research       │
│       Topic         │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│   Task Analyzer     │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Literature Manager  │
└──────────┬──────────┘
           ↓
     ┌─────┴─────┐
     ↓     ↓     ↓
   Paper  Paper  Paper
   Reader Reader Reader
     └─────┬─────┘
           ↓
┌─────────────────────┐
│ Knowledge Organizer │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│   Outline Planner   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│   Survey Writer     │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│ Citation Verifier   │
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│    Final Survey     │
└──────────┬──────────┘
           ↓
      Evaluation
```

---

# 39. 最终开发目标

第一版 Application 不追求“最复杂的 Agent”，而追求：

```text
可运行
+
可复现
+
可解释
+
可验证
+
可批量评测
```

最终 Hy-SurveyAgent 应当成为一个清晰的研究流程：

> **理解一个研究问题 → 组织相关论文 → 提取论文知识 → 建立研究分类 → 规划 Survey → 综合写作 → 核验引用。**

并且所有中间产物都可以被保存、检查和用于后续 Evaluation。