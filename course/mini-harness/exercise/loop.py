#!/usr/bin/env python3
"""Module 1 exercise: write the agent loop.

Fill in the five TODOs. When you're done, this runs against the practice app
with the scripted mock model:

    python3 exercise/loop.py ~/practice-app scenarios/investigate.json

The model's replies and the tool definitions use the shapes shown in Module 1:
  reply content blocks:  {"type": "text", "text": ...}
                         {"type": "tool_use", "id": ..., "name": ..., "input": {...}}
  tool results you send: {"type": "tool_result", "tool_use_id": <id>, "content": <str>}
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
        # TODO 5: Before running anything, ask the user for permission with
        # input(). If they don't answer "y", return a denial message instead.
        proc = subprocess.run(["bash", "-c", inp["command"]], cwd=workdir,
                              capture_output=True, text=True, timeout=60)
        return f"exit code {proc.returncode}\n{proc.stdout}{proc.stderr}"
    return f"Unknown tool: {name}"


def main():
    workdir = pathlib.Path(sys.argv[1]).expanduser().resolve()
    model = MockBackend(sys.argv[2])
    prompt = sys.argv[3] if len(sys.argv) > 3 else "Why is the login test failing?"

    # TODO 1: Start the conversation history with the user's prompt.
    messages = []

    for step in range(1, 21):
        response = model.complete(SYSTEM, TOOLS, messages)
        print(f"[request {step}] ~{response['usage']['input_tokens']} input tokens")

        # TODO 2: Append the model's reply to the history, and print any text blocks.

        # TODO 3: Collect the tool_use blocks. If there are none, stop the loop.
        tool_calls = []

        # TODO 4: Run each tool with run_tool(), wrap each output in a
        # tool_result block, and append them all to the history as ONE
        # message with role "user".
        for call in tool_calls:
            print(f"tool:  {call['name']}({json.dumps(call['input'])})")


if __name__ == "__main__":
    main()
