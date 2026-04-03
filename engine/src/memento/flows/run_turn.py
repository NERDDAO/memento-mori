"""Run a single game turn — for manual testing."""

from memento.round_controller import RoundController
from memento.log import get_logger

logger = get_logger(__name__)


def main():
    controller = RoundController(
        location="The Bleeding Lantern",
        actions=[{
            "player_name": "Kael",
            "action": "I look around the tavern, taking in the details of the room.",
        }],
    )
    narrative, state_update = controller.run()

    logger.info("\n" + "=" * 60)
    logger.info("NARRATIVE:")
    logger.info("=" * 60)
    logger.info(narrative)
    logger.info("=" * 60)
    logger.info("State update: %s", state_update)


if __name__ == "__main__":
    main()
