---
name: sbem-feature-kickoff
description: >-
  Bootstrap and initialize a new feature or bugfix in SBEMimage using spec-driven development.
  Use whenever the user asks to start, plan, bootstrap, or begin working on a new feature,
  issue, or fix in SBEMimage (e.g. "start working on a new feature", "create a worktree for...",
  "new feature: ...", "let's work on ...").
---

# SBEMimage Feature Kickoff & Lifecycle Protocol

Follow this runbook to bootstrap and initialize any new feature or bugfix in SBEMimage. This ensures strict adherence to project constraints, domain knowledge preservation, and spec-driven development.

---

## Phase 1: Feature Metadata & Worktree Provisioning

1. Determine the feature parameters:
   - **Feature Name / Topic**: e.g., `focus-map-interpolation`
   - **Branch Name**: `feat/<name>` (or `fix/<name>`)
   - **Worktree Directory**: `sbemimage-<name>` (placed in `/Users/ganctoma/SW/workspaces/sbemimage-workspace/`)
   - **Parent Branch**: `dev-tomgan-rel` (always default to `dev-tomgan-rel` unless user explicitly requests otherwise)

2. Provision the worktree using the automated script:
   ```bash
   /Users/ganctoma/SW/workspaces/sbemimage-workspace/sbem-worktree <branch-name> <dir-name> dev-tomgan-rel
   ```

   This automatically:
   - Creates the branch and git worktree.
   - Symlinks the Python 3.7.6 Conda environment (`sbem-py37`) to `.venv`.
   - Injects the active worktree into the Conda `.pth` path.
   - Copies `.antigravitygitignore`.
   - Scaffolds `docs/feature-architecture/<feature-slug>/` with the 5 core documents:
     - `prd.md`
     - `tasks.md`
     - `knowledge.md`
     - `<slug>_architecture.md`
     - `verification.md`
   - Sets up `.agent -> docs/feature-architecture/<feature-slug>/` for a single source of truth.
   - Adds a placeholder in `docs/feature-architecture/README.md`.

---

## Phase 2: Domain Context & Boundary Discovery

Before writing any implementation code, gather domain context:

1. **Check Existing Knowledge**:
   - Inspect `docs/feature-architecture/` to see if related hardware, optical, or stage dynamics were documented in prior features.
   - Check `GEMINI.md` for project-wide hard constraints.
2. **Define System Boundaries**:
   - **System Objective**: 1–2 clear sentences stating what the feature accomplishes.
   - **In-Scope Boundaries**: Exact list of files in `src/`, `gui/`, or `tests/` to modify.
   - **Anti-Targets**: Explicit declarations of what NOT to touch (e.g., *"Do not refactor legacy PyQt GUI code outside feature scope"*, *"Do not touch magc/*").
3. **Hardware & Physical Dynamics**:
   - Identify electron optics behavior, deflector settling times, stage motor tolerances, SmartSEM coordinate conventions, or microtome cutting dynamics.
   - Record these in `docs/feature-architecture/<slug>/knowledge.md`.

---

## Phase 3: Top-Down Specification & Tasks

Populate the scaffolded files in `docs/feature-architecture/<slug>/` (or via `.agent/`):

1. **`prd.md`**:
   - Fill in System Objective, Hard Constraints (strictly Python 3.7.6, no walrus `:=`, `typing` generics, no PEP 604 unions), In-Scope Boundaries, and Anti-Targets.
2. **`tasks.md`**:
   - Organize into logical phases (Phase 1: Interfaces & Spec, Phase 2: Implementation & Tests, Phase 3: Release Candidate & Docs).
3. **`verification.md`**:
   - List automated pytest commands (`~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_...`) and manual microscope verification steps.

---

## Phase 4: User Approval Gate

- Present the proposed objective, scope boundaries, anti-targets, and execution plan to the user.
- **STOP and wait for user approval** before writing or modifying any source files in `src/` or `gui/`.

---

## Phase 5: Feature Lifecycle Rules during Development

1. **Python 3.7.6 Strictness**:
   - Environment: `~/miniforge3/envs/sbem-py37`.
   - Never use walrus `:=`, `list[str]` (use `typing.List[str]`), `int | None` (use `typing.Optional[int]`), or `f"{var=}"`.
2. **Respect `.antigravitygitignore`**:
   - Never access or index `magc/`.
3. **Test Discipline & Token Optimization**:
   - **Fast Pre-Flight Syntax Check**: Before running full tests, verify modified files with a lightweight syntax check to avoid heavy pytest traceback token bloat:
     `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/<modified_file>.py`
     *(Or: `flake8 src/<file>.py --select=E9,F63,F7,F82` to catch syntax errors and undefined variables in 1-2 lines).*
   - **Token-Optimized Test Runner**: Use `agent_test.py` instead of raw verbose pytest:
     `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_<feature>.py`
     *(Emits compact JSON reporting, suppresses warnings, and limits tracebacks to the last 2 frames, saving 80–90% of context tokens).*
   - **Targeted Scope**: Always target specific test files or methods (`-k <test_name>`) rather than running full test suites.
4. **Release Candidate Procedure**:
   - Write user documentation in `docs/` (e.g. `docs/<feature>_help.md`).
   - Finalize mathematical architecture in `docs/feature-architecture/<slug>/<slug>_architecture.md`.
   - Perform code review.
   - Squash all development commits into a single descriptive commit.
   - Fast-forward merge into `dev-tomgan-rel` and push to `origin` and `usb`.
   - Clean up the feature branch and worktree.
