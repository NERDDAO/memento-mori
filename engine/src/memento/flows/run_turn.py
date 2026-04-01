"""Run a single game turn — for manual testing."""

from memento.flows.game_turn import GameTurnFlow


def main():
    flow = GameTurnFlow()
    flow.state.player_name = "Kael"
    flow.state.location_name = "The Bleeding Lantern"
    flow.state.action = "I look around the tavern, taking in the details of the room."

    flow.kickoff()

    print("\n" + "=" * 60)
    print("NARRATIVE:")
    print("=" * 60)
    print(flow.state.narrative)
    print("=" * 60)
    print(f"Events: {flow.state.events}")
    print(f"Plausible: {flow.state.plausible}")


if __name__ == "__main__":
    main()
