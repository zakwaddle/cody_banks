# Cody Banks Roadmap

Cody Banks is a local-first coding agent: a folder-aware assistant that can read a project, plan changes, edit files, run safe commands, ask before risky commands, and keep its own reusable skills. The goal is not to clone Codex exactly. The goal is to build the useful shape of Codex or Claude Code in a way that is inspectable, hackable, and able to run against local GGUF models through llama.cpp.

## Working assumptions

The first version should run from a terminal inside a project folder. It should treat the current folder as the workspace root unless another path is provided. It should not modify files outside that root without explicit confirmation. It should use a local OpenAI-compatible endpoint, probably llama.cpp server, so the model can be swapped by changing configuration rather than rewriting the agent.

The agent should begin simple: one chat loop, one workspace, a handful of tools, a permission gate, and persistent logs. Everything else can grow out of that.

## Phase 1 — Project skeleton

Create a small Python project named `cody_banks`.

Use a structure roughly like this:

```text
cody_banks/
  README.md
  roadmap.md
  pyproject.toml
  .gitignore
  cody_banks/
    __init__.py
    cli.py
    config.py
    llm.py
    session.py
    workspace.py
    permissions.py
    tools/
      __init__.py
      shell.py
      files.py
      search.py
    prompts/
      system.md
    skills/
      README.md
  data/
    sessions/
    logs/
```

The first executable target should be:

```bash
cody
```

or, before packaging:

```bash
python -m cody_banks.cli
```

The first run should print the detected workspace root, model endpoint, and permission mode.


Codex Result:
```
 Completed Phase 1 from roadmap.md.
  Added the Python project skeleton under cody_banks, including CLI, config, workspace, session, permissions, LLM
  placeholder, tool placeholders, prompt, skills README, pyproject.toml, .gitignore, and data directories.
  Verified:
  python -m cody_banks.cli
  python -m compileall cody_banks
  python -m cody_banks.cli --workspace /tmp
  The first run now prints:
  Cody Banks
  Workspace root: /storage/cody_banks
  Model endpoint: http://localhost:8080/v1
  Permission mode: ask
```


## Phase 2 — Local model connection

Implement a minimal LLM client that talks to an OpenAI-compatible local endpoint.

Configuration should support:

```toml
[model]
base_url = "http://localhost:8080/v1"
api_key = "local"
model = "local-model"
temperature = 0.2
max_tokens = 4096
```

Do not hard-code a specific GGUF. The user can launch llama.cpp separately with whichever model is appropriate.

Useful starting models from the available folder may include:

- `qwen3-coder-30b-a3b-instruct-q4_k_m.gguf` for coding work if it runs well enough.
- `qwen2.5-coder-32b-instruct-q4_k_m.gguf` as another strong coding option.
- `qwen2.5-coder-14b-instruct-q4_k_m.gguf` for faster iteration.
- `nomic-embed-text-v2-moe.Q8_0.gguf` later for embeddings and retrieval.

For phase 2, only chat completion is required. Embeddings can wait.


Codex Result:
```
• Completed Phase 2.
  Implemented a minimal OpenAI-compatible chat completions client in cody_banks/llm.py:21. It posts to {base_url}/
  chat/completions, sends the configured model, temperature, max_tokens, and bearer api_key, then returns
  choices[0].message.content.
  Added a one-shot CLI prompt path in cody_banks/cli.py:27:
  python -m cody_banks.cli --prompt "Say hello in one sentence."
  Updated README.md:7 with the Phase 2 usage and TOML config example.
  Verified with:
  python -m compileall cody_banks
  python -m cody_banks.cli
  Also tested the LLM client against a local mock OpenAI-compatible HTTP server and confirmed the request path, auth
  header, payload, and response parsing.
```


## Phase 3 — The basic agent loop

Build the core loop as plainly as possible.

The loop should:

1. Read user input.
2. Build a message list using `prompts/system.md`, recent conversation history, and a short workspace summary.
3. Ask the model for either a normal answer or a tool request.
4. Validate the requested tool call.
5. Ask for permission when needed.
6. Run the tool.
7. Feed the result back to the model.
8. Continue until the model gives a final answer.

Do not start with a complicated planner. Start with a loop that can see what happened and make the next move.

Use a simple tool-call format at first, even if it is just JSON inside a fenced block:

```json
{
  "tool": "shell",
  "args": {
    "cmd": "ls -la"
  }
}
```

The parser should be forgiving, but the executor should be strict.


Codex Result:
```
Completed Phase 3.
Added a basic interactive agent loop in cody_banks/agent.py that builds messages from the system prompt, recent history, and a workspace summary; asks the model for final text or a fenced JSON tool request; validates tool requests; runs approved tools; feeds tool results back to the model; and stops on a final answer.
Implemented the first strict shell tool executor in cody_banks/tools/shell.py with stdout, stderr, exit code, elapsed time, workspace-root cwd, and timeout capture.
Added a simple Phase 3 permission gate in cody_banks/permissions.py for safe inspection commands, read-only blocking, risky command prompts, and session-level "always" approval.
Updated cody_banks/cli.py so python -m cody_banks.cli starts the interactive loop when --prompt is not provided, while preserving one-shot prompt behavior.
Updated the system prompt and README with the JSON tool-call format.
Verified with:
python -m compileall cody_banks
parser, shell, and loop smoke checks using a fake model client
```

