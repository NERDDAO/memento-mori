"""Quest flow — designs a quest, breaks it into stages, and writes NPC dialogue."""

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel
from memento.crews.quest.design import make_quest_design_crew
from memento.crews.quest.stages import make_quest_stage_crew
from memento.crews.quest.dialogue import make_quest_dialogue_crew


class QuestState(BaseModel):
    location: str = ""
    npc: str = ""
    player_level: int = 1
    quest_concept: str = ""
    quest_stages: str = ""
    quest_dialogue: str = ""


class QuestFlow(Flow[QuestState]):
    @start()
    def design(self):
        crew = make_quest_design_crew(
            location=self.state.location,
            npc=self.state.npc,
            player_level=self.state.player_level,
        )
        result = crew.kickoff()
        self.state.quest_concept = result.raw
        return result.raw

    @listen(design)
    def build_stages(self, concept):
        crew = make_quest_stage_crew(quest_concept=concept)
        result = crew.kickoff()
        self.state.quest_stages = result.raw
        return result.raw

    @listen(build_stages)
    def write_dialogue(self, stages):
        crew = make_quest_dialogue_crew(
            quest=f"{self.state.quest_concept}\n\nStages:\n{stages}",
            npc_name=self.state.npc,
        )
        result = crew.kickoff()
        self.state.quest_dialogue = result.raw
        return result.raw
