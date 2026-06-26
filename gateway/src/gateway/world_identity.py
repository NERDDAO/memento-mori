"""Single source of truth for the world's bonfire id.

graph-memory coerces the {bonfire_id} URL path param to a Mongo ObjectId and
404s anything that isn't one. The SDK already reads BONFIRE_ID (the ObjectId)
from the environment for every client.kg.* call; the scene / cxn / comprehend /
memory paths historically hardcoded the slug "mm-world-v1" and so never agreed
with the KG. This resolver makes them agree: read BONFIRE_ID from the env (the
same value the SDK uses), falling back to the slug only for local / no-KG play.
"""

from __future__ import annotations

import os

_SLUG_FALLBACK = "mm-world-v1"


def resolve_bonfire_id() -> str:
    return os.environ.get("BONFIRE_ID") or _SLUG_FALLBACK
