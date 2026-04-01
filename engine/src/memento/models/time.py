# engine/src/memento/models/time.py
from pydantic import BaseModel

MOON_PHASES = [
    ("New Moon", "\U0001f311"),
    ("Waxing Crescent", "\U0001f312"),
    ("First Quarter", "\U0001f313"),
    ("Waxing Gibbous", "\U0001f314"),
    ("Full Moon", "\U0001f315"),
    ("Waning Gibbous", "\U0001f316"),
    ("Last Quarter", "\U0001f317"),
    ("Waning Crescent", "\U0001f318"),
]

MONTHS = [
    "Ashfall", "Bleakwind", "Cinderwatch", "Duskhollow",
    "Embertide", "Frostmere", "Grimshade", "Hollowmoon",
    "Ironveil", "Jadewane", "Knellrise", "Lostember",
]

TIMES_OF_DAY = ["Dawn", "Morning", "Midday", "Afternoon", "Dusk", "Evening", "Night", "Midnight"]


class WorldTime(BaseModel):
    tick: int = 0

    @property
    def time_of_day(self) -> str:
        return TIMES_OF_DAY[self.tick % len(TIMES_OF_DAY)]

    @property
    def day_number(self) -> int:
        return (self.tick // len(TIMES_OF_DAY)) % 30 + 1

    @property
    def month(self) -> str:
        return MONTHS[(self.tick // (len(TIMES_OF_DAY) * 30)) % len(MONTHS)]

    @property
    def season(self) -> str:
        month_idx = (self.tick // (len(TIMES_OF_DAY) * 30)) % len(MONTHS)
        return ["Winter", "Spring", "Summer", "Autumn"][month_idx // 3]

    @property
    def moon_phase(self) -> str:
        return MOON_PHASES[(self.tick // len(TIMES_OF_DAY)) % len(MOON_PHASES)][0]

    @property
    def moon_icon(self) -> str:
        return MOON_PHASES[(self.tick // len(TIMES_OF_DAY)) % len(MOON_PHASES)][1]

    def advance(self, ticks: int = 1) -> "WorldTime":
        return WorldTime(tick=self.tick + ticks)

    def to_display(self) -> dict:
        return {
            "moon_phase": self.moon_phase,
            "moon_icon": self.moon_icon,
            "day_name": "",
            "day_number": self.day_number,
            "month": self.month,
            "season": self.season,
            "time_of_day": self.time_of_day,
        }
