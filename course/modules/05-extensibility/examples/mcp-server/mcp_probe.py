#!/usr/bin/env python3
"""Act as an MCP client (a harness) and print every message on the wire.

This is what a harness does when it starts a stdio MCP server: launch the
process, negotiate a protocol version, ask for the tool list (which goes into
the model's context), and later forward the model's tool calls.

    python3 mcp_probe.py                       # talks to practice_db_server.py
    python3 mcp_probe.py -- python3 other.py   # or any stdio MCP server command
"""
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
command = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else \
    [sys.executable, str(HERE / "practice_db_server.py")]

proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def send(msg: dict, expect_reply: bool = True):
    line = json.dumps(msg)
    print(f"\n--> {line}")
    proc.stdin.write(line + "\n")
    proc.stdin.flush()
    if expect_reply:
        reply = proc.stdout.readline()
        print(f"<-- {reply.strip()}")
        return json.loads(reply)
    return None


send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
      "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                 "clientInfo": {"name": "mcp-probe", "version": "0.1"}}})
send({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)

tools = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
listing = json.dumps(tools)
print(f"\n[{len(tools)} tools; their definitions add about {len(listing) // 4} tokens "
      "to every request in a harness that loads them all]")

send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
      "params": {"name": "run_select",
                 "arguments": {"sql": "SELECT name, created FROM users WHERE password_hash = ''"}}})
send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
      "params": {"name": "run_select", "arguments": {"sql": "DELETE FROM users"}}})

proc.stdin.close()
proc.wait(timeout=5)
