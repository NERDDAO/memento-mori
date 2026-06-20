def test_types_importable_and_shaped():
    from memento.cxn import types as t
    # TypedDicts expose __annotations__ with the spec field sets
    assert set(t.StatePrimitive.__annotations__) == {"substrate", "op", "args", "if_condition"}
    assert set(t.SemanticFrame.__annotations__) == {"predicate", "roles", "confidence", "raw_text"}
    assert set(t.CxnDef.__annotations__) == {
        "name", "predicate", "mcp_tool_name", "description", "semantic_roles",
        "restrictions", "guards", "chain_mirror", "effect_template", "episode_template",
    }
    assert set(t.MatchedCxn.__annotations__) == {"cxn", "bound_roles"}
    assert set(t.StateDelta.__annotations__) == {"op", "target_uuid", "field", "before", "after"}
    assert issubclass(t.ConstructionError, Exception)


def test_constructicon_is_protocol():
    from memento.cxn import types as t
    assert hasattr(t.Constructicon, "match") and hasattr(t.Constructicon, "all_cxns")
