"""Lazy-initialized Bonfires SDK client with edge query support."""

from __future__ import annotations

from typing import Any

from bonfires.sdk import BonfiresClient
from bonfires.sdk.http import _post

_client: BonfiresClient | None = None


def get_client() -> BonfiresClient:
    """Return a shared BonfiresClient instance, initialized from env vars.

    Patches in get_edges() if not already present on the KG service.
    """
    global _client
    if _client is None:
        _client = BonfiresClient()
        # Patch get_edges onto the KG service (uses /knowledge_graph/expand/entity)
        if not hasattr(_client.kg, "get_edges"):
            _patch_get_edges(_client)
    return _client


def _patch_get_edges(client: BonfiresClient) -> None:
    """Add get_edges() to the KG service using the expand/entity endpoint."""

    def get_edges(
        entity_uuid: str,
        direction: str = "outgoing",
        edge_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query edges for an entity via /knowledge_graph/expand/entity.

        Args:
            entity_uuid: UUID of the entity to expand.
            direction: 'outgoing', 'incoming', or 'both'. Filters by source/target.
            edge_type: Optional edge name filter (e.g. 'CARRIES', 'LOCATED_IN').
            limit: Max edges to return.

        Returns:
            List of edge dicts with source, target, name, fact, uuid,
            valid_at, expired_at fields.
        """
        result = _post(
            client.kg._config,
            "/knowledge_graph/expand/entity",
            body={
                "entity_uuid": entity_uuid,
                "bonfire_id": client.kg._config.bonfire_id,
                "limit": limit,
            },
        )

        edges = result.get("edges", [])

        # Filter by direction
        filtered = []
        for edge in edges:
            src = edge.get("source_node_uuid", edge.get("source", {}).get("uuid", ""))
            tgt = edge.get("target_node_uuid", edge.get("target", {}).get("uuid", ""))

            if direction == "outgoing" and src != entity_uuid:
                continue
            if direction == "incoming" and tgt != entity_uuid:
                continue

            # Filter by edge type
            edge_name = edge.get("name", edge.get("relationship", ""))
            if edge_type and edge_name.upper() != edge_type.upper():
                continue

            # Normalize to consistent format
            filtered.append({
                "uuid": edge.get("uuid", ""),
                "name": edge_name,
                "fact": edge.get("fact", ""),
                "source": edge.get("source", {"uuid": src}),
                "target": edge.get("target", {"uuid": tgt}),
                "valid_at": edge.get("valid_at"),
                "expired_at": edge.get("expired_at"),
                "invalid_at": edge.get("invalid_at"),
            })

        return filtered

    # Also add update_edge since the SDK doesn't have it
    def update_edge(edge_uuid: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update an edge's properties (e.g. expired_at for temporal invalidation)."""
        return _post(
            client.kg._config,
            f"/knowledge_graph/edge/{edge_uuid}/update",
            body={
                "bonfire_id": client.kg._config.bonfire_id,
                **updates,
            },
        )

    client.kg.get_edges = get_edges  # type: ignore[attr-defined]
    client.kg.update_edge = update_edge  # type: ignore[attr-defined]
