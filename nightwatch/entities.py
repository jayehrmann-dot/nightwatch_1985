"""Ship, townsfolk, invaders, shots and explosion particles."""
import math
import random

from .constants import (
    WORLD_W, KARMAN, GROUND_Y, PERSON_Y, MOTHER_Y, MAX_SHIELD,
)


def wrap(x):
    return x % WORLD_W


def dxw(a, b):
    """Shortest signed horizontal distance from a to b on the wrapping world."""
    d = (b - a) % WORLD_W
    if d > WORLD_W / 2.0:
        d -= WORLD_W
    return d


def sign(v):
    return (v > 0) - (v < 0)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class Body:
    w = 1
    h = 1

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.alive = True

    @property
    def ix(self):
        return int(self.x) % WORLD_W

    @property
    def iy(self):
        return int(self.y)

    def cx(self):
        return self.x + self.w / 2.0

    def cy(self):
        return self.y + self.h / 2.0

    def in_space(self):
        return self.y < KARMAN


def overlap(a, b):
    dx = dxw(int(a.x), int(b.x))
    if not (dx < a.w and dx + b.w > 0):
        return False
    ay, by = int(a.y), int(b.y)
    return ay < by + b.h and by < ay + a.h


# ---------------------------------------------------------------- the player
class Ship(Body):
    w, h = 7, 2

    def __init__(self, x, y):
        super().__init__(x, y)
        self.facing = 1
        self.shield = MAX_SHIELD
        self.carrying = None
        self.cool = 0
        self.invuln = 0
        self.thrust_ticks = 0
        self.thrust_dir = (0, 0)
        self.landed = True
        self.was_space = False


# ---------------------------------------------------------------- townsfolk
class Person(Body):
    w, h = 1, 2
    # states: ground, beamed, carried, falling, drifting, rescued, lost, dead

    def __init__(self, name, x):
        super().__init__(x, PERSON_Y)
        self.name = name
        self.home = x
        self.state = "ground"
        self.dir = random.choice((-1, 1))
        self.walk_t = random.randint(0, 20)
        self.panic = 0
        self.fall_from = None
        self.pod = False

    def gone(self):
        return self.state in ("lost", "dead")

    def loose(self):
        return self.state in ("falling", "drifting")


# ---------------------------------------------------------------- invaders
class Lander(Body):
    w, h = 5, 2
    # states: seek, beam, carry, roam

    def __init__(self, x, y):
        super().__init__(x, y)
        self.state = "seek"
        self.target = None
        self.victim = None
        self.cool = random.randint(40, 120)
        self.phase = random.random() * math.tau
        self.speed = 0.42


class Scout(Body):
    w, h = 5, 1

    def __init__(self, x, y):
        super().__init__(x, y)
        self.vx = random.choice((-0.6, 0.6))
        self.state = "patrol"
        self.cool = random.randint(30, 90)
        self.alt = y


class Drone(Body):
    w, h = 3, 2

    def __init__(self, x, y):
        super().__init__(x, y)
        self.vx = random.uniform(-0.3, 0.3)
        self.vy = random.uniform(-0.1, 0.1)
        self.cool = random.randint(60, 150)


class Hunter(Body):
    w, h = 5, 1

    def __init__(self, x, y):
        super().__init__(x, y)
        self.cool = 30


class Mothership(Body):
    w, h = 15, 3
    # states: orbit (invulnerable, drops landers), boss (descends, hatch cycles), dead

    def __init__(self, x):
        super().__init__(x, MOTHER_Y)
        self.state = "orbit"
        self.hp = 8
        self.max_hp = 8
        self.hatch_t = 0
        self.hatch_open = False
        self.flash = 0
        self.cool = 60
        self.phase = 0.0

    def core_body(self):
        b = Body(int(self.x) + 7, int(self.y) + 1)
        return b


# ---------------------------------------------------------------- projectiles
class Shot(Body):
    def __init__(self, x, y, vx, vy, owner, life, kind="bolt"):
        super().__init__(x, y)
        self.vx, self.vy = vx, vy
        self.owner = owner        # "p" player, "e" enemy
        self.life = life
        self.kind = kind          # bolt, eshot, plasma
        self.w = 2 if kind == "bolt" else 1
        self.h = 1


class Particle(Body):
    def __init__(self, x, y, vx, vy, life, ch):
        super().__init__(x, y)
        self.vx, self.vy = vx, vy
        self.life = life
        self.max_life = life
        self.ch = ch
