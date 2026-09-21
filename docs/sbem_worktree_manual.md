# `sbem-worktree` Command Manual

`sbem-worktree` is an automated provisioning script designed for SBEMimage feature development. It provisions isolated git worktrees, configures the Python 3.7.6 Conda environment, establishes Antigravity/IDE settings, injects active Python search paths, and bootstraps the feature architecture documentation suite.

---

## 1. Syntax

```bash
./sbem-worktree <branch-name> <worktree-dir-name> [base-ref]
```

### Parameters
- `<branch-name>`: Name of the git branch to create or checkout (e.g. `feat/focus-interpolation` or `fix/stage-limits`).
- `<worktree-dir-name>`: Directory name for the new worktree, placed in `/Users/ganctoma/SW/workspaces/sbemimage-workspace/` (e.g. `sbemimage-focus`).
- `[base-ref]` *(Optional)*: Parent branch to branch off from. Defaults to **`dev-tomgan-rel`**.

---

## 2. Usage Examples

### Standard New Feature (defaults to `dev-tomgan-rel`)
```bash
cd /Users/ganctoma/SW/workspaces/sbemimage-workspace
./sbem-worktree feat/focus-map sbemimage-focus
```

### Specifying a Custom Parent Branch
```bash
./sbem-worktree fix/motor-timeout sbemimage-timeout origin/master
```

---

## 3. What the Script Automates

When executed, `sbem-worktree` performs the following steps in sequence:

1. **Git Worktree Provisioning**:
   - Fetches the latest refs from `origin` and `usb`.
   - Creates a new branch from `base-ref` and provisions an isolated worktree at `../<worktree-dir-name>`.
2. **Conda Environment Integration (`sbem-py37`)**:
   - Symlinks the Conda environment (`~/miniforge3/envs/sbem-py37`) to `<worktree>/.venv` for automatic IDE interpreter detection.
   - Creates `.antigravity/settings.json` and `.vscode/settings.json` pointing `python.defaultInterpreterPath` to the Conda Python binary.
3. **Active Worktree Python Path Injection (`.pth`)**:
   - Writes the new worktree path into `sbemimage_active_worktree.pth` inside Conda's `site-packages`, ensuring imports resolve to the active worktree.
4. **Agent Ignore Rules**:
   - Copies `.antigravitygitignore` from `main_repo` into the worktree to keep `magc/`, caches, and build artifacts excluded from AI context.
5. **Feature Architecture Scaffolding (`docs/feature-architecture/<slug>/`)**:
   - Computes a clean feature slug (e.g. `feat/focus-map` $\to$ `focus-map`).
   - Scaffolds the 5 core documents:
     - `prd.md`: System objectives, hard constraints (Python 3.7.6, no walrus `:=`, `typing` generics), in-scope files, and anti-targets.
     - `tasks.md`: Phased execution checklist.
     - `knowledge.md`: Physical optics, deflector settling, SmartSEM polarities, and stage dynamics.
     - `<slug>_architecture.md`: Mathematical equations and pipeline architecture.
     - `verification.md`: Automated pytest commands and physical microscope verification protocol.
6. **Single Source of Truth (`.agent` Symlink)**:
   - Creates a relative symlink: `.agent -> docs/feature-architecture/<slug>/`.
   - Edits made by the AI in `.agent/` directly update the version-controlled documentation in `docs/feature-architecture/`.
7. **Feature Registry Update**:
   - Automatically registers an "In Progress" entry in `docs/feature-architecture/README.md`.

---

## 4. Development Workflow with Antigravity

1. **Open Worktree**:
   Open the newly created directory (e.g. `/Users/ganctoma/SW/workspaces/sbemimage-workspace/sbemimage-focus`) in Antigravity or VS Code.
2. **Kickoff Feature with AI**:
   Prompt the agent:
   > *"Start working on feature focus-map"*
   The agent activates the `sbem-feature-kickoff` skill, reads `GEMINI.md`, interviews you for domain boundaries, and completes `prd.md`, `knowledge.md`, and `tasks.md` before coding.
3. **Run Relevant Tests**:
   ```bash
   ~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_<feature>.py
   ```
4. **Release Candidate & Merge**:
   - Update user documentation (`docs/<feature>_help.md`).
   - Finalize `<feature>_architecture.md`.
   - Squash development commits into a single descriptive commit.
   - Fast-forward merge into `dev-tomgan-rel` in `main_repo` and push to `origin` and `usb`.

---

## 5. Teardown & Worktree Cleanup

Once the feature has been merged into `dev-tomgan-rel` and pushed:

```bash
# In main_repo:
git worktree remove /Users/ganctoma/SW/workspaces/sbemimage-workspace/<worktree-dir-name>
git branch -d <branch-name>
git push origin --delete <branch-name>   # (Optional) delete remote branch
```
