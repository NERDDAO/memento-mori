"""Run world generation — for manual testing."""

from memento.flows.world_gen import WorldGenFlow
from memento.log import get_logger

logger = get_logger(__name__)


def main():
    flow = WorldGenFlow()
    flow.state.theme = "haunted marshlands"
    flow.state.player_level = 3

    logger.info("Starting world generation for: haunted marshlands")
    logger.info("This will take several minutes (many LLM calls)...")

    flow.kickoff()

    logger.info("\n" + "=" * 60)
    logger.info("WORLD GENERATION COMPLETE")
    logger.info("=" * 60)
    logger.info("Region: %s", flow.state.region_name)
    logger.info("Locations created: %d", len(flow.state.locations_created))
    for i, loc in enumerate(flow.state.locations_created):
        logger.info("\n--- Location %d ---", i + 1)
        logger.info(loc)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