## Phase 4 — Workspace tools

Implement a small, boring tool set first.

Required tools:

- `read_file(path)` — read a file under the workspace root.
- `write_file(path, content)` — create or replace a file, with permission required.
- `edit_file(path, old, new)` — replace exact text, with permission required.
- `list_files(path=".")` — list files under the workspace root.
- `search_text(query, path=".")` — ripgrep-style search.
- `shell(cmd)` — run a shell command from the workspace root.

The shell tool should capture stdout, stderr, exit code, and elapsed time.

Reject paths that escape the workspace root. Reject shell commands that try to silently `cd` somewhere outside the workspace unless the user explicitly approves it.


Codex Result:
```
Completed Phase 4.
Implemented workspace file tools in cody_banks/tools/files.py:
- read_file(path)
- write_file(path, content)
- edit_file(path, old, new)
- list_files(path=".")
All file paths are resolved against the workspace root and rejected if they escape it.

Implemented search_text(query, path=".") in cody_banks/tools/search.py using ripgrep when available with a Python fallback.

Extended the agent dispatcher in cody_banks/agent.py to validate and execute all Phase 4 tools. write_file and edit_file require permission, read-only mode blocks writes, and structured tool results are fed back to the model.

Kept shell(cmd) workspace-root execution with stdout, stderr, exit code, and elapsed time capture. Added detection for shell commands that cd outside the workspace so they require explicit approval.

Updated README.md with the Phase 4 tool list.
Verified with:
python -m compileall cody_banks
workspace tool smoke checks for read/write/edit/list/search/shell/path escape rejection
agent loop smoke checks for permission-gated write_file and tool feedback
```

## Phase 5 — Permission system

Use a clear command risk model.

Default allow without asking:

- `ls`, `pwd`, `cat`, `head`, `tail`, `grep`, `rg`, `find` inside the workspace.
- Reading files inside the workspace.
- Non-mutating inspection commands.

Ask before running:

- Anything that writes files.
- `git add`, `git commit`, `git push`, `git reset`, `git checkout`, `git clean`.
- Package installs.
- Test commands that may take a while.
- Any command containing `sudo`.
- Any command touching paths outside the workspace.

Always block unless manually overridden:

- `rm -rf /`
- destructive commands outside the workspace
- credential exfiltration patterns
- commands that read private keys by default
- fork bombs or obvious resource attacks

Permission modes:

```text
ask       default; ask before risky actions
read-only never mutate anything
auto      allow workspace edits and safe commands, still ask for destructive/system actions
```

The permission prompt should show the exact command or file change and ask for `y`, `n`, or `always for this session`.


Codex Result:
```
Completed Phase 5.
Reworked cody_banks/permissions.py into a clearer risk classifier with:
- safe inspection command allow-list
- prompts for file-mutating commands, git add/commit/push/reset/checkout/clean, package installs, test commands, sudo, unknown commands, and paths outside the workspace
- read-only mode blocking mutations
- auto mode allowing workspace edits and safe commands while still prompting for package installs, sudo, outside-workspace paths, and high-risk git operations
- manual-override-only handling for rm -rf /, destructive commands outside the workspace, private-key reads, credential exfiltration patterns, and fork bombs

Updated cody_banks/agent.py so shell permissions pass workspace context, manual-override blocks require explicit approval, write_file/edit_file prompts show the requested file change, read-only blocks writes, auto mode allows workspace writes, and prompts accept y, n, or always for this session where appropriate.

Updated README.md with permission mode configuration and behavior.
Verified with:
python -m compileall cody_banks
permission classifier checks for safe inspection, sudo, git, package install, tests, read-only, auto, private key reads, destructive outside-workspace commands, and rm -rf /
agent permission mode checks for read-only writes, auto writes, prompted outside-workspace reads, manual override denial, and file-change prompt details
printf '/exit\n' | python -m cody_banks.cli
```

## Phase 6 — Diffs before writes

Before modifying an existing file, show a unified diff.

The agent should not just say what it will change. It should show what will change.

For `write_file`, if the file already exists, show a diff from old content to new content. For `edit_file`, show the exact patch.

After applying a change, log:

- timestamp
- tool name
- path or command
- whether permission was requested
- whether permission was granted
- result summary

## Phase 7 — Sessions and memory

Persist each session locally.

Store:

```text
data/sessions/YYYYMMDD-HHMMSS.jsonl
```

Each line should be one event:

- user message
- assistant message
- tool request
- permission decision
- tool result
- final answer

Add a `/resume` command later, but do not make it part of the first milestone.

Add a lightweight project memory file later, probably:

```text
.cody/memory.md
```

This should contain stable project facts the agent has learned, not a giant transcript.

