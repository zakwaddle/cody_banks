# Optional TUI Plan

## Decision

Do not build a richer terminal UI yet.

The current CLI loop is the primary interface and should remain the default until the agent behavior is stable. A TUI can be added later without changing the core agent loop if the UI calls the same `Agent` methods and tool APIs.

## Candidate Features

- Scrolling transcript for long conversations.
- Separate panels for tool requests and tool results.
- Diff viewer for proposed file changes.
- Permission dialog for file writes, tests, and risky shell commands.
- Status bar showing workspace, model, git branch, dirty state, and permission mode.

## Candidate Libraries

- Textual for a full terminal application.
- Rich for lightweight panels, syntax highlighting, and diffs.
- prompt_toolkit for improved input editing, history, and completions.

## Integration Notes

- Keep the existing CLI as the stable fallback.
- Do not duplicate agent logic in the TUI.
- Route all model turns through `Agent.run_turn`.
- Route permissions through the existing permission methods.
- Keep session logging, tool logging, and git awareness shared with the CLI.

## Done Criteria Before Building

- CLI slash commands are stable.
- Tool output formatting is compact and predictable.
- Diff and permission prompts are reliable.
- Tests/build validation flow is stable.
- There is a clear user need for persistent panes or richer navigation.
