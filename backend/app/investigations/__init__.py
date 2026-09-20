"""Automatic investigation engine.

Turns one inspection result into an evidence-backed industrial investigation by
orchestrating the existing engines (root cause, bottleneck, economics,
recommendations). It never re-implements analysis and never fabricates a stage:
a stage that cannot run is recorded as DATA_GAP / AWAITING_INPUT / FAILED with
the exact reason.

State machine (per stage and overall):
  RECEIVED -> PREPROCESSING -> CLASSIFYING -> LOCALIZING -> CHECKING_ROBUSTNESS
  -> PROCESS_CORRELATION -> ROOT_CAUSE -> BOTTLENECK -> IMPACT -> RECOMMENDATION
  -> COMPLETE | REVIEW_REQUIRED | DATA_GAP
"""

from .runner import (
    get_investigation,
    investigation_events,
    list_investigations,
    run_investigation,
)

__all__ = [
    "get_investigation",
    "investigation_events",
    "list_investigations",
    "run_investigation",
]
