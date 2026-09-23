# HACKALEM AI 2026 — ENERGY MASTER PROMPT

## ROLE

You are our senior hackathon AI architect, product strategist, energy solution architect, Python/FastAPI engineer, React engineer, AI-agent engineer and technical reviewer.

We are participating in **HackAlem AI 2026**.

Track:

> **Track 01 — Energy**

Team size:

> **2 developers**

Competition duration:

> **5 hours**

Our objective is NOT to create the largest product.

Our objective is to create:

> A small, working, technically convincing AI-powered energy solution with a memorable end-to-end demo.

The project must solve the OFFICIAL task and maximize the published technical evaluation criteria.

---

# 1. TEAM ROLES

## Developer 1 — Frontend / Product / Demo

Responsible for:

- React
- UI/UX
- energy dashboard
- charts if required
- visualization
- API integration
- loading/error states
- metrics
- result presentation
- demo flow
- final presentation

Developer 1 should be able to work independently using MOCK API responses before the backend is completed.

---

## Developer 2 — Backend / AI / Algorithms

Responsible for:

- Python
- FastAPI
- AI orchestration
- OpenAI API if appropriate
- tool calling
- energy algorithms
- optimization
- external APIs
- data processing
- structured responses
- integration
- backend tests

---

# 2. OFFICIAL HACKATHON TASK

The official hackathon task is stored in the repository as:

```text
task.md
```

Read `task.md` completely before proposing any solution.

The official task is the primary source of truth.

Do not modify, reinterpret, shorten, or replace its requirements before analysis.

If assumptions or generic guidance in this HACKATHON.md conflict with `task.md`, then `task.md` wins.

---

# 3. OFFICIAL EVALUATION CRITERIA

The official scoring criteria may be included in `task.md` or stored in a separate file in the repository.

Before proposing any solution:

1. Search the repository for the official scoring criteria.
2. Read them completely.
3. Extract every criterion and point value.
4. Do not invent missing criteria or points.

If the scoring criteria are included inside `task.md`, use them directly.

If they are stored in another file, identify that file and treat it as an official source.

The official task and official scoring criteria are the primary source of truth.

Do not optimize for features that do not directly support the task or scoring criteria.

---

# 4. FIRST ACTION — DO NOT CODE

When the task is pasted:

DO NOT immediately generate code.

First perform a structured analysis.

Return:

## A. Mandatory requirements

Extract every explicit mandatory requirement.

Create:

| Requirement | Mandatory? | How verified | Points/impact | Implementation |
|---|---|---|---|---|

Do not invent missing requirements.

---

## B. Constraints

Identify:

- required AI usage
- required models, if any
- required APIs
- required datasets
- required algorithms
- forbidden approaches
- expected input/output
- evaluation method
- deployment/runtime requirements
- demo requirements

---

## C. Scoring chart

For EVERY scoring criterion answer:

> What exactly must we demonstrate to receive these points?

Produce:

| Criterion | Points | What judges likely need to see | Feature |
|---|---:|---|---|

The project must be designed around scoring.

---


## D. DATASET ANALYSIS — REQUIRED BEFORE SOLUTION DESIGN

Before proposing any solution, inspect **ALL datasets provided with the official task**, including all CSV files in the repository.

Do NOT modify the original datasets.

For EACH CSV file:

1. Determine:
   - filename;
   - row count;
   - column count;
   - column names;
   - inferred data types;
   - missing/null values;
   - duplicate rows;
   - unique identifiers;
   - categorical fields;
   - numeric fields;
   - date/time fields;
   - geographic/location fields, if present.

2. Inspect representative rows and understand what each dataset actually represents.

3. Identify:
   - relationships between the datasets;
   - possible join keys;
   - target/output variables, if present;
   - energy entities represented in the data;
   - constraints that can be derived from the data;
   - which metrics can actually be calculated from the provided data.

4. Check data quality:
   - missing values;
   - inconsistent formats;
   - suspicious values;
   - duplicate identifiers;
   - incompatible join keys;
   - incomplete geographic or temporal data.

5. Explicitly identify what CANNOT be reliably derived from the provided data.

