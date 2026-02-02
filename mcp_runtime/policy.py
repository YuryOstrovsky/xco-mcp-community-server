class PolicyViolation(Exception):
    pass


def enforce_policy(tool, auto_mode=False):
    policy = tool["policy"]

    if auto_mode and not policy["allowed_in_auto_mode"]:
        raise PolicyViolation(
            f"Tool '{tool['name']}' is not allowed in auto mode"
        )

    if policy["requires_confirmation"]:
        raise PolicyViolation(
            f"Tool '{tool['name']}' requires human confirmation"
        )

