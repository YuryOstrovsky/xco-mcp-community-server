"""Shared pytest setup — make the suite run offline, from the repo root.

These tests must NOT require a live XCO / SLX backend. We chdir to the repo root
(so relative paths like ``generated/mcp_tools.json`` resolve) and seed dummy
credentials so imports never block on a real ``.env``.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# Dummy config so `import api.app` / registry load never needs a real backend.
# (load_dotenv(override=False) won't clobber these, so tests stay deterministic
# even on a dev box that has a populated .env.)
os.environ.setdefault("XCO_HOST", "xco.invalid")
os.environ.setdefault("XCO_USERNAME", "test")
os.environ.setdefault("XCO_PASS", "test")
os.environ.setdefault("XCO_VERIFY_TLS", "false")
os.environ.setdefault("RESTCONF_USERNAME", "admin")
os.environ.setdefault("RESTCONF_PASS", "test")