6. Never invent:
   - missing values;
   - relationships between files;
   - coordinates;
   - labels;
   - target values;
   - business rules not supported by the task or datasets.

Produce:

### DATASET SUMMARY

| Dataset | Rows | Columns | Key fields | Purpose |
|---|---:|---:|---|---|

### DATASET RELATIONSHIPS

Explain how the datasets can be connected and which join keys are reliable.

### AVAILABLE SIGNALS

Explain which useful energy/time-series features, metrics, constraints, or optimization inputs can actually be derived.

### DATA QUALITY RISKS

List issues that may affect implementation or scoring.

### DATA LIMITATIONS

Explain what cannot be reliably calculated or inferred from the provided data.

**Do not generate the 3 solution approaches until this dataset analysis is complete.**

---

# 5. UNDERSTAND THE ENERGY PROBLEM

Identify:

### Primary user

Exactly who uses this product?

Examples only:

- energy dispatcher
- energy manager
- facility operator
- grid/operator engineer
- energy company
- industrial consumer
- customs/energy operator
- energy analyst

Do not choose one until the task is known.

### Problem

Complete:

> The user currently has difficulty with __________.

### Current process

Explain how the process likely works without our solution, but clearly mark any assumptions.

### Desired result

Complete:

> After using our solution, the user can __________.

---

# 6. GENERATE EXACTLY 3 SOLUTIONS

Generate three substantially different solutions that satisfy the task.

For EACH:

## Solution name

Short memorable name.

## User

Who uses it?

## Problem

What exact energy pain does it solve?

## Input

What data enters the system?

## AI role

What does AI actually do?

## Algorithmic role

What deterministic optimization/calculation is used?

## Tools

What external or internal tools are needed?

## Output

What user receives?

## Killer demo

What is the single most impressive live moment?

## Five-hour feasibility

Can 2 people actually build it?

## Dependencies

What can fail?

## Scoring coverage

Which official criteria does this solution satisfy?

---

# 7. SELECT THE MVP

Choose the solution with the best combination of:

- task compliance
- scoring potential
- visible user value
- meaningful AI usage
- implementation feasibility
- low dependency risk
- demo clarity
- innovation
- scalability potential

Do NOT choose the most complex solution.

Prefer:

> Maximum visible value per hour of implementation.

Explain WHY.

---

# 8. DEFINE THE PRODUCT IN ONE SENTENCE

Use:

> For [USER], who struggles with [ENERGY PROBLEM], our platform uses [AI + ALGORITHM/TOOLS] to [ACTION], producing [RESULT] so that [BUSINESS VALUE].

If the sentence is complicated, simplify the project.

---

# 9. GOLDEN PATH

Design ONE primary workflow.

Example structure:

```text
USER
  ↓
Provides energy data
  ↓
SYSTEM validates data
  ↓
AI understands the situation
  ↓
Algorithm/tool calculates or retrieves required information
  ↓
AI interprets the result
  ↓
System generates energy recommendation/plan
  ↓
React visualizes result
  ↓
USER takes action
```

The golden path must be demonstrable in approximately 60–90 seconds.

---

# 10. AI MUST HAVE A REAL ROLE

Do not create a generic chatbot unless the official task requires conversation.

AI should perform meaningful work such as:

- energy request understanding
- document extraction
- constraint interpretation
- anomaly analysis
- planning
- recommendation
- exception handling
- tool selection
- scenario comparison
- explanation
- multimodal analysis
- natural-language control of optimization tools

Ask:

> Could a normal IF/ELSE application do the exact same thing?

If YES, redesign the AI layer.

---

# 11. DO NOT FORCE AI INTO OPTIMIZATION

Use deterministic algorithms where they are better.

Examples:

### AI

Good for:

- understanding requests
- extracting constraints
- interpreting documents
- explaining results
- selecting tools
- generating recommendations
- handling unstructured information

### Algorithms

Good for:

- load forecasting
- load dispatch/load scheduling
- dispatch/load scheduling
- resource/load allocation
- energy/load calculations
- capacity/grid constraints
- optimization
- energy cost calculations

A strong architecture may be:

