# mcp_runtime/context_merge.py

from copy import deepcopy
from typing import Dict

def merge_context(
    *,
    user_ctx: Dict,
    session_ctx: Dict,
    inferred_ctx: Dict
) -> Dict:
    """
    Merge precedence:
    user > session > inferred
    """

    result = {}

    for source in (inferred_ctx, session_ctx, user_ctx):
        for k, v in source.items():
            if v is not None:
                result[k] = deepcopy(v)

    return result