## Phase 8 — Runtime prompt and skills

Put the main behavior in:

```text
cody_banks/prompts/system.md
```

The system prompt should tell the agent:

- it is operating inside a workspace
- it must prefer small, inspectable changes
- it must ask before risky commands
- it must use tools instead of guessing about files
- it must summarize what changed at the end
- it must not invent command results

Add a skills folder:

```text
cody_banks/skills/
  python.md
  git.md
  react.md
  local_llm.md
```

Skills are plain markdown files that can be loaded into context when relevant. Start with manual loading. Automatic skill retrieval can come later.

A skill should include:

- when to use it
- useful commands
- project conventions
- common traps
- done criteria

## Phase 9 — Git awareness

Add git helpers after the basic loop works.

Useful features:

- Detect whether the workspace is a git repo.
- Show current branch.
- Show dirty files.
- Show diff summary before and after agent work.
- Refuse to overwrite uncommitted user changes without warning.
- Offer commit message suggestions, but do not commit without explicit approval.

End every coding task with a short status:

```text
Changed:
- file A
- file B

Validated:
- command run
- result

Not done:
- anything skipped or uncertain
```

## Phase 10 — Search and retrieval

Add local project indexing once the basic agent is useful.

Start with keyword search using `rg` and file summaries. Do not jump straight to vectors.

Then add embeddings using the available embedding GGUF, likely `nomic-embed-text-v2-moe.Q8_0.gguf`, through a local embedding server.

Index:

- source files
- README files
- markdown docs
- roadmap files
- skill files
- session summaries

Store index data under:

```text
.cody/index/
```

The retrieval rule should be simple: use keyword search first, then vector search when keyword search is not enough.

## Phase 11 — Better editing

Once basic exact replacement works, add patch application.

Possible tools:

- `apply_patch(patch_text)`
- `create_file(path, content)`
- `rename_file(old_path, new_path)`
- `delete_file(path)` with strong permission checks

Keep exact replacement as the default because it is easier to inspect and safer.

## Phase 12 — Tests and validation

The agent should learn to validate changes, but it should not run expensive commands blindly.

Implement conventions:

- Ask before first test run in a session.
- Remember approved test commands for the session.
- Capture output compactly.
- If a command fails, summarize the relevant failure and propose the next fix.

Useful commands to detect:

- `pytest`
- `npm test`
- `npm run build`
- `uv run pytest`
- `python -m pytest`
- `ruff check`
- `mypy`

## Phase 13 — Slash commands

Add a few terminal slash commands:

```text
/help       show commands
/status     show workspace, model, git state, permission mode
/model      show or change model config
/permissions show or change permission mode
/compact    summarize current session into memory
/clear      clear current chat context, keep session log
/exit       quit
```

Do not overbuild the interface. The loop matters more than the shell UI.

## Phase 14 — Optional TUI

Only after the CLI works, consider a richer terminal interface.

Possible additions:

- scrolling transcript
- separate tool output panels
- diff viewer
- permission dialog
- model/status bar

Good libraries to consider later:

- Textual
- Rich
- prompt_toolkit

This is not required for the first useful version.

## Milestone 1 — Minimum viable Cody

Done when Cody can:

- start from a project folder
- talk to a local llama.cpp OpenAI-compatible server
- read files
- search files
- propose edits
- show diffs
- ask before writes and risky shell commands
- apply approved edits
- run approved commands
- summarize what changed
- save a session log

Do not add embeddings, TUI, or complex skills before this works.

## Milestone 2 — Useful local coding agent

Done when Cody can:

- understand project layout
- inspect git state
- make multi-file changes safely
- run tests/builds with permission
- recover from failed commands
- keep compact project memory
- load relevant skills manually
- produce clear final summaries

## Milestone 3 — Cody with RAG and skills

Done when Cody can:

- index project files
- retrieve relevant docs/code chunks
- use local embeddings
- load skills based on task type
- summarize old sessions into project memory
- explain why it chose a tool or file

## Suggested first Codex prompt

Use this prompt from inside the empty `cody_banks` folder:

```text
Create the initial Python project for Cody Banks using the roadmap.md in this folder.

Start with Milestone 1 only. Build a terminal coding agent that runs from the current workspace, talks to an OpenAI-compatible local llama.cpp endpoint, supports read_file, write_file, edit_file, list_files, search_text, and shell tools, and asks permission before risky commands or file writes.

Keep the implementation simple and inspectable. Do not build embeddings, a TUI, or a plugin system yet. Create the project skeleton, config loading, CLI loop, LLM client, workspace safety checks, tool execution, permission prompts, diffs before writes, and JSONL session logging.

After implementation, show me how to run it against a local llama.cpp server and give me one tiny manual test plan.
```

## Design principle

The point is not to make an impressive demo. The point is to make a loop you can understand.

A good first Cody Banks should feel like this:

```text
Think carefully.
Inspect the files.
Ask before touching things.
Change the smallest thing that solves the problem.
Run only the validation that makes sense.
Tell me exactly what happened.
```