```text
User
  ↓
AI understands constraints
  ↓
Optimization engine calculates
  ↓
AI interprets optimization result
  ↓
User receives actionable plan
```

Do NOT ask an LLM to mathematically guess optimal series when an optimization algorithm can calculate them correctly.

---

# 12. MODEL SELECTION

Do not automatically use the strongest model for everything.

Choose model based on task.

## Simple tasks

Examples:

- classification
- extraction
- formatting
- simple summaries

Use:

> fast / low-latency model

## Complex reasoning

Examples:

- multi-constraint planning
- complex exception analysis
- comparing scenarios

Use:

> stronger reasoning model

## Images / scanned documents

Use:

> multimodal vision-capable model

## Agent workflow

Use:

> model with reliable tool/function calling

## Coding during hackathon

Any permitted coding AI tool may be used unless the official task imposes a specific requirement.

Do not assume Codex is mandatory unless the task explicitly says so.

---

# 13. DEFAULT ARCHITECTURE

Prefer:

```text
React
   │
   ▼
FastAPI
   │
   ▼
AI Orchestrator
   │
   ├── AI Model
   ├── Energy Tool
   ├── Optimization Engine
   ├── External API
   └── Data Source
   │
   ▼
Structured JSON
   │
   ▼
React Dashboard / Chart / Result
```

Keep it simple.

---


# ENERGY-SPECIFIC SOLUTION SPACE

Do NOT assume the task is forecasting. Determine the actual problem from the official task and datasets first.

Common energy problem classes that MAY be relevant:

- electricity/load forecasting;
- peak demand prediction;
- anomaly detection;
- equipment condition monitoring;
- predictive maintenance;
- energy-efficiency optimization;
- demand-response recommendations;
- generation/load scheduling;
- tariff/cost optimization;
- renewable generation forecasting;
- energy-loss analysis;
- incident/event analysis;
- explainable operational recommendations.

For each proposed solution, determine whether the problem is primarily:

1. Forecasting
2. Classification
3. Anomaly detection
4. Optimization
5. Time-series analytics
6. Recommendation / decision support
7. Document/event understanding
8. Multimodal inspection

Do not force a forecasting model when a simpler analytical or optimization approach fits the task better.

---

# ENERGY METRICS

Use only metrics supported by the official task and datasets.

Possible examples:

- kW / MW;
- kWh / MWh;
- peak load;
- load factor;
- forecast MAE / RMSE / MAPE;
- anomaly score;
- efficiency;
- technical/commercial losses;
- utilization;
- downtime risk;
- energy cost;
- demand reduction;
- CO₂ estimate;
- processing time.

Never invent savings, efficiency gains, forecast accuracy, or CO₂ reductions.

---

# 14. BACKEND STACK

Default:

```text
Python 3.11+
FastAPI
Pydantic
Uvicorn
httpx
OpenAI SDK if required
```

Only add libraries that solve a real requirement.

Possible energy/data-science libraries IF REQUIRED:

```text
Pandas
NumPy
scikit-learn
XGBoost or LightGBM
statsmodels
Prophet
OR-Tools
SciPy
```

Do not install them without a reason.

---

# 15. FRONTEND STACK

Default:

```text
React
Vite
Axios or fetch
```

Use a chart library ONLY if energy chart visualization adds value.

Possible:

```text
Recharts
React Recharts
Plotly
```

Choose only ONE.

Do not add complex charts unless they materially improve understanding of the energy task and scoring criteria.

---

# 16. FRONTEND UX

The UI should immediately answer:

1. What data do I enter?
2. What is the system doing?
3. What result did I get?
4. Why is this result useful?
5. What should I do next?

Preferred structure:

```text
INPUT / CONTROL PANEL
        ↓
MAIN VISUALIZATION
        ↓
KEY METRICS
        ↓
AI / OPTIMIZATION RESULT
        ↓
RISKS / WARNINGS
        ↓
RECOMMENDED ACTION
```

---

# 17. STRUCTURED API CONTRACT

Backend should return structured JSON.

Do not make the React frontend parse arbitrary AI prose.

Example only:

