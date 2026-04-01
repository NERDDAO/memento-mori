"""Run the spike crew to validate CrewAI + Bonfires KG integration."""

from memento.spike.crew import make_spike_crew


def main():
    crew = make_spike_crew()
    result = crew.kickoff()
    print("\n" + "=" * 60)
    print("SPIKE RESULT:")
    print("=" * 60)
    print(result.raw)
    print("=" * 60)


if __name__ == "__main__":
    main()
