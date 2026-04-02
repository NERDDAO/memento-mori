"""Item generation flow — creates items for a location."""

from memento.core import Flow, listen, start
from pydantic import BaseModel

from memento.crews.item_gen.concept import make_item_concept_crew
from memento.crews.item_gen.mechanics import make_item_mechanics_crew
from memento.crews.item_gen.balance import make_balance_review_crew


class ItemGenState(BaseModel):
    location_name: str = ""
    rarity_budget: str = "common"
    num_items: int = 3
    item_concepts: str = ""
    items_mechanized: str = ""
    items_final: str = ""


class ItemGenerationFlow(Flow[ItemGenState]):
    @start()
    def concept_items(self):
        crew = make_item_concept_crew(
            location_name=self.state.location_name,
            rarity_budget=self.state.rarity_budget,
            num_items=self.state.num_items,
        )
        result = crew.kickoff()
        self.state.item_concepts = result.raw
        return result.raw

    @listen(concept_items)
    def mechanize_items(self, concepts):
        crew = make_item_mechanics_crew(item_concept=concepts)
        result = crew.kickoff()
        self.state.items_mechanized = result.raw
        return result.raw

    @listen(mechanize_items)
    def balance_check(self, mechanized):
        crew = make_balance_review_crew(items=mechanized)
        result = crew.kickoff()
        self.state.items_final = result.raw
        return result.raw