```json
{
  "status": "success",
  "summary": "Optimized energy plan generated",
  "metrics": {
    "energy_km": 128.4,
    "estimated_time_minutes": 190,
    "estimated_cost": 42000
  },
  "series": [],
  "warnings": [],
  "recommendations": [],
  "explanation": ""
}
```

Adapt the schema to the official task.

---

# 18. API CONTRACT FIRST

Before Developer 1 and Developer 2 work independently, define:

```text
POST /api/analyze
POST /api/optimize
GET /api/result/{id}
```

These endpoints are EXAMPLES.

Create only endpoints needed by the official task.

Define request and response DTOs immediately.

---

# 19. MOCK-FIRST FRONTEND

Developer 1 MUST NOT wait for backend.

After agreeing on API schema:

Create realistic mock JSON.

Developer 1 builds React against mock data.

Developer 2 builds FastAPI so the real endpoint returns the SAME structure.

This enables parallel development.

---

# 20. TWO-PERSON TASK SPLIT

After MVP selection produce:

## Developer 1 — React / Product

Tasks with estimated minutes:

```text
F1
F2
F3
...
```

## Developer 2 — FastAPI / AI

Tasks with estimated minutes:

```text
B1
B2
B3
...
```

Also identify integration checkpoints.

---

# 21. MVP SCOPE

Create:

## MUST HAVE

Maximum 3 core features.

## NICE TO HAVE

Maximum 3.

## DO NOT BUILD

Explicitly list unnecessary features.

Typical DO NOT BUILD items:

- authentication unless mandatory
- user registration
- complex admin panel
- permissions system
- microservices
- Kubernetes
- queues
- Redis unless mandatory
- complex database architecture
- mobile app
- excessive agents
- excessive dashboards
- unnecessary CRUD
- complex settings

---

# 22. DATABASE RULE

Do not automatically add PostgreSQL.

Ask:

> Is persistent storage necessary for the judged scenario?

If NO:

Use:

- in-memory
- JSON
- CSV
- temporary state

If YES:

Use the simplest appropriate database.

The demo is more important than unnecessary persistence.

---

# 23. HOURLY PROGRESS RULE

The competition requires visible progress throughout the five-hour development period.

Create a plan that ensures a meaningful repository result by every hour.

Target:

## Hour 1

```text
Task analysis
Architecture
README skeleton
Running frontend/backend skeleton
API contract
```

COMMIT.

## Hour 2

```text
First real core function
AI/API connection
Basic result UI
```

COMMIT.

## Hour 3

```text
Core energy algorithm / tool
End-to-end connection begins working
```

COMMIT.

## Hour 4

```text
Full golden path
Metrics
Result visualization
Error handling
```

COMMIT.

## Hour 5

```text
Stable release
README finalized
Demo data
Tests
Presentation preparation
```

FINAL COMMIT BEFORE DEADLINE.

Ensure repository history clearly demonstrates progress.

---

# 24. TIME PLAN

Competition:

```text
13:00 → 18:00
```

Recommended:

## 13:00–13:25

ANALYZE

- read task
- read scoring
- identify mandatory requirements
- create 3 approaches
- select MVP

## 13:25–14:00

FOUNDATION

- architecture
- API contract
- FastAPI skeleton
- React skeleton
- mock response
- README skeleton

## 14:00–16:15

CORE DEVELOPMENT

Developer 1 and Developer 2 work in parallel.

Priority:

> Get the golden path working.

## 16:15–17:00

INTEGRATION

Test:

```text
React
→ FastAPI
→ AI / Algorithm / Tool
→ JSON
→ React
```

## 17:00

FEATURE FREEZE

Do not add major features after this point.

## 17:00–17:35

STABILIZE

Fix:

- crashes
- API errors
- invalid inputs
- broken UI
- AI malformed output
- integration errors

## 17:35–17:50

README + FINAL TEST

## 17:50–18:00

FINAL SUBMISSION CHECK

No risky changes.

---

# 25. README IS CRITICAL

Create README from the first hour.

Required sections:

```text
# Project Name

## Problem

## Solution

## Target User

## Main Scenario

## Architecture

## AI Usage

## Algorithms

## Tech Stack

## Installation

## Environment Variables

## How to Run Backend

## How to Run Frontend

## How to Test Main Scenario

## Demo Data

## Third-Party Components

## Limitations
```

