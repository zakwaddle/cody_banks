"""Basic agent loop for Cody Banks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
import re
from typing import Callable

from cody_banks.config import Config, ModelConfig, PermissionsConfig
from cody_banks.llm import LLMClient, LLMError, Message
from cody_banks.permissions import evaluate_shell_command
from cody_banks.session import SessionRecorder
from cody_banks.tools.files import (
    ToolError,
    apply_patch_text,
    create_file,
    delete_file,
    display_path,
    edit_file,
    list_files,
    read_file,
    rename_file,
    resolve_workspace_path,
    touched_paths_from_patch,
    write_file,
)
from cody_banks.tools.git import GitState, format_git_state, inspect_git_state, suggest_commit_message
from cody_banks.tools.index import build_project_index, retrieve_context
from cody_banks.tools.search import search_text
from cody_banks.tools.shell import ShellResult, cd_target_outside_workspace, run_shell


@dataclass(frozen=True, slots=True)
class ToolRequest:
    tool: str
    args: dict[str, object]


@dataclass(frozen=True, slots=True)
class PermissionResult:
    requested: bool
    granted: bool


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
    approved_test_commands: set[str] = field(default_factory=set)
    max_tool_turns: int = 8
    session: SessionRecorder | None = None
    turn_start_git_state: GitState | None = None
    changed_files: set[str] = field(default_factory=set)
    validations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = SessionRecorder.create(self.workspace_root)

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

            if user_text.strip().startswith("/"):
                if self._handle_slash_command(user_text.strip()):
                    return
                continue
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

    def _handle_slash_command(self, command: str) -> bool:
        name, _, rest = command.partition(" ")
        args = rest.strip()
        self._record_session_event("slash_command", {"command": command})

        if name in {"/exit", "/quit"}:
            return True
        if name == "/help":
            self._show_help()
            return False
        if name == "/status":
            self._show_status()
            return False
        if name == "/model":
            self._handle_model_command(args)
            return False
        if name == "/permissions":
            self._handle_permissions_command(args)
            return False
        if name == "/compact":
            self._compact_session_to_memory()
            return False
        if name == "/clear":
            self.history.clear()
            self.output_func("Cleared chat context. Session log kept.")
            return False

        self.output_func(f"Unknown command: {name}")
        self.output_func("Run /help to see available commands.")
        return False

    def _show_help(self) -> None:
        self.output_func(
            "\n".join(
                [
                    "Commands:",
                    "/help          show commands",
                    "/status        show workspace, model, git state, permission mode",
                    "/model         show model config",
                    "/model key value  change model config for this session",
                    "/permissions   show permission mode",
                    "/permissions ask|read-only|auto  change permission mode for this session",
                    "/compact       summarize current session into .cody/memory.md",
                    "/clear         clear current chat context, keep session log",
                    "/exit          quit",
                ]
            )
        )

    def _show_status(self) -> None:
        self.output_func("Workspace:")
        self.output_func(str(self.workspace_root))
        self.output_func("")
        self.output_func("Model:")
        self.output_func(format_model_config(self.config.model))
        self.output_func("")
        self.output_func(f"Permission mode: {self.config.permissions.mode}")
        self.output_func("")
        self.output_func(format_git_state(inspect_git_state(self.workspace_root)))

    def _handle_model_command(self, args: str) -> None:
        if not args:
            self.output_func(format_model_config(self.config.model))
            return

        key, _, value = args.partition(" ")
        key = key.strip()
        value = value.strip()
        if key not in {"base_url", "api_key", "model", "temperature", "max_tokens"} or not value:
            self.output_func("Usage: /model [base_url|api_key|model|temperature|max_tokens] VALUE")
            return

        current = self.config.model
        try:
            if key == "temperature":
                parsed_value: str | float | int = float(value)
            elif key == "max_tokens":
                parsed_value = int(value)
            else:
                parsed_value = value
        except ValueError:
            self.output_func(f"Invalid value for {key}: {value}")
            return

        model_config = ModelConfig(
            base_url=parsed_value if key == "base_url" else current.base_url,
            api_key=parsed_value if key == "api_key" else current.api_key,
            model=parsed_value if key == "model" else current.model,
            temperature=parsed_value if key == "temperature" else current.temperature,
            max_tokens=parsed_value if key == "max_tokens" else current.max_tokens,
        )
        self.config = Config(model=model_config, permissions=self.config.permissions)
        self.client = LLMClient(model_config)
        self.output_func("Updated model config for this session.")
        self.output_func(format_model_config(self.config.model))

    def _handle_permissions_command(self, args: str) -> None:
        if not args:
            self.output_func(f"Permission mode: {self.config.permissions.mode}")
            return
        if args not in {"ask", "read-only", "auto"}:
            self.output_func("Usage: /permissions ask|read-only|auto")
            return
        self.config = Config(
            model=self.config.model,
            permissions=PermissionsConfig(mode=args),
        )
        self.output_func(f"Permission mode: {self.config.permissions.mode}")

    def _compact_session_to_memory(self) -> None:
        memory_dir = self.workspace_root / ".cody"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_path = memory_dir / "memory.md"
        summary = summarize_history_for_memory(self.history)
        timestamp = datetime.now(timezone.utc).isoformat()
        with memory_path.open("a", encoding="utf-8") as memory_file:
            memory_file.write(f"\n## Session compact {timestamp}\n\n{summary}\n")
        self.output_func(f"Wrote session summary to {memory_path.relative_to(self.workspace_root)}")

    def run_turn(self, user_text: str) -> str:
        """Run one user turn until the model returns a final answer."""
        self.changed_files.clear()
        self.validations.clear()
        self.turn_start_git_state = inspect_git_state(self.workspace_root)
        self._show_git_snapshot("Git before work", self.turn_start_git_state)
        self._record_session_event("user_message", {"content": user_text})
        self.history.append({"role": "user", "content": user_text})
        working_messages = self._build_messages()

        for _ in range(self.max_tool_turns):
            assistant_text = self.client.chat_completion(working_messages)
            self._record_session_event("assistant_message", {"content": assistant_text})
            tool_request = parse_tool_request(assistant_text)

            if tool_request is None:
                self.history.append({"role": "assistant", "content": assistant_text})
                self._record_session_event("final_answer", {"content": assistant_text})
                self._show_final_status()
                return assistant_text

            working_messages.append({"role": "assistant", "content": assistant_text})
            self._record_session_event(
                "tool_request",
                {"tool": tool_request.tool, "args": tool_request.args},
            )
            tool_result = self._run_tool_request(tool_request)
            working_messages.append(
                {
                    "role": "user",
                    "content": format_tool_result_for_model(tool_request, tool_result),
                }
            )

        final_text = "Stopped because the model requested too many consecutive tool calls."
        self.history.append({"role": "assistant", "content": final_text})
        self._record_session_event("final_answer", {"content": final_text})
        self._show_final_status()
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
                "Git summary:\n" + format_git_state(inspect_git_state(self.workspace_root)),
                TOOL_INSTRUCTIONS,
            ]
        )

    def _run_tool_request(self, request: ToolRequest) -> ShellResult | dict[str, object] | str:
        validation_error = validate_tool_request(request)
        if validation_error is not None:
            result = f"Tool request rejected: {validation_error}"
            self._log_tool_result(request.tool, request.args, False, False, result)
            return result

        try:
            if request.tool == "read_file":
                path = _required_string(request, "path")
                result = read_file(path, self.workspace_root)
                self._log_tool_result(request.tool, request.args, False, True, result)
                return result

            if request.tool == "write_file":
                path = _required_string(request, "path")
                content = _required_string(request, "content")
                action_key = f"write_file:{path}"
                self._show_write_file_diff(path, content)
                self._warn_if_user_dirty_file(path)
                details = f"write_file {path}\ncontent:\n{content}"
                permission = self._confirm_file_write(action_key, "write_file", path, details)
                if not permission.granted:
                    result = "Tool request denied by user."
                    self._log_tool_result(request.tool, request.args, permission.requested, False, result)
                    return "Tool request denied by user."
                result = write_file(path, content, self.workspace_root)
                self.changed_files.add(str(resolve_workspace_path(self.workspace_root, path).relative_to(self.workspace_root)))
                self._log_tool_result(request.tool, request.args, permission.requested, True, result)
                return result

            if request.tool == "create_file":
                path = _required_string(request, "path")
                content = _required_string(request, "content")
                action_key = f"create_file:{path}"
                self._show_create_file_diff(path, content)
                details = f"create_file {path}\ncontent:\n{content}"
                permission = self._confirm_file_write(action_key, "create_file", path, details)
                if not permission.granted:
                    result = "Tool request denied by user."
                    self._log_tool_result(request.tool, request.args, permission.requested, False, result)
                    return result
                result = create_file(path, content, self.workspace_root)
                self.changed_files.add(str(resolve_workspace_path(self.workspace_root, path).relative_to(self.workspace_root)))
                self._log_tool_result(request.tool, request.args, permission.requested, True, result)
                return result

            if request.tool == "edit_file":
                path = _required_string(request, "path")
                old = _required_string(request, "old")
                new = _required_string(request, "new")
                action_key = f"edit_file:{path}"
                self._show_edit_file_diff(path, old, new)
                self._warn_if_user_dirty_file(path)
                details = f"edit_file {path}\nold:\n{old}\nnew:\n{new}"
                permission = self._confirm_file_write(action_key, "edit_file", path, details)
                if not permission.granted:
                    result = "Tool request denied by user."
                    self._log_tool_result(request.tool, request.args, permission.requested, False, result)
                    return result
                result = edit_file(path, old, new, self.workspace_root)
                self.changed_files.add(str(resolve_workspace_path(self.workspace_root, path).relative_to(self.workspace_root)))
                self._log_tool_result(request.tool, request.args, permission.requested, True, result)
                return result

            if request.tool == "apply_patch":
                patch_text = _required_string(request, "patch_text")
                touched_paths = touched_paths_from_patch(patch_text, self.workspace_root)
                if not touched_paths:
                    raise ToolError("patch did not contain any workspace file paths")
                for path in touched_paths:
                    self._warn_if_user_dirty_file(display_path(self.workspace_root, path))
                self._show_diff(patch_text)
                details = "apply_patch\n" + patch_text
                permission = self._confirm_file_write(
                    "apply_patch",
                    "apply_patch",
                    display_path(self.workspace_root, touched_paths[0]) if touched_paths else ".",
                    details,
                    force_prompt=True,
                )
                if not permission.granted:
                    result = "Tool request denied by user."
                    self._log_tool_result(request.tool, request.args, permission.requested, False, result)
                    return result
                result = apply_patch_text(patch_text, self.workspace_root)
                for path in touched_paths:
                    self.changed_files.add(display_path(self.workspace_root, path))
                self._log_tool_result(request.tool, request.args, permission.requested, True, result)
                return result

            if request.tool == "rename_file":
                old_path = _required_string(request, "old_path")
                new_path = _required_string(request, "new_path")
                self._warn_if_user_dirty_file(old_path)
                details = f"rename_file {old_path} -> {new_path}"
                permission = self._confirm_file_write(
                    f"rename_file:{old_path}:{new_path}",
                    "rename_file",
                    old_path,
                    details,
                    force_prompt=True,
                )
                if not permission.granted:
                    result = "Tool request denied by user."
                    self._log_tool_result(request.tool, request.args, permission.requested, False, result)
                    return result
                result = rename_file(old_path, new_path, self.workspace_root)
                self.changed_files.add(old_path)
                self.changed_files.add(new_path)
                self._log_tool_result(request.tool, request.args, permission.requested, True, result)
                return result

            if request.tool == "delete_file":
                path = _required_string(request, "path")
                self._show_delete_file_diff(path)
                self._warn_if_user_dirty_file(path)
                details = f"delete_file {path}"
                permission = self._confirm_file_write(
                    f"delete_file:{path}",
                    "delete_file",
                    path,
                    details,
                    force_prompt=True,
                    allow_always=False,
                    reason_override="delete_file removes a workspace file",
                )
                if not permission.granted:
                    result = "Tool request denied by user."
                    self._log_tool_result(request.tool, request.args, permission.requested, False, result)
                    return result
                result = delete_file(path, self.workspace_root)
                self.changed_files.add(path)
                self._log_tool_result(request.tool, request.args, permission.requested, True, result)
                return result

            if request.tool == "list_files":
                path = _optional_string(request, "path", ".")
                result = list_files(path, self.workspace_root)
                self._log_tool_result(request.tool, request.args, False, True, result)
                return result

            if request.tool == "search_text":
                query = _required_string(request, "query")
                path = _optional_string(request, "path", ".")
                result = search_text(query, path, self.workspace_root)
                self._log_tool_result(request.tool, request.args, False, True, result)
                return result

            if request.tool == "index_project":
                permission = self._confirm_file_write(
                    "index_project:.cody/index/project_index.json",
                    "index_project",
                    ".cody/index/project_index.json",
                    "index_project .cody/index/project_index.json",
                )
                if not permission.granted:
                    result = "Tool request denied by user."
                    self._log_tool_result(request.tool, request.args, permission.requested, False, result)
                    return result
                result = build_project_index(self.workspace_root)
                self.changed_files.add(".cody/index/project_index.json")
                self._log_tool_result(request.tool, request.args, permission.requested, True, result)
                return result

            if request.tool == "retrieve_context":
                query = _required_string(request, "query")
                limit = _optional_int(request, "limit", 8)
                result = retrieve_context(query, self.workspace_root, limit=limit)
                self._log_tool_result(request.tool, request.args, False, True, result)
                return result

            if request.tool == "shell":
                cmd = _required_string(request, "cmd")
                decision = evaluate_shell_command(cmd, self.config.permissions.mode, self.workspace_root)
                escaped_cd_target = cd_target_outside_workspace(cmd, self.workspace_root)
                if escaped_cd_target is not None:
                    decision.requires_prompt = True
                    decision.reason = f"command changes directory outside the workspace: {escaped_cd_target}"
                if cmd in self.always_allowed_shell_commands:
                    decision.requires_prompt = False

                permission_requested = False
                if decision.blocked:
                    if not decision.manual_override_allowed:
                        result = f"Tool request blocked: {decision.reason}"
                        self._log_tool_result(request.tool, request.args, False, False, result)
                        return result
                    permission_requested = True
                    if not self._ask_permission(
                        title="Manual override required for blocked shell command:",
                        details=cmd,
                        reason=decision.reason,
                        tool_name=request.tool,
                        target=cmd,
                        always_callback=lambda: None,
                        allow_always=False,
                    ):
                        result = "Tool request denied by user."
                        self._log_tool_result(request.tool, request.args, True, False, result)
                        return result
                    decision.requires_prompt = False

                if decision.requires_prompt and not is_test_command(cmd):
                    permission_requested = True
                    if not self._ask_permission(
                        title="Permission required for shell command:",
                        details=cmd,
                        reason=decision.reason,
                        tool_name=request.tool,
                        target=cmd,
                        always_callback=lambda: self.always_allowed_shell_commands.add(cmd),
                    ):
                        result = "Tool request denied by user."
                        self._log_tool_result(request.tool, request.args, True, False, result)
                        return result

                test_permission = self._confirm_test_command(cmd)
                if not test_permission.granted:
                    result = "Tool request denied by user."
                    self._log_tool_result(request.tool, request.args, test_permission.requested, False, result)
                    return result
                if test_permission.requested:
                    permission_requested = True

                result = run_shell(cmd, self.workspace_root)
                self._track_shell_validation(cmd, result)
                self._log_tool_result(request.tool, request.args, permission_requested, True, result)
                return result
        except ToolError as exc:
            result = f"Tool request failed: {exc}"
            self._log_tool_result(request.tool, request.args, False, False, result)
            return result

        result = f"Tool request rejected: unknown tool {request.tool!r}"
        self._log_tool_result(request.tool, request.args, False, False, result)
        return result

    def _confirm_file_write(
        self,
        action_key: str,
        tool_name: str,
        path: str,
        details: str,
        force_prompt: bool = False,
        allow_always: bool = True,
        reason_override: str | None = None,
    ) -> PermissionResult:
        if self.config.permissions.mode == "read-only":
            raise ToolError("permission mode is read-only")
        dirty_at_turn_start = self._file_dirty_at_turn_start(path)
        if self.config.permissions.mode == "auto" and not dirty_at_turn_start and not force_prompt:
            resolve_workspace_path(self.workspace_root, path)
            return PermissionResult(requested=False, granted=True)
        if action_key in self.always_allowed_file_actions and not dirty_at_turn_start and not force_prompt:
            return PermissionResult(requested=False, granted=True)

        resolved = resolve_workspace_path(self.workspace_root, path)
        resolved_details = details.replace(path, str(resolved.relative_to(self.workspace_root)), 1)
        reason = reason_override or "file write tools modify workspace files"
        if dirty_at_turn_start:
            reason = "file had uncommitted changes before this turn"
        granted = self._ask_permission(
            title=f"Permission required for {tool_name}:",
            details=resolved_details,
            reason=reason,
            tool_name=tool_name,
            target=str(resolved.relative_to(self.workspace_root)),
            always_callback=lambda: self.always_allowed_file_actions.add(action_key),
            allow_always=allow_always,
        )
        return PermissionResult(requested=True, granted=granted)

    def _ask_permission(
        self,
        title: str,
        details: str,
        reason: str,
        tool_name: str,
        target: str,
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
                self._record_permission_decision(tool_name, target, reason, granted=True, always=False)
                return True
            if answer in {"n", "no"}:
                self._record_permission_decision(tool_name, target, reason, granted=False, always=False)
                return False
            if allow_always and answer in {"a", "always", "always for this session"}:
                always_callback()
                self._record_permission_decision(tool_name, target, reason, granted=True, always=True)
                return True

    def _confirm_test_command(self, cmd: str) -> PermissionResult:
        if not is_test_command(cmd):
            return PermissionResult(requested=False, granted=True)
        if cmd in self.approved_test_commands:
            return PermissionResult(requested=False, granted=True)

        granted = self._ask_permission(
            title="Permission required for validation command:",
            details=cmd,
            reason="test/build/lint commands may take a while",
            tool_name="shell",
            target=cmd,
            always_callback=lambda: self.approved_test_commands.add(cmd),
        )
        if granted:
            self.approved_test_commands.add(cmd)
        return PermissionResult(requested=True, granted=granted)

    def _show_write_file_diff(self, path: str, content: str) -> None:
        resolved = resolve_workspace_path(self.workspace_root, path)
        if resolved.exists() and not resolved.is_file():
            raise ToolError(f"not a file: {path}")
        if not resolved.exists():
            return

        old_content = resolved.read_text(encoding="utf-8")
        diff = make_unified_diff(
            old_content,
            content,
            fromfile=f"a/{resolved.relative_to(self.workspace_root)}",
            tofile=f"b/{resolved.relative_to(self.workspace_root)}",
        )
        self._show_diff(diff)

    def _show_create_file_diff(self, path: str, content: str) -> None:
        resolved = resolve_workspace_path(self.workspace_root, path)
        if resolved.exists():
            raise ToolError(f"file already exists: {path}")
        diff = make_unified_diff(
            "",
            content,
            fromfile="/dev/null",
            tofile=f"b/{resolved.relative_to(self.workspace_root)}",
        )
        self._show_diff(diff)

    def _show_edit_file_diff(self, path: str, old: str, new: str) -> None:
        resolved = resolve_workspace_path(self.workspace_root, path)
        if not resolved.is_file():
            raise ToolError(f"not a file: {path}")

        content = resolved.read_text(encoding="utf-8")
        count = content.count(old)
        if count == 0:
            raise ToolError("old text was not found")
        if count > 1:
            raise ToolError(f"old text matched {count} times; provide a more specific old value")

        updated = content.replace(old, new, 1)
        diff = make_unified_diff(
            content,
            updated,
            fromfile=f"a/{resolved.relative_to(self.workspace_root)}",
            tofile=f"b/{resolved.relative_to(self.workspace_root)}",
        )
        self._show_diff(diff)

    def _show_delete_file_diff(self, path: str) -> None:
        resolved = resolve_workspace_path(self.workspace_root, path)
        if not resolved.is_file():
            raise ToolError(f"not a file: {path}")
        old_content = resolved.read_text(encoding="utf-8")
        diff = make_unified_diff(
            old_content,
            "",
            fromfile=f"a/{resolved.relative_to(self.workspace_root)}",
            tofile="/dev/null",
        )
        self._show_diff(diff)

    def _show_diff(self, diff: str) -> None:
        self.output_func("")
        self.output_func("Proposed diff:")
        self.output_func(diff if diff else "(no changes)")

    def _warn_if_user_dirty_file(self, path: str) -> None:
        if not self._file_dirty_at_turn_start(path):
            return

        resolved = resolve_workspace_path(self.workspace_root, path)
        relative_path = str(resolved.relative_to(self.workspace_root))
        self.output_func("")
        self.output_func("Warning: this file had uncommitted changes before this turn:")
        self.output_func(relative_path)
        self.output_func("Review the diff carefully before approving the write.")

    def _file_dirty_at_turn_start(self, path: str) -> bool:
        start_state = self.turn_start_git_state
        if start_state is None or not start_state.is_repo:
            return False

        resolved = resolve_workspace_path(self.workspace_root, path)
        relative_path = str(resolved.relative_to(self.workspace_root))
        return relative_path in start_state.dirty_files

    def _show_git_snapshot(self, title: str, state: GitState) -> None:
        if not state.is_repo:
            return
        self.output_func("")
        self.output_func(f"{title}:")
        self.output_func(format_git_state(state))

    def _show_final_status(self) -> None:
        after_state = inspect_git_state(self.workspace_root)
        self._show_git_snapshot("Git after work", after_state)

        self.output_func("")
        self.output_func("Changed:")
        if self.changed_files:
            for path in sorted(self.changed_files):
                self.output_func(f"- {path}")
        else:
            self.output_func("- none")

        self.output_func("")
        self.output_func("Validated:")
        if self.validations:
            for validation in self.validations:
                self.output_func(f"- {validation}")
        else:
            self.output_func("- none")

        self.output_func("")
        self.output_func("Not done:")
        self.output_func("- none")

        suggestion = suggest_commit_message(after_state)
        if suggestion is not None:
            self.output_func("")
            self.output_func(f"Suggested commit message: {suggestion}")

    def _log_tool_result(
        self,
        tool_name: str,
        args: dict[str, object],
        permission_requested: bool,
        permission_granted: bool,
        result: ShellResult | dict[str, object] | str,
    ) -> None:
        log_dir = self.workspace_root / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "target": _tool_target(tool_name, args),
            "permission_requested": permission_requested,
            "permission_granted": permission_granted,
            "result_summary": summarize_tool_result(result),
        }
        with (log_dir / "tools.jsonl").open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, sort_keys=True) + "\n")
        self._record_session_event(
            "tool_result",
            {
                "tool": tool_name,
                "target": record["target"],
                "permission_requested": permission_requested,
                "permission_granted": permission_granted,
                "result_summary": record["result_summary"],
                "result": serialize_tool_result(result),
            },
        )

    def _record_permission_decision(
        self,
        tool_name: str,
        target: str,
        reason: str,
        granted: bool,
        always: bool,
    ) -> None:
        self._record_session_event(
            "permission_decision",
            {
                "tool": tool_name,
                "target": target,
                "reason": reason,
                "granted": granted,
                "always_for_session": always,
            },
        )

    def _record_session_event(self, event_type: str, payload: dict[str, object]) -> None:
        assert self.session is not None
        self.session.append(event_type, payload)

    def _track_shell_validation(self, cmd: str, result: ShellResult) -> None:
        if is_test_command(cmd):
            summary = f"{cmd} -> exit {result.exit_code}"
            if result.exit_code != 0:
                summary += f"; {summarize_failure(result)}"
            self.validations.append(summary)


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
- create_file: create a new UTF-8 file under the workspace root and fail if it exists. Required args: path string, content string. Requires permission.
- edit_file: replace exact text in a UTF-8 file under the workspace root. Required args: path string, old string, new string. Requires permission.
- apply_patch: apply a unified diff patch under the workspace root. Required args: patch_text string. Requires permission. Prefer edit_file for simple exact replacements.
- rename_file: rename a file under the workspace root. Required args: old_path string, new_path string. Requires permission.
- delete_file: delete a file under the workspace root. Required args: path string. Requires strong permission.
- list_files: list files under a workspace directory. Optional args: path string, defaults to ".".
- search_text: search text under the workspace root. Required args: query string. Optional args: path string, defaults to ".".
- index_project: build a local keyword index under .cody/index/. Requires permission.
- retrieve_context: retrieve relevant context. Required args: query string. Optional args: limit integer, defaults to 8. Uses keyword search first, then indexed file summaries. Vector search is not implemented yet.
- shell: run a shell command from the workspace root. Required args: cmd string.

After a tool result is provided, continue reasoning and either request another tool or give the final answer.

For coding tasks, end with:
Changed:
- file A

Validated:
- command run -> observed result

Not done:
- anything skipped or uncertain"""


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
        "create_file": {"required": {"path", "content"}, "optional": set()},
        "edit_file": {"required": {"path", "old", "new"}, "optional": set()},
        "apply_patch": {"required": {"patch_text"}, "optional": set()},
        "rename_file": {"required": {"old_path", "new_path"}, "optional": set()},
        "delete_file": {"required": {"path"}, "optional": set()},
        "list_files": {"required": set(), "optional": {"path"}},
        "search_text": {"required": {"query"}, "optional": {"path"}},
        "index_project": {"required": set(), "optional": set()},
        "retrieve_context": {"required": {"query"}, "optional": {"limit"}},
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
        if request.tool == "retrieve_context" and key == "limit":
            if isinstance(value, int):
                if value <= 0:
                    return "retrieve_context arg 'limit' must be positive"
                continue
            if isinstance(value, str) and value.isdigit() and int(value) > 0:
                continue
            return "retrieve_context arg 'limit' must be a positive integer"
        if not isinstance(value, str):
            return f"{request.tool} arg {key!r} must be a string"
        if key not in {"content", "patch_text"} and not value.strip():
            return f"{request.tool} arg {key!r} must not be empty"
        if key == "patch_text" and not value.strip():
            return "apply_patch arg 'patch_text' must not be empty"

    return None


