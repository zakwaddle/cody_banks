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

Run locally with:

```bash
python -m cody_banks.cli
```

Send a one-shot prompt to a running local endpoint:

```bash
python -m cody_banks.cli --prompt "Say hello in one sentence."
```

Start the interactive agent loop:

```bash
python -m cody_banks.cli
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
- `edit_file(path, old, new)`
- `list_files(path=".")`
- `search_text(query, path=".")`
- `index_project()`
- `retrieve_context(query, limit=8)`
- `shell(cmd)`

The permission gate allows safe inspection commands, prompts for risky commands and file writes, blocks mutations in `read-only`, and requires manual override for clearly destructive or credential-sensitive shell commands.

When `write_file` replaces an existing file or `edit_file` changes exact text, Cody Banks prints a unified diff before applying the change. Tool activity is logged to `data/logs/tools.jsonl`.

Each agent session is written to `data/sessions/YYYYMMDD-HHMMSS.jsonl` with user messages, assistant messages, tool requests, permission decisions, tool results, and final answers.

Reusable skills live in `cody_banks/skills/` and can be manually loaded into context when relevant.

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

After installation, the console command is:

```bash
cody
```
