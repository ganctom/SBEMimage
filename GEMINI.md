# SBEMimage Project Rules

## 1. Hard Constraints
- **Python Version**: STRICTLY Python 3.7.6. The environment is located at `~/miniforge3/envs/sbem-py37`.
  - **NO walrus operator** (`:=` is 3.8+).
  - **NO PEP 585 generics** (`list[str]`); you MUST use `typing.List[str]`.
  - **NO PEP 604 unions** (`int | None`); you MUST use `typing.Optional[int]` or `typing.Union`.
  - **NO f-strings with `=`** (e.g. `f"{var=}"` is 3.8+).

## 2. Philosophy of Software Design
- **Minimize System Complexity**: Fight change amplification and cognitive load. The root causes of complexity are dependencies and obscurity.
- **Deep Interfaces (Ousterhout)**: Prefer "deep" modules and classes where the interface is much simpler than the implementation. Hide complexity behind clean APIs.
- **Single Responsibility (SRP)**: Apply SRP primarily at the function/method level to ensure they are easily testable. Do not over-decompose classes if it leads to "shallow" interfaces and fragmented logic.
- **Strategic Programming**: Invest time in robust design over tactical (hacky) fixes.
- **Rule of Three**: Prevent premature abstraction. Defer creating abstract base classes (ABCs) or protocols until there are at least three concrete use cases.

## 3. Workflow & Architecture Strategy
- **Top-Down Specification**: For new features, always start with a top-down architecture specification. Define the interfaces and data structures before writing implementation logic. Look at the existing SBEMimage architecture to reverse-engineer and match existing patterns.
- **TDD / Bottom-Up**: Use TDD only when the goal is completely clear and the interfaces are already validated (e.g., implementing an already-designed interface).
- **Proof of Concepts (POC/POP)**: Keep quick exploratory code as isolated modules. Do not pollute the core codebase with experimental features until they are validated.

## 4. Codebase Map
- `src/`: Core logic and backend components.
- `gui/`: PyQt user interface code.
- `dm/`: scripts for Digital Micrograph (part of the Gatan Microscopy Suite that serves for interfacing SBEMimage and ultr-microtome for Serial Block-Face Imaging).
- `tests/`: Unit and integration tests.
*(Note: `magc/` is intentionally excluded from AI context via `.antigravitygitignore`)*

## 5. Feature Lifecycle & Automation Protocol
1. **Dedicated Worktree**: Always provision feature worktrees using:
   `../sbem-worktree <branch-name> <dir-name> dev-tomgan-rel`
   (Defaults parent branch to `dev-tomgan-rel`, configures Python 3.7.6 Conda environment, injects `.pth`, and copies `.antigravitygitignore`).
2. **Architecture Documentation Registry**:
   Every feature must be tracked in `docs/feature-architecture/<feature-slug>/`:
   - `prd.md`: System objectives, hard constraints, in-scope files, anti-targets.
   - `tasks.md`: Phased execution ledger.
   - `knowledge.md`: Physical dynamics, electron optics, SmartSEM polarities, settling times.
   - `<feature>_architecture.md`: Mathematical equations and pipeline.
   - `verification.md`: Automated pytest suite and physical microscope testing routines.
   - Note: `.agent/` is symlinked to `docs/feature-architecture/<feature-slug>/` for a single source of truth.
3. **Spec-Driven Gating**:
   Always establish domain boundaries, interfaces, and PRD with the user before writing any functional implementation in `src/` or `gui/`.
4. **Testing Discipline & Token Conservation**:
   - Run only relevant tests (`tests/test_<feature>.py`) or functions (`-k <name>`).
   - Run lightweight pre-flight syntax checks (`python -m py_compile src/<file>.py` or `flake8 --select=E9,F63,F7,F82`) before pytest to prevent giant crash tracebacks from polluting context.
   - Prefer token-optimized test harness (`python agent_test.py tests/test_<feature>.py`) which yields clean JSON summaries with truncated diffs and 2-frame tracebacks.
5. **Release Candidate Procedure**:
   - Write/update user documentation in `docs/` (e.g. `docs/<feature>_help.md`).
   - Conduct a formal code review artifact.
   - Squash development commits into a single descriptive commit.
   - Fast-forward merge into `dev-tomgan-rel` and push to `origin` and `usb`.
   - Delete the feature branch and remove its worktree.
