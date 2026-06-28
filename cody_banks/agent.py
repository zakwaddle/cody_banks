"""Basic agent loop for Cody Banks."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Callable

from cody_banks.config import Config
from cody_banks.llm import LLMClient, LLMError, Message
from cody_banks.permissions import evaluate_shell_command
from cody_banks.tools.files import (
    ToolError,
    edit_file,
    list_files,
    read_file,
    resolve_workspace_path,
    write_file,
)
from cody_banks.tools.search import search_text
from cody_banks.tools.shell import ShellResult, cd_target_outside_workspace, run_shell


@dataclass(frozen=True, slots=True)
class ToolRequest:
    tool: str
    args: dict[str, object]


@dataclass(slots=True)
class Agent:
    workspace_root: Path
    config: Config
    client: LLMClient
    input_func: Callable[[str], str] = input
    output_func: Callable[[str], None] = print
    history: list[Message] = field(default_factory=list)
    always_allowed_shell_commands: set[str] = field(default_factory=set)
    always_allowed_file_actions: set[str] = field(default_factory=set)
    max_tool_turns: int = 8

    def run_chat(self) -> None:
        """Run an interactive terminal chat loop."""
        self.output_func("")
        self.output_func("Enter a message. Use Ctrl-D or /exit to quit.")
        while True:
            try:
                user_text = self.input_func("> ")
            except EOFError:
                self.output_func("")
                return

            if user_text.strip() in {"/exit", "/quit"}:
                return
            if not user_text.strip():
                continue

            try:
                answer = self.run_turn(user_text)
            except LLMError as exc:
                self.output_func(f"Model error: {exc}")
                continue

            self.output_func("")
            self.output_func(answer)

    def run_turn(self, user_text: str) -> str:
        """Run one user turn until the model returns a final answer."""
        self.history.append({"role": "user", "content": user_text})
        working_messages = self._build_messages()

        for _ in range(self.max_tool_turns):
            assistant_text = self.client.chat_completion(working_messages)
            tool_request = parse_tool_request(assistant_text)

            if tool_request is None:
                self.history.append({"role": "assistant", "content": assistant_text})
                return assistant_text

            working_messages.append({"role": "assistant", "content": assistant_text})
            tool_result = self._run_tool_request(tool_request)
            working_messages.append(
                {
                    "role": "user",
                    "content": format_tool_result_for_model(tool_request, tool_result),
                }
            )

        final_text = "Stopped because the model requested too many consecutive tool calls."
        self.history.append({"role": "assistant", "content": final_text})
        return final_text

    def _build_messages(self) -> list[Message]:
        return [
            {"role": "system", "content": self._system_message()},
            *self.history[-12:],
        ]

    def _system_message(self) -> str:
        prompt_path = Path(__file__).parent / "prompts" / "system.md"
        base_prompt = prompt_path.read_text(encoding="utf-8")
        return "\n\n".join(
            [
                base_prompt,
                "Workspace summary:\n" + summarize_workspace(self.workspace_root),
                TOOL_INSTRUCTIONS,
            ]
        )

    def _run_tool_request(self, request: ToolRequest) -> ShellResult | dict[str, object] | str:
        validation_error = validate_tool_request(request)
        if validation_error is not None:
            return f"Tool request rejected: {validation_error}"

        try:
            if request.tool == "read_file":
                path = _required_string(request, "path")
                return read_file(path, self.workspace_root)

            if request.tool == "write_file":
                path = _required_string(request, "path")
                content = _required_string(request, "content")
                action_key = f"write_file:{path}"
                details = f"write_file {path}\ncontent:\n{content}"
                if not self._confirm_file_write(action_key, "write_file", path, details):
                    return "Tool request denied by user."
                return write_file(path, content, self.workspace_root)

            if request.tool == "edit_file":
                path = _required_string(request, "path")
                old = _required_string(request, "old")
                new = _required_string(request, "new")
                action_key = f"edit_file:{path}"
                details = f"edit_file {path}\nold:\n{old}\nnew:\n{new}"
                if not self._confirm_file_write(action_key, "edit_file", path, details):
                    return "Tool request denied by user."
                return edit_file(path, old, new, self.workspace_root)

            if request.tool == "list_files":
                path = _optional_string(request, "path", ".")
                return list_files(path, self.workspace_root)

            if request.tool == "search_text":
                query = _required_string(request, "query")
                path = _optional_string(request, "path", ".")
                return search_text(query, path, self.workspace_root)

            if request.tool == "shell":
                cmd = _required_string(request, "cmd")
                decision = evaluate_shell_command(cmd, self.config.permissions.mode, self.workspace_root)
                escaped_cd_target = cd_target_outside_workspace(cmd, self.workspace_root)
                if escaped_cd_target is not None:
                    decision.requires_prompt = True
                    decision.reason = f"command changes directory outside the workspace: {escaped_cd_target}"
                if cmd in self.always_allowed_shell_commands:
                    decision.requires_prompt = False

                if decision.blocked:
                    if not decision.manual_override_allowed:
                        return f"Tool request blocked: {decision.reason}"
                    if not self._ask_permission(
                        title="Manual override required for blocked shell command:",
                        details=cmd,
                        reason=decision.reason,
                        always_callback=lambda: None,
                        allow_always=False,
                    ):
                        return "Tool request denied by user."
                    decision.requires_prompt = False

                if decision.requires_prompt and not self._ask_permission(
                    title="Permission required for shell command:",
                    details=cmd,
                    reason=decision.reason,
                    always_callback=lambda: self.always_allowed_shell_commands.add(cmd),
                ):
                    return "Tool request denied by user."

                return run_shell(cmd, self.workspace_root)
        except ToolError as exc:
            return f"Tool request failed: {exc}"

        return f"Tool request rejected: unknown tool {request.tool!r}"

    def _confirm_file_write(self, action_key: str, tool_name: str, path: str, details: str) -> bool:
        if self.config.permissions.mode == "read-only":
            raise ToolError("permission mode is read-only")
        if self.config.permissions.mode == "auto":
            resolve_workspace_path(self.workspace_root, path)
            return True
        if action_key in self.always_allowed_file_actions:
            return True

        resolved = resolve_workspace_path(self.workspace_root, path)
        resolved_details = details.replace(path, str(resolved.relative_to(self.workspace_root)), 1)
        return self._ask_permission(
            title=f"Permission required for {tool_name}:",
            details=resolved_details,
            reason="file write tools modify workspace files",
            always_callback=lambda: self.always_allowed_file_actions.add(action_key),
        )

    def _ask_permission(
        self,
        title: str,
        details: str,
        reason: str,
        always_callback: Callable[[], None],
        allow_always: bool = True,
    ) -> bool:
        self.output_func("")
        self.output_func(title)
        self.output_func(details)
        self.output_func(f"Reason: {reason}")

        while True:
            prompt = "Run it? [y/n/always for this session] " if allow_always else "Run it? [y/n] "
            answer = self.input_func(prompt).strip().lower()
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False
            if allow_always and answer in {"a", "always", "always for this session"}:
                always_callback()
                return True


TOOL_INSTRUCTIONS = """Tool use:
- Reply normally when you can answer without tools.
- To request a tool, reply with only a fenced JSON object in this format:

