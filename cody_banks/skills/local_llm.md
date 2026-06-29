# Local LLM Skill

## When to use it

Use this skill for local OpenAI-compatible endpoints, llama.cpp server configuration, model settings, chat completion payloads, prompt behavior, or debugging model connection errors.

## Useful commands

```bash
python -m cody_banks.cli --prompt "Say hello in one sentence."
curl http://localhost:8080/v1/models
curl http://localhost:8080/v1/chat/completions
```

## Project conventions

- Do not hard-code a GGUF model path or model name.
- Keep endpoint settings in configuration, not in the LLM client logic.
- Treat `base_url`, `api_key`, `model`, `temperature`, and `max_tokens` as user-configurable.
- Keep request/response parsing compatible with OpenAI-style `/chat/completions`.

## Common traps

- Do not assume a local model server is running.
- Do not treat every connection failure as a code bug.
- Do not invent model output when the endpoint is unreachable.
- Avoid adding remote API dependencies to local-first behavior.

## Done criteria

- The configured endpoint and model settings are visible to the user.
- Connection errors are reported clearly.
- Chat completion request shape is verified with a mock or a real local endpoint when feasible.
- No specific GGUF or server command is required by the code.
