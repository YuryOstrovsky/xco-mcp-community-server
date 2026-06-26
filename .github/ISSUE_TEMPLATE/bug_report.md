---
name: Bug report
about: Report a problem with the XCO MCP server
title: "[bug] "
labels: ["bug"]
---

## Describe the bug
A clear and concise description of what the bug is.

## To reproduce
Steps to reproduce — include the tool name and inputs, e.g.:

```bash
curl -sS -X POST http://127.0.0.1:8000/invoke \
  -H 'Content-Type: application/json' \
  -d '{"tool":"<tool_name>","inputs":{ ... }}'
```

## Expected behavior
What you expected to happen.

## Actual behavior
What actually happened (include the response body / error and any `error_id`).

## Environment
- Server commit / version:
- Python version:
- Deployment: (local `api/run.py` / Docker / other)
- XCO version (if known):

## Logs
Relevant log lines (redact credentials).
