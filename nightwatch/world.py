"""The town of Cedar Hollow: ground features, townsfolk, stars and sky bands."""
import random

from .constants import WORLD_W, WORLD_H, KARMAN, GROUND_Y

STAR_SEED = 1985

# Sky colour bands from the top of the atmosphere (KARMAN) down to the horizon.
ATMO_BANDS = ["atmo0", "atmo0", "atmo1", "atmo1", "atmo2", "atmo3", "atmo4", "atmo5", "atmo6"]


def sky_name(y):
    """Palette name for the background at world row y."""
    if y >= GROUND_Y:
        return "ground"
    if y < KARMAN:
        return "space"
    t = (y - KARMAN) / float(GROUND_Y - KARMAN)
    return ATMO_BANDS[min(len(ATMO_BANDS) - 1, int(t * len(ATMO_BANDS)))]


# ---------------------------------------------------------------- ground features
# Rows are bottom-aligned to the row just above the ground line.  Legend for
# special cells: 'o' lit window, 'r' red beacon, '~' glowing screen, ':' corn.
BASE = (
    "     ▄▄▄▄▄▄▄▄     ",
    "    ██o▐▌▐▌o██    ",
    "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
)
HOUSE = (
    " ▄▄▄ ",
    "▐o█o▌",
)
CHURCH = (
    "   ▲   ",
    "   █   ",
    " ▄███▄ ",
    " ██o██ ",
)
DINER = (
    "▄▄▄▄▄▄▄▄▄▄",
    "█o██o██o██",
    "██████████",
)
GAS = (
    "▄▄▄▄▄▄▄▄▄",
    "▌  ▐o█  ▐",
    "▌  ▐██  ▐",
)
CORN = (
    "::::::::::::::",
)
CORN_SMALL = (
    "::::::::",
)
FARM = (
    "        ▄▄  ",
    "  ▄▄▄▄  ██  ",
    " ██o███ ██  ",
    " ██████ ██  ",
)
TOWER_WATER = (
    " ▄███▄ ",
    " ▀███▀ ",
    "  ▌ ▐  ",
    "  ▌ ▐  ",
)
TOWER_RADIO = (
    "  r  ",
    "  █  ",
    " ▐█▌ ",
    " ▐█▌ ",
    "▐███▌",
)
TRAILERS = (
    "▄▄▄▄  ▄▄▄▄ ",
    "█o██  █o██ ",
)
DRIVE_IN = (
    "████████",
    "██~~~~██",
    "   ▌▐   ",
)
MOTEL = (
    "▄▄▄▄▄▄▄▄▄▄▄▄",
    "█o█o█o█o█o██",
)
HILL = (
    "  ▄██▄  ",
    " ██████ ",
)

# (x, sprite, colour, place name shown on the radio)
FEATURES = [
    (10, BASE, "pad", "Nightwatch Base"),
    (40, HOUSE, "silhouette", "Elm Street"),
    (47, HOUSE, "silhouette", "Elm Street"),
    (54, HOUSE, "silhouette", "Elm Street"),
    (70, CHURCH, "silhouette", "the church"),
    (90, DINER, "silhouette", "Route 9 Diner"),
    (110, GAS, "silhouette", "Gus's Garage"),
    (130, CORN, "corn", "the cornfields"),
    (150, FARM, "silhouette", "Miller Farm"),
    (170, CORN, "corn", "the cornfields"),
    (190, TOWER_WATER, "silhouette", "the water tower"),
    (205, TOWER_RADIO, "silhouette", "the KRUX tower"),
    (220, TRAILERS, "silhouette", "the trailer park"),
    (240, DRIVE_IN, "silhouette", "the Drive-In"),
    (260, MOTEL, "silhouette", "the motel"),
    (280, HILL, "hill", "Lookout Hill"),
    (295, HOUSE, "silhouette", "Orchard Road"),
    (302, HOUSE, "silhouette", "Orchard Road"),
    (311, CORN_SMALL, "corn", "the cornfields"),
]

BASE_X = 10
BASE_W = len(BASE[0])
BASE_PAD = (BASE_X, BASE_X + BASE_W)     # landing here repairs the ship

# (name, home x)
TOWNSFOLK = [
    ("Mrs. Henderson", 44),
    ("Mr. Henderson", 51),
    ("Deputy Ray", 62),
    ("Pastor Dale", 75),
    ("Flo", 96),
    ("Gus", 116),
    ("Farmer Miller", 156),
    ("Bobby Miller", 163),
    ("DJ Randy", 209),
    ("Nurse Kim", 266),
]


def place_name(x):
    """Nearest ground feature's name, for radio chatter."""
    best, bd = "town", WORLD_W
    for fx, rows, _c, name in FEATURES:
        cx = fx + len(rows[0]) / 2.0
        d = abs((x - cx + WORLD_W / 2) % WORLD_W - WORLD_W / 2)
        if d < bd:
            best, bd = name, d
    return best


class World:
    def __init__(self):
        rng = random.Random(STAR_SEED)
        self.stars = {}          # row -> list of (x, char, palette name)
        for _ in range(300):
            x, y = rng.randrange(WORLD_W), rng.randrange(0, KARMAN)
            ch = rng.choice("··∙·+·")
            self.stars.setdefault(y, []).append((x, ch, "star" if rng.random() < 0.4 else "star_dim"))
        for _ in range(90):
            x, y = rng.randrange(WORLD_W), rng.randrange(KARMAN, KARMAN + 18)
            self.stars.setdefault(y, []).append((x, "·", "star_dim"))
        self.moon = (212, 9)     # x, y of a moon drifting past in orbit

    def feature_rows(self):
        """Yield (x, y_top, rows, colour) for every ground feature."""
        for fx, rows, colour, _name in FEATURES:
            yield fx, GROUND_Y - len(rows), rows, colour
