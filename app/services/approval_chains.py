CHAIN_ROLE_LEVEL: dict[str, int] = {
    "staff": 0,
    "department_head": 1,
    "regional_department_head": 2,
    "regional_manager": 3,
    "finance_controller": 4,
    "cfo": 5,
    "md": 6,
}

# Per the CFO's 2026-07 review call, the Invoice Submitter Form (formerly
# "Procurement Form") chain is collapsed to CFO-only for now — Project Owner /
# Procurement / Finance & Control are deferred as a later "backward
# integration" once those roles/PO records actually exist. Flip this flag to
# restore the full chain without any other code change.
PROJECT_PAYMENT_BACKWARD_INTEGRATION_ENABLED = False

# Same collapse applied to Cash Advance / State of Expense / IOU — these went
# through the full Department Head -> Regional Department Head -> Regional
# Manager -> Finance Controller -> CFO chain; simplified to requester -> CFO
# only. Flip this flag to restore the full chain without any other code change.
ADV_EXP_PROP_BACKWARD_INTEGRATION_ENABLED = False

_PROJECT_PAYMENT_FULL_CHAIN = ["project_owner", "procurement", "finance_control", "cfo"]
_PROJECT_PAYMENT_CFO_ONLY_CHAIN = ["cfo"]
_ADV_EXP_PROP_FULL_CHAIN = [
    "department_head",
    "regional_department_head",
    "regional_manager",
    "finance_controller",
    "cfo",
]
_ADV_EXP_PROP_CFO_ONLY_CHAIN = ["cfo"]
_THRESHOLD = 150_000.0


def build_chain(request_type: str, amount: float, requester_role: str) -> list[str]:
    if request_type == "project_payment":
        return list(
            _PROJECT_PAYMENT_FULL_CHAIN
            if PROJECT_PAYMENT_BACKWARD_INTEGRATION_ENABLED
            else _PROJECT_PAYMENT_CFO_ONLY_CHAIN
        )

    chain = list(
        _ADV_EXP_PROP_FULL_CHAIN
        if ADV_EXP_PROP_BACKWARD_INTEGRATION_ENABLED
        else _ADV_EXP_PROP_CFO_ONLY_CHAIN
    )

    # 1. Threshold rule — drop CFO for sub-₦150k amounts (full chain only; the
    # CFO-only chain always requires the CFO regardless of amount).
    if ADV_EXP_PROP_BACKWARD_INTEGRATION_ENABLED and amount < _THRESHOLD:
        chain = [r for r in chain if r != "cfo"]

    # 2. Seniority-skip — drop every role <= requester's own seniority level
    # (e.g. the CFO requesting their own advance shouldn't need self-approval).
    requester_level = CHAIN_ROLE_LEVEL.get(requester_role, 0)
    chain = [r for r in chain if CHAIN_ROLE_LEVEL.get(r, 0) > requester_level]

    return chain


def get_effective_amount(req) -> float:
    """Returns the monetary amount for any request type (ORM or Pydantic)."""
    req_type = getattr(req, "type", None)
    if req_type == "project_payment":
        return float(getattr(req, "amount_due", None) or 0)
    if req_type in ("advance", "expense"):
        return float(getattr(req, "amount", None) or 0)
    if req_type == "proposal":
        return float(getattr(req, "amount_proposed", None) or 0)
    return 0.0
