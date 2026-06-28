# Cody Banks

Cody Banks is a local-first coding agent skeleton intended to run from a terminal inside a project workspace.

## Current milestone

Phase 1 provides the Python project structure and a minimal executable entry point.
Phase 2 adds a minimal OpenAI-compatible chat completions client for local model servers such as llama.cpp.
Phase 3 adds the basic interactive agent loop with JSON tool requests, shell execution, and permission prompts.
Phase 4 adds workspace file, search, and shell tools with workspace path validation.
Phase 5 adds the explicit permission risk model and permission modes.

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
- `shell(cmd)`

The permission gate allows safe inspection commands, prompts for risky commands and file writes, blocks mutations in `read-only`, and requires manual override for clearly destructive or credential-sensitive shell commands.

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
