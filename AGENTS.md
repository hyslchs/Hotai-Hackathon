# yoxi AI Demo repository guide

This file is the map, not the complete specification. Read only the documents needed for the current task.

## Start here

1. Inspect `git status` and the current tree. Preserve user changes and do not assume the repository is empty.
2. Read `docs/exec-plans/ROADMAP.md` to identify the current phase, its dependencies, and any human decision gate.
3. If an active plan exists, read the relevant file in `docs/exec-plans/active/` in full and continue from its first incomplete milestone.
4. Read the relevant sections of `docs/PROJECT_SPEC.md` and the subsystem map in `docs/ARCHITECTURE.md`.
5. Consult `docs/DECISIONS.md` before changing an accepted architecture, data rule, model, policy, or product claim.

For complex features, significant refactors, or any phase-sized work, use an ExecPlan governed by `docs/PLANS.md`. Keep that plan current while working. A fresh Codex session must be able to resume from the repository and the active plan without relying on chat history.

## Sources of truth

When instructions conflict, use this order:

1. Safety, privacy, data-handling, acceptance, and prohibition rules in `docs/PROJECT_SPEC.md`.
2. Reproducible observations from the current data, code, and automated tests.
3. Accepted entries in `docs/DECISIONS.md`.
4. The current active ExecPlan.
5. Slides, mockups, and informal notes.
6. Agent assumptions.

Never silently resolve a conflict that can change a research conclusion, user-visible behavior, privacy posture, external API policy, budget, or project scope. Record the evidence and stop at the applicable human decision gate.

## Working boundaries

- Work on one roadmap phase at a time. Do not start a later phase because it appears convenient.
- Deliver observable behavior and evidence, not merely new files or compiling code.
- Fit models, scalers, clustering, similarity data, popularity statistics, and weights only on the data split permitted by the spec.
- Ranking must remain deterministic and reproducible. An LLM may phrase evidence but may not decide ranking.
- Do not expose or commit raw trip data, real rider identifiers, secrets, unauthorized brand assets, or restricted Google Places responses.
- Use repository-relative paths in plans and reports. Provide exact commands and expected observations.
- Make changes idempotent where practical. Document recovery steps for migrations or expensive pipelines.
- Do not push, create a PR, deploy, purchase services, or change remote configuration unless the user explicitly asks.
- Do not overwrite unrelated changes or use destructive Git commands.

## Verification expectations

Run the narrowest relevant tests during implementation and the phase acceptance commands before marking a milestone complete. Record commands, results, metrics, artifact locations, and remaining limitations in the active ExecPlan. If a prescribed command does not yet exist, create the smallest consistent entry point or document the temporary equivalent and its replacement.

## Plan lifecycle

- `docs/exec-plans/active/` contains only plans currently approved for execution.
- `docs/exec-plans/completed/` contains finished plans with final evidence and retrospective notes.
- `docs/exec-plans/ROADMAP.md` is the portfolio view; it is not a substitute for a self-contained active ExecPlan.
- When a phase reaches `Needs review`, stop before the next gated phase. After approval, archive the plan and author the next plan using the repository's observed state.

## Key commands

The target command surface is described in `docs/PROJECT_SPEC.md` section 19. During Phase 0, establish and verify these commands rather than assuming they already work:

    make bootstrap
    make data-audit
    make cluster-experiments
    make preprocess
    make evaluate
    make load-db
    make dev
    make test
    make e2e
    make demo-check

