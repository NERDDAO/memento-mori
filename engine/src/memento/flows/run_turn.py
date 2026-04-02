"""Run a single game turn — for manual testing."""

from memento.flows.game_turn import GameTurnFlow
from memento.log import get_logger

logger = get_logger(__name__)


def main():
    flow = GameTurnFlow()
    flow.state.player_name = "Kael"
    flow.state.location_name = "The Bleeding Lantern"
    flow.state.action = "I look around the tavern, taking in the details of the room."

    flow.kickoff()

    logger.info("\n" + "=" * 60)
    logger.info("NARRATIVE:")
    logger.info("=" * 60)
    logger.info(flow.state.narrative)
    logger.info("=" * 60)
    logger.info("Events: %s", flow.state.events)
    logger.info("Plausible: %s", flow.state.plausible)


if __name__ == "__main__":
    main()
