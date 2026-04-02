"""Run the spike crew to validate CrewAI + Bonfires KG integration."""

from memento.log import get_logger
from memento.spike.crew import make_spike_crew

logger = get_logger(__name__)


def main():
    crew = make_spike_crew()
    result = crew.kickoff()
    logger.info("\n" + "=" * 60)
    logger.info("SPIKE RESULT:")
    logger.info("=" * 60)
    logger.info(result.raw)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
