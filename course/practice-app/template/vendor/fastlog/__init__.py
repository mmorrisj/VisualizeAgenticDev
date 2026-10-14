"""fastlog: minimal structured logging helper (vendored copy, v0.3.1)."""
import json
import time


def log_event(event: str, **fields) -> dict:
    """Print one JSON log line and return the record."""
    record = {"ts": round(time.time(), 3), "event": event, **fields}
    print(json.dumps(record))
    return record
