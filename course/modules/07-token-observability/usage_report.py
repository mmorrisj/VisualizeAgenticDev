#!/usr/bin/env python3
"""Summarize mini-harness usage logs (JSONL). Standard library only.

    python3 usage_report.py ~/practice-app/.mini-harness/usage.jsonl
    python3 usage_report.py LOG --session 05f96190
    python3 usage_report.py LOG --rates 3,15,0.30,3.75   # input,output,cache_read,cache_write per 1M tokens

Rates are deliberately not built in: use your organization's contracted rates,
or leave them off to compare sessions by tokens alone.
"""
import argparse
import collections
import json
import pathlib

TOKEN_KEYS = ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")
BAR_WIDTH = 40


def load(path):
    sessions = collections.OrderedDict()
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            sessions.setdefault(rec["session"], []).append(rec)
    return sessions


def context_of(req):
    """Everything the model processed as input on this request."""
    return req["input_tokens"] + req["cache_read_tokens"] + req["cache_write_tokens"]


def report(session_id, records, rates):
    reqs = [r for r in records if r["type"] == "api_request"]
    tools = [r for r in records if r["type"] == "tool"]
    compactions = [r for r in records if r["type"] == "compaction"]
    if not reqs:
        return
    totals = {k: sum(r[k] for r in reqs) for k in TOKEN_KEYS}
    processed_input = totals["input_tokens"] + totals["cache_read_tokens"] + totals["cache_write_tokens"]
    estimated = any(r.get("estimated") for r in reqs)

    print(f"\n=== session {session_id} · {reqs[0]['backend']} / {reqs[0]['model']}"
          f"{'  (ESTIMATED tokens)' if estimated else ''}")
    print(f"requests: {len(reqs)}   tool calls: {len(tools)}   compactions: {len(compactions)}")
    print("tokens:   " + "   ".join(f"{k.replace('_tokens', '')}: {v:,}" for k, v in totals.items()))
    if processed_input:
        share = totals["cache_read_tokens"] / processed_input
        print(f"cache:    {share:.0%} of input was read from cache")
    last = context_of(reqs[-1])
    print(f"growth:   first request {context_of(reqs[0]):,} -> last request {last:,} input tokens;"
          f" total input over the session {processed_input:,}"
          f" ({processed_input / max(last, 1):.1f}x the final context size)")
    if rates:
        cost = sum(totals[k] * rate / 1_000_000 for k, rate in
                   zip(("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"), rates))
        print(f"cost:     {cost:,.4f} at the rates given")

    print("\ncontext per request (input tokens processed, share served from cache, tools requested)")
    peak = max(context_of(r) for r in reqs)
    compacted_after = set()  # request numbers followed by a compaction (log order)
    last_request = None
    for rec in records:
        if rec["type"] == "api_request":
            last_request = rec["request"]
        elif rec["type"] == "compaction" and last_request is not None:
            compacted_after.add(last_request)
    for r in reqs:
        size = context_of(r)
        bar = "#" * max(1, round(BAR_WIDTH * size / peak))
        calls = ",".join(r.get("tool_calls", [])) or "(final answer)"
        marker = "  <- compacted after this" if r["request"] in compacted_after else ""
        cached = f"{r['cache_read_tokens'] / size:4.0%}" if size and not r.get("estimated") else "   -"
        if not r.get("estimated") and r["request"] > 1 and r["cache_read_tokens"] == 0:
            marker += "  <- cache miss: whole context re-processed"
        print(f"  {r['request']:>3} {bar:<{BAR_WIDTH}} {size:>7,} {cached}  {calls}{marker}")

    if tools:
        print("\nlargest tool results (characters; about 4 per token)")
        for t in sorted(tools, key=lambda t: -t["result_chars"])[:5]:
            print(f"  {t['result_chars']:>7,}  {t['tool']}({t.get('target', '')[:60]})")
        repeats = collections.Counter((t["tool"], t.get("target", "")) for t in tools)
        dupes = [(k, n) for k, n in repeats.items() if n > 1]
        if dupes:
            print("\nrepeated calls (same tool, same target)")
            for (tool, target), n in sorted(dupes, key=lambda x: -x[1]):
                print(f"  {n}x  {tool}({target[:60]})")
        decisions = collections.Counter(t["source"].split(":")[0] for t in tools)
        print("\npermission decisions by source: " +
              ", ".join(f"{src}: {n}" for src, n in decisions.most_common()))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("log", nargs="?", default=".mini-harness/usage.jsonl")
    parser.add_argument("--session", help="report one session id")
    parser.add_argument("--rates", help="input,output,cache_read,cache_write per million tokens")
    args = parser.parse_args()
    rates = [float(x) for x in args.rates.split(",")] if args.rates else None
    if rates and len(rates) != 4:
        raise SystemExit("--rates needs four comma-separated numbers")
    sessions = load(args.log)
    for sid, records in sessions.items():
        if args.session and sid != args.session:
            continue
        report(sid, records, rates)


if __name__ == "__main__":
    main()
