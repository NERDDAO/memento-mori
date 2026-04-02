"""Combat flow — assess, resolve, apply consequences, check death."""

from memento.core import Flow, listen, router, start
from pydantic import BaseModel

from memento.crews.combat.assessment import make_combat_assessment_crew
from memento.crews.combat.attack import make_attack_resolution_crew
from memento.crews.combat.ability import make_ability_resolution_crew
from memento.crews.combat.consequence import make_consequence_crew
from memento.flows.permadeath import PermadeathFlow


class CombatState(BaseModel):
    action: str = ""
    attacker: str = ""
    target: str = ""
    location: str = ""
    context: str = ""
    attacker_stats: str = ""
    target_stats: str = ""
    assessment: str = ""
    action_type: str = "attack"  # attack, ability, flee
    resolution: str = ""
    consequences: str = ""
    target_dead: bool = False


class CombatFlow(Flow[CombatState]):
    @start()
    def assess(self):
        crew = make_combat_assessment_crew(
            action=self.state.action,
            attacker=self.state.attacker,
            target=self.state.target,
            location=self.state.location,
        )
        result = crew.kickoff()
        self.state.assessment = result.raw
        # Try to detect action type from assessment
        raw_lower = result.raw.lower()
        if "flee" in raw_lower or "escape" in raw_lower:
            self.state.action_type = "flee"
        elif "ability" in raw_lower or "spell" in raw_lower:
            self.state.action_type = "ability"
        else:
            self.state.action_type = "attack"
        return result.raw

    @listen(assess)
    def resolve(self, assessment):
        if self.state.action_type == "ability":
            crew = make_ability_resolution_crew(
                ability=self.state.action,
                user_stats=self.state.attacker_stats,
                target_stats=self.state.target_stats,
            )
        else:
            crew = make_attack_resolution_crew(
                action=self.state.action,
                attacker_stats=self.state.attacker_stats,
                target_stats=self.state.target_stats,
                environment=self.state.context,
            )
        result = crew.kickoff()
        self.state.resolution = result.raw
        return result.raw

    @listen(resolve)
    def apply_consequences(self, resolution):
        crew = make_consequence_crew(
            resolution=resolution,
            attacker=self.state.attacker,
            target=self.state.target,
        )
        result = crew.kickoff()
        self.state.consequences = result.raw
        # Check if target died
        if "dead" in result.raw.lower() or "killed" in result.raw.lower() or "slain" in result.raw.lower():
            self.state.target_dead = True
        return result.raw

    @listen(apply_consequences)
    def check_death(self, consequences):
        if self.state.target_dead:
            death_flow = PermadeathFlow()
            death_flow.state.player_name = self.state.target
            death_flow.state.cause = self.state.action
            death_flow.state.location = self.state.location
            death_flow.state.context = self.state.context
            death_flow.kickoff()
            return death_flow.state.narrative
        return consequences
