# gateway/src/gateway/engine_state.py
"""Process-wide engine state shared by all transports (HTTP routes and MCP).

This module intentionally owns no transport logic. It holds only state that
must be shared across transports running in the same gateway process — like
the crew-kickoff serialization lock.
"""

from __future__ import annotations

import threading

# Serialises CrewAI crew kickoffs across HTTP routes and the MCP server so
# two concurrent callers (e.g. a legacy HTTP route handler and a new MCP
# handler) don't collide inside the CrewAI runtime.
engine_lock = threading.Lock()
