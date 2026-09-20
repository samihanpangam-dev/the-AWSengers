"""
security.py — Root-level proxy for backend.security.
"""
from backend.security import (
    CedarDecision,
    CedarSecurityEngine,
    cedar_engine,
    get_cedar_policy_path,
)

__all__ = [
    "CedarDecision",
    "CedarSecurityEngine",
    "cedar_engine",
    "get_cedar_policy_path",
]
