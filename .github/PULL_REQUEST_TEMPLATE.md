<!-- Thanks for contributing! Please fill out the checklist below. -->

## What does this PR do?

<!-- A clear, concise description of the change and why it's needed. -->

## Related issues

<!-- e.g. Closes #123 -->

## Type of change

- [ ] Bug fix
- [ ] New tool (read-only / `SAFE_READ`)
- [ ] Docs / packaging / CI
- [ ] Refactor (no behavior change)

## Checklist

- [ ] `pytest -q` passes locally
- [ ] `flake8 . --select=E9,F63,F7,F82` is clean
- [ ] If a tool changed: catalog (`generated/mcp_tools.json`) and registry are updated
- [ ] New tools are **read-only** (`SAFE_READ`) — this edition adds no mutating tools
- [ ] Docs updated where relevant (README / CONTRIBUTING / CHANGELOG)

## How was this verified?

<!-- Unit tests, and/or smoke-test output against a live XCO. -->
