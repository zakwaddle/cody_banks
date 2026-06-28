"""Command line entry point for Cody Banks."""

from __future__ import annotations

import argparse
from pathlib import Path

from cody_banks.agent import Agent
from cody_banks.config import load_config
from cody_banks.llm import LLMClient, LLMError
from cody_banks.workspace import detect_workspace_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cody", description="Run Cody Banks.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Workspace root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a TOML config file.",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Send a one-shot prompt to the configured local model endpoint.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    workspace_root = detect_workspace_root(args.workspace)
    config = load_config(args.config)

    print("Cody Banks")
    print(f"Workspace root: {workspace_root}")
    print(f"Model endpoint: {config.model.base_url}")
    print(f"Permission mode: {config.permissions.mode}")

    if args.prompt is not None:
        client = LLMClient(config.model)
        try:
            response = client.chat_completion(
                [{"role": "user", "content": args.prompt}],
            )
        except LLMError as exc:
            print(f"Model error: {exc}")
            return 1
        print()
        print(response)
    else:
        Agent(
            workspace_root=workspace_root,
            config=config,
            client=LLMClient(config.model),
        ).run_chat()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