```json
{
  "tool": "read_file",
  "args": {
    "path": "README.md"
  }
}
```

Available tools in this phase:
- read_file: read a UTF-8 file under the workspace root. Required args: path string.
- write_file: create or replace a UTF-8 file under the workspace root. Required args: path string, content string. Requires permission.
- edit_file: replace exact text in a UTF-8 file under the workspace root. Required args: path string, old string, new string. Requires permission.
- list_files: list files under a workspace directory. Optional args: path string, defaults to ".".
- search_text: search text under the workspace root. Required args: query string. Optional args: path string, defaults to ".".
- shell: run a shell command from the workspace root. Required args: cmd string.

After a tool result is provided, continue reasoning and either request another tool or give the final answer."""


def parse_tool_request(text: str) -> ToolRequest | None:
    """Extract a tool request from assistant text, accepting fenced or raw JSON."""
    candidates = _json_candidates(text)
    for candidate in candidates:
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(decoded, dict):
            continue
        tool = decoded.get("tool")
        args = decoded.get("args", {})
        if isinstance(tool, str) and isinstance(args, dict):
            return ToolRequest(tool=tool, args=args)
    return None


def validate_tool_request(request: ToolRequest) -> str | None:
    """Validate tool shape strictly before execution."""
    tool_specs = {
        "read_file": {"required": {"path"}, "optional": set()},
        "write_file": {"required": {"path", "content"}, "optional": set()},
        "edit_file": {"required": {"path", "old", "new"}, "optional": set()},
        "list_files": {"required": set(), "optional": {"path"}},
        "search_text": {"required": {"query"}, "optional": {"path"}},
        "shell": {"required": {"cmd"}, "optional": set()},
    }
    spec = tool_specs.get(request.tool)
    if spec is None:
        return f"unknown tool {request.tool!r}"

    allowed = spec["required"] | spec["optional"]
    unexpected = set(request.args) - allowed
    if unexpected:
        return f"unexpected {request.tool} args: {', '.join(sorted(unexpected))}"

    missing = spec["required"] - set(request.args)
    if missing:
        return f"missing {request.tool} args: {', '.join(sorted(missing))}"

    for key, value in request.args.items():
        if not isinstance(value, str):
            return f"{request.tool} arg {key!r} must be a string"
        if key != "content" and not value.strip():
            return f"{request.tool} arg {key!r} must not be empty"

    return None


def format_tool_result_for_model(request: ToolRequest, result: ShellResult | dict[str, object] | str) -> str:
    if isinstance(result, str):
        body = result
    elif isinstance(result, dict):
        body = json.dumps(result, indent=2)
    else:
        body = (
            f"exit_code: {result.exit_code}\n"
            f"elapsed_seconds: {result.elapsed_seconds:.3f}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return (
        "Tool result for request:\n"
        f"{json.dumps({'tool': request.tool, 'args': request.args}, indent=2)}\n\n"
        f"{body}"
    )


def summarize_workspace(root: Path, limit: int = 40) -> str:
    files: list[str] = []
    ignored_dirs = {".git", ".idea", "__pycache__", ".pytest_cache", ".mypy_cache"}
    for path in sorted(root.rglob("*")):
        if any(part in ignored_dirs for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            files.append(str(path.relative_to(root)))
        if len(files) >= limit:
            break

    listed = "\n".join(f"- {file_path}" for file_path in files) or "- no files found"
    extra = "\n- ..." if len(files) >= limit else ""
    return f"root: {root}\nfiles:\n{listed}{extra}"


def _json_candidates(text: str) -> list[str]:
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced

    stripped = text.strip()
    candidates = [stripped]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(stripped[start : end + 1])
    return candidates


def _required_string(request: ToolRequest, key: str) -> str:
    value = request.args[key]
    assert isinstance(value, str)
    return value


def _optional_string(request: ToolRequest, key: str, default: str) -> str:
    value = request.args.get(key, default)
    assert isinstance(value, str)
    return value
