# Codex Execution Plans for this repository

An ExecPlan is a living implementation document for one approved phase or another complex change. It must allow a new contributor with only the working tree and that plan to continue safely. Chat history is never a dependency.

## When to use an ExecPlan

Use one for every roadmap phase, work spanning multiple subsystems, migrations, expensive data experiments, or changes with unresolved technical risk. A small isolated fix may use a lightweight in-turn plan, but it still must satisfy the relevant specification and tests.

Only one roadmap phase should normally be active. Do not create detailed plans for all future phases before their inputs exist. At the end of a phase, archive its final plan; after any required human approval, author the next active plan from the observed repository state.

## Required qualities

Every active ExecPlan must be:

- Self-contained: define the purpose, current repository state, assumptions, terms, paths, commands, expected observations, and recovery steps needed to execute it.
- Outcome-oriented: acceptance describes behavior a person can observe, a report that can be inspected, or a test that demonstrably passes.
- Living: update progress, discoveries, decisions, validation evidence, and the exact next step whenever work pauses.
- Safe and repeatable: steps should be idempotent where practical; destructive or expensive steps include retry and recovery guidance.
- Honest about uncertainty: hypotheses, target metrics, confirmed facts, and human decisions must not be blended together.

The plan may reference checked-in source-of-truth documents, but it must restate the constraints needed to avoid unsafe or incorrect work. A bare instruction such as “follow the spec” is insufficient.

## Required sections

Use these headings in this order:

1. `# <Outcome-oriented title>`
2. `## Purpose and observable outcome`
3. `## Progress` — timestamped checklist; this is the only section that should be primarily a checklist.
4. `## Surprises and discoveries` — facts learned during execution, with evidence.
5. `## Decision log` — decision, rationale, date, and whether human approval is required.
6. `## Outcomes and retrospective` — final result, gaps, and lessons; complete before archiving.
7. `## Context and orientation` — current paths, concepts, dependencies, and starting state.
8. `## Scope` — in scope and explicitly out of scope.
9. `## Plan of work` — prose describing the implementation sequence and why it is ordered that way.
10. `## Milestones` — each milestone ends in a separately observable, testable state.
11. `## Concrete commands and expected observations`
12. `## Validation and acceptance`
13. `## Idempotence and recovery`
14. `## Interfaces and artifacts`
15. `## Handoff` — exact next action for a fresh session and any blocking question.

## Progress rules

Use status values `Pending`, `In progress`, `Needs review`, `Blocked`, and `Completed`. Add a UTC timestamp in ISO 8601 form whenever an item starts, completes, or becomes blocked; an untouched pending item does not need an invented timestamp. Split partially completed work so the plan does not claim more than the repository proves. Record test failures and negative results; do not rewrite history to show only success.

Update `docs/exec-plans/ROADMAP.md` only when phase-level status, dependencies, or scope change. Put detailed work evidence in the active ExecPlan. Put durable cross-phase choices in `docs/DECISIONS.md`.

## Milestones and acceptance

A milestone should fit one coherent implementation and verification loop. Prefer “the health endpoints start against PostgreSQL and their contract tests pass” over “backend scaffolding complete.” State the working directory, exact commands, expected exit status, and key output or artifact. When a fixed numeric threshold exists in `PROJECT_SPEC.md`, repeat it in the active plan.

If feasibility is unknown, the first milestone should be a bounded experiment that produces evidence and a decision point. Do not build downstream production code before that uncertainty is resolved.

## Handoff and completion

Before pausing, make the plan match reality and name the first incomplete action. Before marking `Completed`, run the full phase acceptance suite, record outputs and artifact paths, check for secrets and prohibited data, and fill in the retrospective. At an approval gate, set `Needs review` and stop. Move a plan to `completed/` only after approval or when the roadmap explicitly has no gate.

Do not push, deploy, purchase a service, or start a later phase merely because a plan is complete. Those actions require their own authorization or gate.
