# mini-harness

A small agent harness written for teaching. It uses only the Python standard library (3.9+), so it runs on the air-gapped network with no installs. Every part of a harness covered in this course is in `harness.py`, in code short enough to read in one sitting.

| File | What it is |
|---|---|
| `harness.py` | The reference harness: agent loop, tools, permission rules, hooks, compaction, usage logging |
| `backends.py` | Model connections: `mock` (scripted, offline), `anthropic` (Messages API), `openai` (chat completions, used by most self-hosted model servers) |
| `exercise/loop.py` | Module 1 exercise: write the agent loop yourself |
| `solutions/loop_solution.py` | Module 1 solution |
| `policies/*.json` | Permission policies: `default`, `naive-matching` (a deliberate flaw), `strict` (Module 2 solution) |
| `hooks/*.py` | Example pre-tool hooks used by `strict.json` |
| `scenarios/*.json` | Scripted mock-model sessions that recreate each walkthrough screen |

## Quick start (no model needed)

```bash
../practice-app/setup.sh ~/practice-app
python3 harness.py --workdir ~/practice-app --scenario scenarios/investigate.json \
    --prompt "The login test is failing. Find out why, but don't change anything yet."
```

The mock backend replays a script. It does not react to tool results or denials the way a real model would, but everything else (permissions, hooks, tool execution, logging) is real.

## Connecting a real model

```bash
export MINI_HARNESS_API_KEY=...              # never put keys in the command line history
python3 harness.py --workdir ~/practice-app \
    --backend openai --base-url https://llm.internal.example/v1 --model <model-name>
```

| Option | Meaning |
|---|---|
| `--backend anthropic` | Endpoint speaks the Anthropic Messages API; posts to `<base-url>/messages` |
| `--backend openai` | Endpoint speaks OpenAI-compatible chat completions; posts to `<base-url>/chat/completions` |
| `--auth-style` | `x-api-key` or `bearer` (defaults: anthropic uses `x-api-key`, openai uses `bearer`) |
| `--ca-file` | PEM bundle for an internal certificate authority |
| `--policy` | Permission policy file (default `policies/default.json`) |
| `--context-limit` | Token budget for the context meter and compaction (default 32000) |
| `--show-requests` | Print every request body: see exactly what is sent |
| `--log` | Usage log location (default `<workdir>/.mini-harness/usage.jsonl`) |

`HTTPS_PROXY` and `NO_PROXY` are honored. Settings can also come from `MINI_HARNESS_BASE_URL`, `MINI_HARNESS_MODEL`, `MINI_HARNESS_API_KEY`, and `MINI_HARNESS_CA_FILE`.

Tool calling quality varies a lot between models. If a self-hosted model never calls tools, or returns malformed arguments, check that its server has tool calling enabled; many servers need a flag or a specific chat template for it.

## Interactive commands

Run without `--prompt` for an interactive session:

| Command | What it shows |
|---|---|
| `/context` | Estimated tokens by category: system prompt, tool definitions, messages, tool results |
| `/usage` | Requests and token totals for this session |
| `/clear` | Drop the conversation (system prompt and tools remain) |
| `/quit` | Exit |

## Policy file format

```json
{
  "mode": "ask",
  "allow": ["read_file", "run_command(python3 run_tests.py*)"],
  "ask":   ["run_command(git push*)"],
  "deny":  ["read_file(.env)", "edit_file(tests/*)", "run_command(curl *)"],
  "hooks": {"pre_tool": ["python3 ../hooks/protect_secrets.py"]},
  "scrub_env": true,
  "sandbox_prefix": ["unshare", "-rn"],
  "command_timeout": 60,
  "max_output_chars": 8000
}
```

- A rule is `tool` or `tool(pattern)`. Patterns use shell-style wildcards and match the file path for file tools, or **each subcommand** of a `run_command`.
- Order of evaluation: hooks first (exit code 2 blocks), then deny, then ask, then allow, then `mode`.
- Commands containing `$(...)`, backticks, or process substitution can't be analyzed, so allow rules never approve them.
- Hook commands run from the policy file's folder and receive the tool call as JSON on stdin.

This is a teaching tool, not a security product. Module 2 explains which of these controls are real boundaries and which are not.
