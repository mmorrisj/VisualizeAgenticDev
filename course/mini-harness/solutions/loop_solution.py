#!/usr/bin/env python3
"""Module 1 solution: the smallest useful agent harness.

Two tools, one permission check, one loop. Compare with exercise/loop.py.

    python3 solutions/loop_solution.py ~/practice-app scenarios/investigate.json
"""
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from backends import MockBackend  # noqa: E402

TOOLS = [
    {"name": "read_file", "description": "Read a text file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}},
                      "required": ["path"]}},
    {"name": "run_command", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}},
                      "required": ["command"]}},
]
SYSTEM = "You are a coding agent. Use the tools to inspect the repository."


def run_tool(workdir: pathlib.Path, name: str, inp: dict) -> str:
    if name == "read_file":
        return (workdir / inp["path"]).read_text(encoding="utf-8")
    if name == "run_command":
        # The permission check: nothing runs until a human says yes.
        answer = input(f"  allow `{inp['command']}`? [y/N] ").strip().lower()
        if answer != "y":
            return "Permission denied by user."
        proc = subprocess.run(["bash", "-c", inp["command"]], cwd=workdir,
                              capture_output=True, text=True, timeout=60)
        return f"exit code {proc.returncode}\n{proc.stdout}{proc.stderr}"
    return f"Unknown tool: {name}"


def main():
    workdir = pathlib.Path(sys.argv[1]).expanduser().resolve()
    model = MockBackend(sys.argv[2])
    prompt = sys.argv[3] if len(sys.argv) > 3 else "Why is the login test failing?"

    # 1. The conversation starts with the user's request.
    messages = [{"role": "user", "content": prompt}]

    for step in range(1, 21):
        # 2. Send EVERYTHING: system prompt, tool definitions, full history.
        response = model.complete(SYSTEM, TOOLS, messages)
        print(f"[request {step}] ~{response['usage']['input_tokens']} input tokens")

        # 3. Record the model's reply in the history.
        messages.append({"role": "assistant", "content": response["content"]})
        for block in response["content"]:
            if block["type"] == "text":
                print("model:", block["text"])

        # 4. No tool requests means the model is done.
        tool_calls = [b for b in response["content"] if b["type"] == "tool_use"]
        if not tool_calls:
            break

        # 5. Run each requested tool and send the results back.
        results = []
        for call in tool_calls:
            print(f"tool:  {call['name']}({json.dumps(call['input'])})")
            output = run_tool(workdir, call["name"], call["input"])
            results.append({"type": "tool_result", "tool_use_id": call["id"],
                            "content": output})
        messages.append({"role": "user", "content": results})


if __name__ == "__main__":
    main()
