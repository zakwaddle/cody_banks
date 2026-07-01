# Cody Banks

Cody Banks is a local-first coding agent skeleton intended to run from a terminal inside a project workspace.

## Current milestone

Phase 1 provides the Python project structure and a minimal executable entry point.
Phase 2 adds a minimal OpenAI-compatible chat completions client for local model servers such as llama.cpp.
Phase 3 adds the basic interactive agent loop with JSON tool requests, shell execution, and permission prompts.
Phase 4 adds workspace file, search, and shell tools with workspace path validation.
Phase 5 adds the explicit permission risk model and permission modes.
Phase 6 shows unified diffs before modifying existing files and logs tool results.
Phase 7 persists session event streams locally.
Phase 8 expands the runtime system prompt and adds manually loaded markdown skills.
Phase 9 adds read-only git awareness, dirty-file warnings, and final task status output.
Phase 10 adds a local keyword index and retrieval helper under `.cody/index/`.
Phase 11 adds patch, create, rename, and delete editing tools.
Phase 12 adds validation command approval, compact output, and failure summaries.
Phase 13 adds terminal slash commands.
Phase 14 documents the optional TUI plan and defers implementation.
Phase 15 makes `.cody/memory.md` a first-class project memory file with explicit memory commands.
Phase 16 adds Roadmap Mode for planning tasks into saved `.cody/roadmaps/` markdown files before execution.
Phase 17 adds Execution Mode for following saved roadmaps step by step and updating checkbox progress.
Phase 18 adds automatic markdown skill loading during roadmap creation and execution.

## Installation

Cody Banks requires Python 3.11 or newer. From this repository, install it as a global user command with:

```bash
python -m pip install --user .
```

That installs the `cody` console script. If your shell cannot find it, make sure Python's user script directory is on `PATH`:

```bash
python -m site --user-base
```

The command above prints a base directory. The executable is usually in its `bin` subdirectory on macOS/Linux, or its `Scripts` subdirectory on Windows.

For active development, use an editable install instead:

```bash
python -m pip install --user -e .
```

If you use `pipx`, you can also install the command in an isolated environment:

```bash
pipx install .
```

After installation, run Cody Banks from the project directory you want it to operate on:

```bash
cody
```

Send a one-shot prompt to a running local endpoint:

```bash
cody --prompt "Say hello in one sentence."
```

You can also run without installing while developing:

```bash
python -m cody_banks.cli
```

Or send a one-shot prompt with the module entry point:

```bash
python -m cody_banks.cli --prompt "Say hello in one sentence."
```

The model can request tools with fenced JSON:

```json
{
  "tool": "read_file",
  "args": {
    "path": "README.md"
  }
}
```

Available tools:

- `read_file(path)`
- `write_file(path, content)`
- `create_file(path, content)`
- `edit_file(path, old, new)`
- `apply_patch(patch_text)`
- `rename_file(old_path, new_path)`
- `delete_file(path)`
- `list_files(path=".")`
- `search_text(query, path=".")`
- `index_project()`
- `retrieve_context(query, limit=8)`
- `shell(cmd)`

The permission gate allows safe inspection commands, prompts for risky commands and file writes, blocks mutations in `read-only`, and requires manual override for clearly destructive or credential-sensitive shell commands.

When `write_file` replaces an existing file or `edit_file` changes exact text, Cody Banks prints a unified diff before applying the change. Tool activity is logged to `data/logs/tools.jsonl`.

Exact replacement with `edit_file` remains the default safe edit path. `apply_patch` is available for unified diffs, while `delete_file` always requires explicit `y/n` approval.

Validation commands such as `pytest`, `python -m pytest`, `npm test`, `npm run build`, `ruff check`, and `mypy` require approval the first time they run in a session. Approved validation commands are remembered for that session, and failed output is summarized compactly.

Slash commands in the interactive loop:

- `/help`
- `/status`
- `/model`
- `/permissions`
- `/memory show`
- `/memory add TEXT`
- `/memory search QUERY`
- `/memory prune`
- `/roadmap`
- `/roadmap latest`
- `/roadmap new TASK`
- `/execute latest`
- `/execute PATH`
- `/compact`
- `/clear`
- `/exit`

Project memory lives at `.cody/memory.md`. Cody creates it automatically and reads it into task context as durable background knowledge. Use it for stable project facts, architectural decisions, coding conventions, user preferences, known risks, recurring warnings, and durable lessons learned. Do not use it for full transcripts, raw tool output, temporary task plans, or speculative notes.

`/compact` no longer writes session transcripts into memory. It now reminds you to add only durable lessons with `/memory add TEXT`.

Roadmaps live under `.cody/roadmaps/` with timestamped filenames like `YYYYMMDD-HHMM-task-name.md`. Use `/roadmap new TASK` to create a planning roadmap before making changes. Roadmap Mode can inspect files, search, retrieve context, inspect git state, run safe read-only inspection commands, and draft assumptions or clarifying questions, but it cannot edit project files or run mutating commands.

Use `/execute latest` or `/execute PATH` to follow a saved roadmap. Execution Mode identifies the next unchecked step, executes only that step, marks it complete when successful, records execution notes in the roadmap, and pauses when assumptions break, validation fails, required files are missing, or the next action would be risky.

During roadmap creation, Cody automatically loads relevant markdown skills from `cody_banks/skills/` using simple keyword and file-pattern matching. Roadmaps record loaded skills in a `# Loaded Skills` section, and Execution Mode reloads those named skills before working on roadmap steps.

The optional TUI is intentionally deferred. Notes live in `cody_banks/tui.md`.

Each agent session is written to `data/sessions/YYYYMMDD-HHMMSS.jsonl` with user messages, assistant messages, tool requests, permission decisions, tool results, and final answers.

Reusable skills live in `cody_banks/skills/` and are loaded automatically for roadmap creation and execution when simple task matching identifies them.

When the workspace is a git repository, Cody Banks shows branch, dirty files, and diff summaries before and after each turn. It warns before editing files that were already dirty at the start of the turn and suggests a commit message without committing.

Project retrieval starts with keyword search and then falls back to indexed file summaries. The local index is stored at `.cody/index/project_index.json`; vector search is intentionally deferred.

Use a TOML config file to change model settings:

```toml
[model]
base_url = "http://localhost:8080/v1"
api_key = "local"
model = "local-model"
temperature = 0.2
max_tokens = 4096

[permissions]
mode = "ask"
```

Permission modes are `ask`, `read-only`, and `auto`.
