"""Run world generation — for manual testing."""

from memento.flows.world_gen import WorldGenFlow


def main():
    flow = WorldGenFlow()
    flow.state.theme = "haunted marshlands"
    flow.state.player_level = 3

    print("Starting world generation for: haunted marshlands")
    print("This will take several minutes (many LLM calls)...")

    flow.kickoff()

    print("\n" + "=" * 60)
    print("WORLD GENERATION COMPLETE")
    print("=" * 60)
    print(f"Region: {flow.state.region_name}")
    print(f"Locations created: {len(flow.state.locations_created)}")
    for i, loc in enumerate(flow.state.locations_created):
        print(f"\n--- Location {i+1} ---")
        print(loc)
    print("=" * 60)


if __name__ == "__main__":
    main()
