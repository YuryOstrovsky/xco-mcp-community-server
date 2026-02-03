# mcp_runtime/intent_normalizer.py

import re
from typing import Dict


class IntentNormalizationError(Exception):
    pass


class IntentNormalizer:
    """
    Phase 4.1:
    Normalize free-text intent into canonical form.
    """

    def normalize(self, intent: str) -> Dict:
        """
        Returns:
        {
            "action": "...",
            "object": "...",
            "scope": {...},
            "canonical": "..."
        }
        """

        if not intent or not intent.strip():
            raise IntentNormalizationError("Empty intent")

        text = intent.strip().lower()

        # ---- Normalize synonyms ----
        text = text.replace("list", "show")
        text = text.replace("display", "show")

        # =========================================================
        # Pattern 1: show switches in fabric <fabric>
        # =========================================================
        m = re.match(r"show\s+switches\s+in\s+fabric\s+(.+)", text)
        if m:
            fabric = m.group(1).strip()

            return {
                "action": "show",
                "object": "switches",
                "scope": {
                    "fabric": fabric,
                },
                "canonical": f"show switches in fabric {fabric}",
            }

        # =========================================================
        # Pattern 2: show device <device>
        # =========================================================
        m = re.match(r"show\s+device\s+(.+)", text)
        if m:
            device = m.group(1).strip()

            return {
                "action": "show",
                "object": "device",
                "scope": {
                    "device": device,
                },
                "canonical": f"show device {device}",
            }

        # =========================================================
        # Pattern 3: show switch <device> (singular alias)
        # =========================================================
        m = re.match(r"show\s+switch\s+(.+)", text)
        if m:
            device = m.group(1).strip()

            return {
                "action": "show",
                "object": "device",
                "scope": {
                    "device": device,
                },
                "canonical": f"show device {device}",
            }

        # ---- Fallback ----
        raise IntentNormalizationError(f"Unrecognized intent pattern: '{intent}'")