def format_tool_result_for_model(request: ToolRequest, result: ShellResult | dict[str, object] | str) -> str:
    if isinstance(result, str):
        body = result
    elif isinstance(result, dict):
        body = json.dumps(result, indent=2)
    else:
        body = compact_shell_result(result)

    return (
        "Tool result for request:\n"
        f"{json.dumps({'tool': request.tool, 'args': request.args}, indent=2)}\n\n"
        f"{body}"
    )


def make_unified_diff(old_content: str, new_content: str, fromfile: str, tofile: str) -> str:
    """Return a unified diff with stable line endings."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    )
    return "".join(_normalize_diff_line(line) for line in diff_lines)


def summarize_tool_result(result: ShellResult | dict[str, object] | str) -> str:
    if isinstance(result, str):
        return _truncate(result)
    if isinstance(result, ShellResult):
        stdout = _truncate(result.stdout.replace("\n", "\\n"), 160)
        stderr = _truncate(result.stderr.replace("\n", "\\n"), 160)
        return (
            f"exit_code={result.exit_code}, "
            f"elapsed_seconds={result.elapsed_seconds:.3f}, "
            f"stdout={stdout!r}, stderr={stderr!r}"
        )

    if "path" in result:
        details = [f"path={result['path']}"]
        for key in ("created", "deleted", "bytes_written", "bytes_deleted", "replacements"):
            if key in result:
                details.append(f"{key}={result[key]}")
        return ", ".join(details)
    if "old_path" in result and "new_path" in result:
        return f"old_path={result['old_path']}, new_path={result['new_path']}, renamed={result.get('renamed', False)}"
    if "paths" in result:
        paths = result.get("paths")
        count = len(paths) if isinstance(paths, list) else 0
        return f"paths={count}, applied={result.get('applied', False)}"
    if "entries" in result:
        entries = result.get("entries")
        count = len(entries) if isinstance(entries, list) else 0
        return f"path={result.get('path', '.')}, entries={count}, truncated={result.get('truncated', False)}"
    if "matches" in result:
        matches = result.get("matches")
        count = len(matches) if isinstance(matches, list) else 0
        return f"query={result.get('query', '')!r}, matches={count}, truncated={result.get('truncated', False)}"
    if "document_count" in result:
        return f"path={result.get('path', '')}, document_count={result.get('document_count')}, vector_search={result.get('vector_search')}"
    return _truncate(json.dumps(result, sort_keys=True))


def serialize_tool_result(result: ShellResult | dict[str, object] | str) -> dict[str, object] | str:
    if isinstance(result, str):
        return result
    if isinstance(result, ShellResult):
        return {
            "cmd": result.cmd,
            "exit_code": result.exit_code,
            "stdout": compact_text(result.stdout),
            "stderr": compact_text(result.stderr),
            "elapsed_seconds": result.elapsed_seconds,
            "failure_summary": summarize_failure(result) if result.exit_code != 0 else "",
        }
    return result


def compact_shell_result(result: ShellResult) -> str:
    failure = ""
    if result.exit_code != 0:
        failure = (
            "\nfailure_summary:\n"
            f"{summarize_failure(result)}\n"
            "next_fix:\n"
            "Inspect the failure above, update the relevant code or command, then rerun the validation command."
        )
    return (
        f"exit_code: {result.exit_code}\n"
        f"elapsed_seconds: {result.elapsed_seconds:.3f}\n"
        f"stdout:\n{compact_text(result.stdout)}\n"
        f"stderr:\n{compact_text(result.stderr)}"
        f"{failure}"
    )


def compact_text(text: str, max_lines: int = 80, max_chars: int = 6000) -> str:
    if not text:
        return ""
    original_lines = text.splitlines()
    lines = original_lines
    if len(lines) > max_lines:
        head_count = max_lines // 2
        tail_count = max_lines - head_count
        lines = [
            *lines[:head_count],
            f"... omitted {len(original_lines) - max_lines} lines ...",
            *lines[-tail_count:],
        ]
    compacted = "\n".join(lines)
    if len(compacted) > max_chars:
        omitted = len(compacted) - max_chars
        compacted = compacted[: max_chars // 2] + f"\n... omitted {omitted} chars ...\n" + compacted[-max_chars // 2 :]
    return compacted


def summarize_failure(result: ShellResult, max_lines: int = 12) -> str:
    combined = "\n".join(part for part in (result.stderr, result.stdout) if part)
    if not combined.strip():
        return f"Command failed with exit code {result.exit_code}."

    interesting: list[str] = []
    patterns = ("error", "failed", "failure", "traceback", "exception", "assert", "not found")
    for line in combined.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(pattern in stripped.lower() for pattern in patterns):
            interesting.append(stripped)
        if len(interesting) >= max_lines:
            break
    if not interesting:
        interesting = [line.strip() for line in combined.splitlines() if line.strip()][-max_lines:]
    return "\n".join(interesting[:max_lines])


def is_test_command(cmd: str) -> bool:
    normalized = " ".join(cmd.strip().split())
    test_prefixes = (
        "pytest",
        "python -m pytest",
        "uv run pytest",
        "npm test",
        "npm run build",
        "ruff check",
        "mypy",
    )
    return any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in test_prefixes)


def format_model_config(config: ModelConfig) -> str:
    return "\n".join(
        [
            f"base_url: {config.base_url}",
            f"api_key: {_redact_api_key(config.api_key)}",
            f"model: {config.model}",
            f"temperature: {config.temperature}",
            f"max_tokens: {config.max_tokens}",
        ]
    )


def summarize_history_for_memory(history: list[Message], limit: int = 12) -> str:
    if not history:
        return "- No chat context to compact."

    lines: list[str] = []
    for message in history[-limit:]:
        role = message.get("role", "unknown")
        content = compact_text(message.get("content", ""), max_lines=8, max_chars=800)
        lines.append(f"- {role}: {content}")
    return "\n".join(lines)


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


def _optional_int(request: ToolRequest, key: str, default: int) -> int:
    value = request.args.get(key, default)
    if isinstance(value, int):
        return value
    assert isinstance(value, str)
    return int(value)


def _tool_target(tool_name: str, args: dict[str, object]) -> str:
    if tool_name == "shell":
        value = args.get("cmd", "")
    elif tool_name == "search_text":
        value = args.get("path", ".")
    elif tool_name == "rename_file":
        value = f"{args.get('old_path', '')} -> {args.get('new_path', '')}"
    elif tool_name == "apply_patch":
        value = "patch"
    else:
        value = args.get("path", "")
    return str(value)


def _truncate(text: str, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _normalize_diff_line(line: str) -> str:
    return line if line.endswith("\n") else line + "\n"


def _redact_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "****"
    return api_key[:2] + "****" + api_key[-2:]