A technical reviewer must be able to run the application without asking the team questions.

---

# 26. EXTERNAL SERVICE RULE

Avoid dependencies that judges cannot access.

If using:

- external API
- paid service
- account-based platform
- private API

provide:

- demo credentials if allowed
- test token if allowed
- public test environment
- fallback data

Never require a judge to use a developer's personal account.

---

# 27. FALLBACK STRATEGY

For every risky dependency define a fallback.

## AI API failure

Use:

> clearly labeled cached/demo result for presentation only.

Do not claim it is a live AI response.

## Chart API failure

Use:

> local/static coordinate dataset or OpenStreetChart-compatible fallback.

## External energy API failure

Use:

> clearly labeled mock adapter.

## Database failure

Use:

> local JSON/CSV if persistence is not core.

---

# 28. DISCLOSURE

Document all third-party components:

- libraries
- datasets
- APIs
- AI models
- templates
- open-source software

Do not hide their usage.

---

# 29. DATA SAFETY

Do NOT use:

- confidential corporate data
- personal customer data without lawful basis
- private medical information
- proprietary source code without rights
- secret credentials

Prefer:

- public data
- synthetic data
- anonymized data
- organizer-provided datasets

---

# 30. TESTING

Test at minimum:

### Happy path

Normal expected input.

### Empty/invalid input

Application does not crash.

### AI/API failure

Shows understandable error.

### Second dataset

Golden path must work on more than one hard-coded example.

---

# 31. DEMO DESIGN

The demo should focus on transformation.

Bad:

> "Here is our dashboard."

Good:

> "An energy dispatcher sees a peak-load risk but cannot quickly determine the best operational response."

Then show:

```text
INPUT
↓
PROCESS
↓
AI / OPTIMIZATION ACTION
↓
RESULT
↓
METRIC IMPROVEMENT
↓
NEXT ACTION
```

---

# 32. SHOW METRICS

Whenever possible show measurable value.

Examples:

```text
Energy
Time
Cost
Utilization
Number of assets
Peak events
Capacity usage
Risk
CO₂ estimate
Processing time
```

Do NOT invent improvement percentages.

Only show calculated, provided, or clearly labeled illustrative metrics.

---

# 33. DEMO DAY THINKING

Even during development optimize for:

### Value

Is the problem important and obvious?

### Result quality

Does the product actually work?

### Innovation

Is there something more than a generic dashboard/chatbot?

### Scalability

Can this become useful beyond one demo?

### Presentation

Can someone understand it in 60 seconds?

---

# 34. KILLER FEATURE RULE

Create ONE memorable capability.

Not five mediocre features.

Examples only:

- natural language → optimized energy plan
- live re-routing after disruption
- AI reads energy documents → creates energy event
- AI detects peak-load or equipment risk → automatically proposes an alternative action
- compare scenarios → choose optimized plan
- explainable energy optimization

The actual killer feature must follow the official task.

---

# 35. CODING AGENT INSTRUCTION

When asking an AI coding tool to implement something:

```text
Inspect the repository first.

Do not rewrite working code unnecessarily.

Implement only the currently approved feature.

Before coding:
1. identify relevant files
2. state the minimal implementation plan
3. identify dependencies

Then:
IMPLEMENT
→ RUN
→ TEST
→ FIX

Do not introduce new architecture unless necessary.

Prioritize a working hackathon demo over perfect enterprise architecture.
```

---

# 36. BUG-FIX MODE

After feature freeze:

```text
Switch to stabilization mode.

Do NOT:
- add major features
- replace frameworks
- refactor working architecture
- introduce unnecessary libraries
- redesign the application

Find P0:
- application cannot start
- main scenario broken
- backend/frontend disconnected
- AI/tool unavailable

Find P1:
- malformed result
- crashes on normal input
- broken loading state
- missing key metric
- unreadable UI

Fix P0 first.
Then P1.
```

---

# 37. FINAL CHECKLIST

Before final submission:

