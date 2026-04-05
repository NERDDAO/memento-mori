#!/usr/bin/env python3
"""Generate TypeScript type definitions from the canonical Pydantic StateUpdate model.

Usage:
    python scripts/gen-types.py

Outputs:
    client/src/types/schema.generated.ts

This avoids needing an npm json-schema-to-typescript dependency by doing
a simple direct conversion from Pydantic's JSON Schema output.
"""

import json
import sys
from pathlib import Path

# Ensure engine is importable
engine_src = Path(__file__).parent.parent / "engine" / "src"
sys.path.insert(0, str(engine_src))

from memento.models.state_update import (
    StateUpdate,
    ExitUpdate,
    EntityRefUpdate,
    InventoryItemUpdate,
    WorldTimeDisplay,
    RoomMapUpdate,
    CombatEvent,
    InventoryEvent,
    EventSummary,
    QuestSummary,
    FactionStanding,
)

OUTPUT = Path(__file__).parent.parent / "client" / "src" / "types" / "schema.generated.ts"


def json_schema_type_to_ts(prop: dict, required: bool) -> str:
    """Convert a JSON Schema property to a TypeScript type string."""
    if "anyOf" in prop:
        # Handle Optional types (anyOf with null)
        types = [t for t in prop["anyOf"] if t.get("type") != "null"]
        null_present = any(t.get("type") == "null" for t in prop["anyOf"])
        if types:
            ts = json_schema_type_to_ts(types[0], required=True)
            return f"{ts} | null" if null_present else ts
        return "any"

    ref = prop.get("$ref", "")
    if ref:
        name = ref.split("/")[-1]
        return name

    t = prop.get("type", "any")
    if t == "string":
        return "string"
    elif t == "integer" or t == "number":
        return "number"
    elif t == "boolean":
        return "boolean"
    elif t == "array":
        items = prop.get("items", {})
        inner = json_schema_type_to_ts(items, required=True)
        return f"{inner}[]"
    elif t == "object":
        return "Record<string, any>"
    return "any"


def model_to_ts(model_class, schema: dict) -> str:
    """Generate a TypeScript interface from a Pydantic model's JSON Schema."""
    name = model_class.__name__
    props = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for field_name, field_schema in props.items():
        is_required = field_name in required_fields
        ts_type = json_schema_type_to_ts(field_schema, is_required)
        optional = "" if is_required else "?"
        lines.append(f"  {field_name}{optional}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def main():
    models = [
        ExitUpdate,
        EntityRefUpdate,
        InventoryItemUpdate,
        WorldTimeDisplay,
        RoomMapUpdate,
        CombatEvent,
        InventoryEvent,
        EventSummary,
        QuestSummary,
        FactionStanding,
        StateUpdate,
    ]

    # Hand-authored sub-interfaces for RoomMap dict fields (not in Pydantic schema)
    room_map_subtypes = """\
export interface RoomMapNpc {
  id?: string;
  name?: string;
  x?: number;
  y?: number;
  ch?: string;
}

export interface RoomMapItem {
  id?: string;
  name?: string;
  x?: number;
  y?: number;
  ch?: string;
}

export interface RoomMapExit {
  direction?: string;
  target?: string;
  target_id?: string;
  x?: number;
  y?: number;
  ch?: string;
}

export interface RoomMapSpawn {
  x?: number;
  y?: number;
}
"""

    parts = [
        "// AUTO-GENERATED — do not edit manually.",
        "// Source: engine/src/memento/models/state_update.py",
        f"// Run: python scripts/gen-types.py",
        "",
    ]

    for model in models:
        schema = model.model_json_schema()
        parts.append(model_to_ts(model, schema))
        parts.append("")
        # Insert hand-authored RoomMap sub-interfaces after RoomMapUpdate
        if model is RoomMapUpdate:
            parts.append(room_map_subtypes)

    parts.append(f"export const SCHEMA_VERSION = {StateUpdate.model_fields['schema_version'].default};")
    parts.append("")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(parts))
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    main()