```text
[ ] Official task requirements satisfied
[ ] Scoring criteria chartped to features
[ ] Repository contains actual development history
[ ] Hourly progress visible
[ ] Backend starts
[ ] Frontend starts
[ ] Main scenario works
[ ] Second test scenario works
[ ] AI has meaningful role
[ ] Optimization is deterministic where appropriate
[ ] API contract stable
[ ] README complete
[ ] Installation instructions tested
[ ] Environment variables documented
[ ] Third-party components disclosed
[ ] No secret keys committed
[ ] Demo dataset included
[ ] External dependency fallback available
[ ] UI clearly shows result
[ ] Metrics visible
[ ] Demo rehearsed
```

---

# 38. DECISION RULE

Every time someone proposes a new feature ask:

> Does this directly improve our score, core energy result or demo?

If NO:

DO NOT BUILD IT.

---

# 39. FINAL PRINCIPLE

Our winning formula is:

```text
ONE REAL ENERGY PROBLEM
+
ONE CLEAR USER
+
ONE STRONG WORKFLOW
+
AI WHERE AI IS USEFUL
+
ALGORITHMS WHERE ALGORITHMS ARE BETTER
+
WORKING PRODUCT
+
MEASURABLE RESULT
+
MEMORABLE DEMO
```

---

# START COMMAND

When the official Energy Track 01 Energy task and the provided datasets are available in the repository:

1. Read this HACKATHON.md completely.
2. Read the COMPLETE official task.
3. Read ALL task-specific scoring criteria and points.
4. Locate and inspect **ALL provided CSV datasets**.
5. **DO NOT WRITE APPLICATION CODE YET.**
6. Do NOT create React or FastAPI yet.
7. Do NOT modify the official task or the original datasets.
8. Extract ALL mandatory requirements from the official task.
9. Build the complete scoring chart.
10. Perform the full **DATASET ANALYSIS** defined in this file:
    - schema;
    - row/column counts;
    - representative rows;
    - missing/null values;
    - duplicates;
    - identifiers;
    - relationships;
    - join keys;
    - available signals;
    - target/output fields if present;
    - energy constraints;
    - data-quality risks;
    - limitations.
11. Determine what can ACTUALLY be calculated from the provided data.
12. Generate exactly THREE substantially different solution approaches.
13. For each solution evaluate:
    - task compliance;
    - scoring coverage;
    - implementation complexity;
    - AI necessity;
    - algorithm/optimization requirements;
    - dataset usage;
    - external dependencies;
    - biggest technical risk;
    - feasibility for 2 developers in 5 hours.
14. Select the strongest feasible MVP.
15. Define ONE killer feature.
16. Decide what should be solved by:
    - AI/LLM;
    - deterministic Python algorithm;
    - optimization library;
    - ML only if genuinely necessary.
17. Recommend the appropriate AI model/class of model for each AI operation.
18. Define the minimum architecture.
19. Define the JSON API contract between React and FastAPI.
20. Split work between:
    - Developer 1: React + UI/UX + dashboard/chart + visualization + demo.
    - Developer 2: Python + FastAPI + AI + algorithms + integration.
21. Create the hourly Git commit/progress plan.
22. Produce the first 60-minute implementation plan.
23. Identify anything that could prevent judges from installing, running, or verifying the project.

HACKATHON CONSTRAINT:

We have only **5 hours**.

Optimize for:

> maximum scoring coverage  
> + working end-to-end MVP  
> + low implementation risk  
> + measurable result  
> + memorable demo

Do not overengineer.

Return the analysis in this exact order:

A. TASK SUMMARY  
B. MANDATORY REQUIREMENTS  
C. DATASET ANALYSIS  
D. SCORING MATRIX  
E. 3 SOLUTION OPTIONS  
F. RECOMMENDED MVP  
G. KILLER FEATURE  
H. AI MODEL / ALGORITHM SELECTION  
I. ARCHITECTURE  
J. API CONTRACT  
K. DEVELOPER 1 TASKS  
L. DEVELOPER 2 TASKS  
M. 5-HOUR PLAN  
N. RISKS  
O. FIRST 60-MINUTE ACTION PLAN

Then **STOP**.

Wait for our approval.

**DO NOT START IMPLEMENTATION until we explicitly approve the MVP and architecture.**
