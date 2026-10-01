"""Game loop, input, flight physics, invader AI, waves, collisions and scoring."""
import curses
import json
import math
import os
import random
import time
from collections import deque

from .constants import (
    FPS, TICK, VIEW_COLS, PLAY_ROWS, WORLD_W, WORLD_H, KARMAN, GROUND_Y, MOTHER_Y,
    MOTHER_BOSS_Y, LOST_Y, DELIVER_Y, SHIP_LAND_Y, PERSON_Y, LANDER_HOVER_Y,
    GRAVITY, DRAG, IMPULSE_X_ATMO, IMPULSE_Y_ATMO, MAX_VX_ATMO, MAX_VY_ATMO,
    IMPULSE_X_SPACE, IMPULSE_Y_SPACE, MAX_VX_SPACE, MAX_VY_SPACE, CRASH_VY, FALL_KILL_ROWS,
    BOLT_SPEED, BOLT_LIFE, FIRE_COOLDOWN, ESHOT_LIFE,
    START_LIVES, START_BOMBS, MAX_BOMBS, MAX_SHIELD, EXTRA_LIFE_EVERY, HUNTER_AFTER,
    RESPAWN_TICKS, BANNER_TICKS, SCORE, MOTHER_CORE,
    RADIO_SIGHTING, RADIO_TAKEN, RADIO_SAVED, RADIO_CATCH, RADIO_DROPPED, RADIO_SPACE,
    RADIO_REENTRY, RADIO_BOSS, RADIO_HUNTER, RADIO_WAVE, RADIO_IDLE, BOOM_CHARS,
)
from .world import World, TOWNSFOLK, BASE_PAD, place_name
from .entities import (
    Ship, Person, Lander, Scout, Drone, Hunter, Mothership, Shot, Particle,
    wrap, dxw, sign, clamp, overlap,
)

HIGH_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "highscore.json")

KEYS_UP = (curses.KEY_UP, ord("w"), ord("W"), ord("k"), ord("K"))
KEYS_DOWN = (curses.KEY_DOWN, ord("s"), ord("S"), ord("j"), ord("J"))
KEYS_LEFT = (curses.KEY_LEFT, ord("a"), ord("A"), ord("h"), ord("H"))
KEYS_RIGHT = (curses.KEY_RIGHT, ord("d"), ord("D"), ord("l"), ord("L"))
KEYS_FIRE = (ord(" "), ord("f"), ord("F"))
KEYS_BOMB = (ord("b"), ord("B"))
ESC = 27


class Game:
    def __init__(self, stdscr, renderer=None):
        self.stdscr = stdscr
        if renderer is None:
            from .render import Renderer
            renderer = Renderer(stdscr)
        self.r = renderer
        self.rng = random.Random()
        self.world = World()
        self.high = self.load_high()
        self.running = True
        self.mode = "title"
        self.prev_mode = "title"
        self.tick = 0
        self.title_t = 0
        self.messages = deque(maxlen=2)
        self.msg_expire = 0
        self.cam_x = 0.0
        self.cam_y = float(WORLD_H - PLAY_ROWS)
        self.reset_state()

    # ------------------------------------------------------------ setup
    def reset_state(self):
        self.score = 0
        self.lives = START_LIVES
        self.bombs = START_BOMBS
        self.wave = 0
        self.next_life = EXTRA_LIFE_EVERY
        self.people = [Person(n, x) for n, x in TOWNSFOLK]
        self.mother = Mothership(160)
        self.ship = Ship(BASE_PAD[0] + 5, SHIP_LAND_Y)
        self.landers = []
        self.scouts = []
        self.drones = []
        self.hunters = []
        self.shots = []
        self.particles = []
        self.lander_quota = 0
        self.lander_spawned = 0
        self.spawn_t = 0
        self.wave_t = 0
        self.hunter_t = 0
        self.banner_t = 0
        self.banner = ""
        self.dead_t = 0
        self.idle_t = FPS * 12
        self.boss_wave = False
        self.boss_done = False
        self.mother_respawn = 0
        self.cam_x = float(self.ship.x - VIEW_COLS // 3)
        self.cam_y = float(WORLD_H - PLAY_ROWS)
        self.messages.clear()

    def load_high(self):
        try:
            with open(HIGH_PATH) as f:
                return int(json.load(f).get("high", 0))
        except (OSError, ValueError):
            return 0

    def save_high(self):
        if self.score > self.high:
            self.high = self.score
        try:
            with open(HIGH_PATH, "w") as f:
                json.dump({"high": self.high}, f)
        except OSError:
            pass

    @property
    def cam_xi(self):
        return int(self.cam_x) % WORLD_W

    @property
    def cam_yi(self):
        return int(self.cam_y)

    # ------------------------------------------------------------ messages
    def say(self, text, kind="msg", secs=5):
        self.messages.append((text, kind))
        self.msg_expire = self.tick + int(secs * FPS)
        self.idle_t = FPS * 15

    def radio(self, lines, kind="msg", **kw):
        self.say(self.rng.choice(lines).format(**kw), kind)

    def people_alive(self):
        return [p for p in self.people if not p.gone()]

    # ------------------------------------------------------------ main loop
    def run(self):
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        next_t = time.time()
        while self.running:
            self.handle_input()
            self.step()
            self.r.draw(self)
            next_t += TICK
            delay = next_t - time.time()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.time()

    def step(self):
        """One simulation tick (also used headless by the tests)."""
        self.tick += 1
        if self.mode == "title":
            self.title_t += 1
        elif self.mode in ("play", "dead", "clear"):
            self.update()
        if self.messages and self.tick > self.msg_expire:
            self.messages.clear()

    def handle_input(self):
        while True:
            k = self.stdscr.getch()
            if k == -1:
                break
            if k == curses.KEY_RESIZE:
                continue
            getattr(self, "keys_" + self.mode)(k)

    # ------------------------------------------------------------ key handlers
    def keys_title(self, k):
        if k in (ord("n"), ord("N"), 10, 13, ord(" ")):
            self.start_new()
        elif k == ord("?"):
            self.prev_mode = "title"
            self.mode = "help"
        elif k in (ord("q"), ord("Q"), ESC):
            self.running = False

    def keys_help(self, k):
        if k != -1:
            self.mode = self.prev_mode

    def keys_pause(self, k):
        if k in (ord("p"), ord("P"), ESC, ord(" ")):
            self.mode = "play"
        elif k in (ord("q"), ord("Q")):
            self.mode = "quit"
        elif k == ord("?"):
            self.prev_mode = "pause"
            self.mode = "help"

    def keys_quit(self, k):
        if k in (ord("y"), ord("Y")):
            self.save_high()
            self.running = False
        elif k != -1:
            self.mode = "play"

    def keys_gameover(self, k):
        if k in (ord("n"), ord("N"), 10, 13, ord(" ")):
            self.start_new()
        elif k in (ord("q"), ord("Q"), ESC):
            self.running = False

    def keys_dead(self, k):
        pass

    def keys_clear(self, k):
        self.keys_play(k)

    def keys_play(self, k):
        s = self.ship
        space = s.in_space()
        if k in KEYS_UP:
            s.vy -= IMPULSE_Y_SPACE if space else IMPULSE_Y_ATMO
            s.landed = False
            s.thrust_ticks, s.thrust_dir = 5, (0, -1)
        elif k in KEYS_DOWN:
            if not s.landed:
                s.vy += IMPULSE_Y_SPACE if space else IMPULSE_Y_ATMO
                s.thrust_ticks, s.thrust_dir = 5, (0, 1)
        elif k in KEYS_LEFT:
            s.facing = -1
            s.vx -= IMPULSE_X_SPACE if space else IMPULSE_X_ATMO
            s.thrust_ticks, s.thrust_dir = 5, (-1, 0)
        elif k in KEYS_RIGHT:
            s.facing = 1
            s.vx += IMPULSE_X_SPACE if space else IMPULSE_X_ATMO
            s.thrust_ticks, s.thrust_dir = 5, (1, 0)
        elif k in KEYS_FIRE:
            self.fire()
        elif k in KEYS_BOMB:
            self.smart_bomb()
        elif k in (ord("p"), ord("P")):
            self.mode = "pause"
        elif k == ord("?"):
            self.prev_mode = "play"
            self.mode = "help"
        elif k in (ord("q"), ord("Q"), ESC):
            self.mode = "quit"

    # ------------------------------------------------------------ game flow
    def start_new(self):
        self.reset_state()
        self.mode = "play"
        self.say("Base: Interceptor, you are cleared for launch. Save the town.", "msg_good", 6)
        self.start_wave(1)

    def start_wave(self, n):
        self.wave = n
        self.boss_wave = n % 3 == 0
        self.boss_done = False
        self.lander_quota = min(3 + n, 12)
        self.lander_spawned = 0
        self.spawn_t = BANNER_TICKS + 20
        self.wave_t = 0
        self.hunter_t = HUNTER_AFTER
        self.bombs = min(MAX_BOMBS, self.bombs + 1)
        self.banner_t = BANNER_TICKS
        self.banner = "WAVE %d" % n
        self.mode = "play"
        # scouts patrol the atmosphere, drones lurk in orbit
        for _ in range(min(1 + n // 2, 5)):
            x = self.rng.randrange(WORLD_W)
            if abs(dxw(x, self.ship.x)) < 50:
                x = wrap(x + 120)
            self.scouts.append(Scout(x, self.rng.randint(KARMAN + 6, GROUND_Y - 14)))
        if n >= 2:
            for _ in range(min(n // 2, 4)):
                self.drones.append(Drone(self.rng.randrange(WORLD_W), self.rng.randint(6, KARMAN - 5)))
        if n > 1:
            self.radio(RADIO_WAVE, "msg_alert")

    def wave_cleared(self):
        alive = len(self.people_alive())
        bonus = 100 * self.wave * alive
        self.add_score(bonus)
        self.banner = "WAVE %d CLEAR" % self.wave
        self.banner_t = BANNER_TICKS
        self.mode = "clear"
        self.wave_t = 0
        self.say("Base: Wave clear. %d townsfolk safe, bonus %d." % (alive, bonus), "msg_good", 4)
        for e in self.scouts + self.drones + self.hunters:
            self.explode(e.cx(), e.cy(), 4, e.in_space())
        self.scouts, self.drones, self.hunters = [], [], []
        self.shots = [s for s in self.shots if s.owner == "p"]

    def add_score(self, n):
        self.score += n
        if self.score >= self.next_life:
            self.next_life += EXTRA_LIFE_EVERY
            self.lives += 1
            self.say("Base: Reserve interceptor released to you. Extra ship!", "msg_good")

    def game_over(self, why):
        self.mode = "gameover"
        self.banner = why
        self.save_high()

    # ------------------------------------------------------------ player actions
    def fire(self):
        s = self.ship
        if s.cool > 0 or self.mode != "play":
            return
        s.cool = FIRE_COOLDOWN
        if s.facing > 0:
            x = s.x + s.w
        else:
            x = s.x - 2
        self.shots.append(Shot(x, s.y, s.facing * BOLT_SPEED + s.vx * 0.5, 0.0, "p", BOLT_LIFE))

    def smart_bomb(self):
        if self.bombs <= 0 or self.mode != "play":
            self.say("Base: No smart bombs left, Interceptor.", "msg_alert", 2)
            return
        self.bombs -= 1
        self.r.flash()
        hit = 0
        for group, key in ((self.landers, "lander"), (self.scouts, "scout"),
                           (self.drones, "drone"), (self.hunters, "hunter")):
            for e in list(group):
                if self.on_screen(e):
                    self.kill_enemy(e, group, key)
                    hit += 1
        self.shots = [sh for sh in self.shots if sh.owner == "p" or not self.on_screen(sh)]
        self.say("SMART BOMB! %d invaders down." % hit, "msg_good", 3)

    def on_screen(self, b):
        dx = (int(b.x) - self.cam_xi) % WORLD_W
        if not (dx < VIEW_COLS + b.w or dx > WORLD_W - b.w):
            return False
        return self.cam_yi - b.h < b.y < self.cam_yi + PLAY_ROWS

    # ------------------------------------------------------------ update
    def update(self):
        self.wave_t += 1
        if self.banner_t > 0:
            self.banner_t -= 1
        if self.mode == "clear":
            if self.banner_t <= 0:
                self.start_wave(self.wave + 1)
            self.update_camera()
            self.update_particles()
            return

        if self.mode == "dead":
            self.dead_t -= 1
            if self.dead_t <= 0:
                self.respawn()
        else:
            self.update_ship()

        self.update_mother()
        self.update_spawns()
        for ld in list(self.landers):
            self.update_lander(ld)
        for sc in list(self.scouts):
            self.update_scout(sc)
        for dr in list(self.drones):
            self.update_drone(dr)
        for hu in list(self.hunters):
            self.update_hunter(hu)
        for p in self.people:
            self.update_person(p)
        self.update_shots()
        self.update_particles()
        if self.mode == "play":
            self.collisions()
        self.update_camera()
        self.check_wave_end()
        self.idle_chatter()

    def update_camera(self):
        s = self.ship
        target_x = s.x + s.w / 2.0 + s.facing * 10 - VIEW_COLS / 2.0
        self.cam_x = self.cam_x + dxw(self.cam_x, target_x) * 0.12
        self.cam_x %= WORLD_W
        target_y = clamp(s.y - PLAY_ROWS / 2.0 + 1, 0, WORLD_H - PLAY_ROWS)
        self.cam_y += (target_y - self.cam_y) * 0.18
        self.cam_y = clamp(self.cam_y, 0, WORLD_H - PLAY_ROWS)

    # ------------------------------------------------------------ the ship
    def update_ship(self):
        s = self.ship
        if s.cool > 0:
            s.cool -= 1
        if s.invuln > 0:
            s.invuln -= 1
        if s.thrust_ticks > 0:
            s.thrust_ticks -= 1
        space = s.in_space()
        if space:
            s.vx = clamp(s.vx, -MAX_VX_SPACE, MAX_VX_SPACE)
            s.vy = clamp(s.vy, -MAX_VY_SPACE, MAX_VY_SPACE)
        else:
            if not s.landed:
                s.vy += GRAVITY
            s.vx -= s.vx * DRAG
            s.vy -= s.vy * DRAG
            s.vx = clamp(s.vx, -MAX_VX_ATMO, MAX_VX_ATMO)
            s.vy = clamp(s.vy, -MAX_VY_ATMO, MAX_VY_ATMO)
        if s.landed:
            s.vx *= 0.85
            if abs(s.vx) < 0.02:
                s.vx = 0.0
            if s.vy > 0:
                s.vy = 0.0
        s.x = wrap(s.x + s.vx)
        s.y += s.vy
        if s.y < 1:
            s.y = 1.0
            s.vy = max(0.0, s.vy)
        # touching down
        if s.y >= SHIP_LAND_Y:
            if not s.landed and s.vy > CRASH_VY:
                self.kill_ship("Base: Interceptor down! You came in too hot.")
                return
            s.y = float(SHIP_LAND_Y)
            s.vy = 0.0
            if not s.landed:
                s.landed = True
                if s.carrying is not None:
                    self.deliver()
        if s.landed and BASE_PAD[0] - 4 <= s.x <= BASE_PAD[1] - 3 and s.shield < MAX_SHIELD:
            if self.tick % 20 == 0:
                s.shield += 1
                if s.shield == MAX_SHIELD:
                    self.say("Base: Shields at full. Get back up there.", "msg_good", 3)
        # low, slow drop-off without a full landing
        if s.carrying is not None and s.y >= DELIVER_Y and abs(s.vy) < 0.15 and abs(s.vx) < 0.5:
            self.deliver()
        if s.carrying is not None:
            s.carrying.x = wrap(s.x + 3)
            s.carrying.y = s.y + 2
        # regime change chatter
        space = s.in_space()
        if space != s.was_space:
            s.was_space = space
            self.radio(RADIO_SPACE if space else RADIO_REENTRY, "msg")
            if space:
                self.r.flash()

    def deliver(self):
        p = self.ship.carrying
        self.ship.carrying = None
        p.state = "ground"
        p.x = wrap(self.ship.x + 3)
        p.y = float(PERSON_Y)
        p.vx = p.vy = 0.0
        p.pod = False
        p.panic = 0
        self.add_score(SCORE["deliver"])
        self.radio(RADIO_SAVED, "msg_good", name=p.name)

    def kill_ship(self, why):
        s = self.ship
        self.explode(s.cx(), s.cy(), 26, s.in_space())
        self.r.flash()
        if s.carrying is not None:
            self.drop_person(s.carrying, s.vx, s.vy)
            s.carrying = None
        self.mode = "dead"
        self.dead_t = RESPAWN_TICKS
        self.say(why, "msg_alert", 4)

    def respawn(self):
        self.lives -= 1
        if self.lives < 0:
            self.game_over("GAME OVER")
            return
        s = self.ship
        s.x, s.y = float(BASE_PAD[0] + 5), float(SHIP_LAND_Y)
        s.vx = s.vy = 0.0
        s.facing = 1
        s.shield = MAX_SHIELD
        s.invuln = 90
        s.landed = True
        s.was_space = False
        s.carrying = None
        self.mode = "play"
        self.cam_y = float(WORLD_H - PLAY_ROWS)

    def hurt_ship(self):
        s = self.ship
        if s.invuln > 0 or self.mode != "play":
            return
        s.shield -= 1
        s.invuln = 24
        if s.shield <= 0:
            self.kill_ship("Base: We lost the Interceptor! Rolling out a spare...")
        else:
            self.r.flash()

    # ------------------------------------------------------------ townsfolk
    def update_person(self, p):
        if p.state == "ground":
            p.walk_t -= 1
            near = None
            for ld in self.landers:
                if abs(dxw(ld.cx(), p.x)) < 16 and ld.y > KARMAN + 10:
                    near = ld
            if near is not None:
                p.panic = 20
            if p.panic > 0:
                p.panic -= 1
                # they run, but not far and not fast: nowhere to hide in Cedar Hollow
                if near is not None and self.tick % 4 == 0 and abs(dxw(p.home, p.x)) < 18:
                    away = sign(dxw(p.x, near.cx())) or 1
                    p.x = wrap(p.x - away)
            elif p.walk_t <= 0:
                p.walk_t = self.rng.randint(4, 14)
                if self.rng.random() < 0.15:
                    p.dir = -p.dir
                nx = p.x + p.dir
                if abs(dxw(p.home, nx)) > 12:
                    p.dir = -p.dir
                else:
                    p.x = wrap(nx)
        elif p.state == "falling":
            p.vy += GRAVITY * 1.3
            p.vy = min(p.vy, 0.7)
            p.x = wrap(p.x + p.vx)
            p.vx *= 0.97
            p.y += p.vy
            if p.y >= PERSON_Y:
                p.y = float(PERSON_Y)
                p.vx = p.vy = 0.0
                if p.pod or p.fall_from is None or PERSON_Y - p.fall_from <= FALL_KILL_ROWS:
                    p.state = "ground"
                    p.pod = False
                    self.say("%s hit the dirt and got up. Lucky." % p.name, "msg_good", 3)
                else:
                    p.state = "dead"
                    self.explode(p.x, p.y + 1, 5, False)
                    self.radio(RADIO_DROPPED, "msg_alert", name=p.name)
                    self.check_town_empty()
        elif p.state == "drifting":
            p.x = wrap(p.x + p.vx)
            p.y += p.vy
            if p.y < LOST_Y:
                p.state = "lost"
                self.say("Base: %s drifted into the mothership's field. Gone." % p.name, "msg_alert")
                self.check_town_empty()
            elif p.y >= KARMAN:
                p.state = "falling"
                p.fall_from = p.y
                p.vy = max(p.vy, 0.05)

    def drop_person(self, p, vx, vy):
        """A carrier (lander or the ship) let go of someone."""
        if p.in_space():
            p.state = "drifting"
            p.vx = vx * 0.6
            p.vy = vy * 0.6 if abs(vy) > 0.02 else 0.03
        else:
            p.state = "falling"
            p.fall_from = p.y
            p.vx, p.vy = vx * 0.6, max(0.0, vy)

    def check_town_empty(self):
        if not self.people_alive():
            self.game_over("THE TOWN IS EMPTY")

    # ------------------------------------------------------------ invaders
    def update_mother(self):
        m = self.mother
        if m.state == "dead":
            self.mother_respawn -= 1
            if self.mother_respawn <= 0:
                self.mother = Mothership(wrap(self.ship.x + 160))
                self.say("KRUX: ...another one. A second mothership just made orbit.", "msg_alert")
            return
        m.phase += 0.01
        m.vx = 0.12 * math.sin(m.phase)
        m.x = wrap(m.x + m.vx)
        if m.flash > 0:
            m.flash -= 1
        if m.state == "boss":
            if m.y < MOTHER_BOSS_Y:
                m.y = min(MOTHER_BOSS_Y, m.y + 0.05)
            m.hatch_t -= 1
            if m.hatch_t <= 0:
                m.hatch_open = not m.hatch_open
                m.hatch_t = 100 if m.hatch_open else 110
            m.cool -= 1
            if m.cool <= 0 and self.ship.in_space() and self.mode == "play":
                m.cool = 75
                cx, cy = m.cx(), m.y + m.h
                for spread in (-0.35, 0.0, 0.35):
                    dx = dxw(cx, self.ship.cx())
                    dy = self.ship.cy() - cy
                    d = max(1.0, math.hypot(dx, dy))
                    self.shots.append(Shot(cx, cy, dx / d * 0.5 + spread, dy / d * 0.5, "e", ESHOT_LIFE, "plasma"))
        else:
            m.y = float(MOTHER_Y)

    def update_spawns(self):
        m = self.mother
        if self.banner_t > 0 or m.state == "dead":
            return
        self.spawn_t -= 1
        if self.lander_spawned < self.lander_quota and len(self.landers) < 4 and self.spawn_t <= 0:
            self.spawn_t = max(45, 130 - self.wave * 8)
            self.lander_spawned += 1
            ld = Lander(wrap(m.x + 5), m.y + m.h)
            ld.speed = min(0.62, 0.42 + self.wave * 0.02)
            self.landers.append(ld)
        # boss phase: slow trickle of reinforcements
        if m.state == "boss" and self.spawn_t <= 0 and len(self.landers) < 2:
            self.spawn_t = 300
            self.landers.append(Lander(wrap(m.x + 5), m.y + m.h))
        self.hunter_t -= 1
        if self.hunter_t <= 0 and not self.hunters:
            self.hunter_t = 30 * FPS
            self.hunters.append(Hunter(wrap(self.ship.x + 100), clamp(self.ship.y, 3, GROUND_Y - 8)))
            self.radio(RADIO_HUNTER, "msg_alert")

    def pick_target(self):
        ground = [p for p in self.people if p.state == "ground"]
        taken = {ld.target for ld in self.landers if ld.target is not None}
        free = [p for p in ground if p not in taken] or ground
        return self.rng.choice(free) if free else None

    def update_lander(self, ld):
        ld.phase += 0.08
        if ld.cool > 0:
            ld.cool -= 1
        if ld.state == "seek":
            if ld.target is None or ld.target.state != "ground":
                ld.target = self.pick_target()
                if ld.target is None:
                    ld.state = "roam"
                    return
                if ld.y < KARMAN + 4 and self.rng.random() < 0.5:
                    self.radio(RADIO_SIGHTING, "msg", place=place_name(ld.target.x))
            dx = dxw(ld.cx(), ld.target.x + 0.5)
            ld.vx = clamp(dx * 0.08, -ld.speed, ld.speed)
            ld.vy = 0.22 if ld.y < LANDER_HOVER_Y else 0.0
            if ld.y >= LANDER_HOVER_Y:
                ld.y = float(LANDER_HOVER_Y)
            if abs(dx) < 1.6 and ld.y >= LANDER_HOVER_Y - 0.5:
                ld.state = "beam"
                ld.victim = ld.target
                ld.victim.state = "beamed"
                ld.vx = 0.0
        elif ld.state == "beam":
            v = ld.victim
            v.x = wrap(int(ld.cx()))
            v.y -= 0.07
            ld.vx = ld.vy = 0.0
            if v.y <= ld.y + ld.h:
                ld.state = "carry"
                v.state = "carried"
                self.say("Sheriff: They've got %s! Shoot it, then catch them!" % v.name, "msg_alert", 4)
        elif ld.state == "carry":
            v = ld.victim
            ld.vy = -(0.16 + self.wave * 0.01)
            ld.vx = 0.25 * math.sin(ld.phase * 0.5)
            v.x = wrap(int(ld.x) + 2)
            v.y = ld.y + ld.h
            if ld.y <= LOST_Y:
                v.state = "lost"
                ld.alive = False
                self.landers.remove(ld)
                self.radio(RADIO_TAKEN, "msg_alert", name=v.name)
                self.check_town_empty()
                return
        elif ld.state == "roam":
            if any(p.state == "ground" for p in self.people):
                ld.state = "seek"
            dx = dxw(ld.cx(), self.ship.cx())
            ld.vx = clamp(ld.vx + sign(dx) * 0.01, -ld.speed, ld.speed)
            want_y = KARMAN + 10 + 6 * math.sin(ld.phase * 0.3)
            ld.vy = clamp((want_y - ld.y) * 0.05, -0.2, 0.2)
        ld.x = wrap(ld.x + ld.vx)
        ld.y += ld.vy
        # take a pot shot at the interceptor
        if ld.cool <= 0 and self.mode == "play" and abs(dxw(ld.cx(), self.ship.cx())) < 34 and abs(ld.y - self.ship.y) < 14:
            ld.cool = self.rng.randint(90, 160) - self.wave * 4
            self.enemy_shot(ld.cx(), ld.cy() + 1, 0.45)

    def enemy_shot(self, x, y, speed, kind="eshot"):
        dx = dxw(x, self.ship.cx())
        dy = self.ship.cy() - y
        d = max(1.0, math.hypot(dx, dy))
        self.shots.append(Shot(x, y, dx / d * speed, dy / d * speed, "e", ESHOT_LIFE, kind))

    def update_scout(self, sc):
        s = self.ship
        if sc.cool > 0:
            sc.cool -= 1
        dx = dxw(sc.cx(), s.cx())
        if sc.state == "patrol":
            sc.vy = clamp((sc.alt - sc.y) * 0.05, -0.2, 0.2)
            if abs(dx) < 36 and not s.in_space() and self.mode == "play":
                sc.state = "dive"
        else:
            if abs(dx) > 70 or s.in_space():
                sc.state = "patrol"
                sc.alt = self.rng.randint(KARMAN + 6, GROUND_Y - 14)
            sc.vx = clamp(sc.vx + sign(dx) * 0.03, -0.95, 0.95)
            sc.vy = clamp(sc.vy + sign(s.y - sc.y) * 0.02, -0.35, 0.35)
            if sc.cool <= 0 and abs(dx) < 26 and self.mode == "play":
                sc.cool = 70
                self.enemy_shot(sc.cx(), sc.y, 0.6)
        sc.x = wrap(sc.x + sc.vx)
        sc.y += sc.vy
        if sc.y < KARMAN + 2:            # scouts can't fly in vacuum
            sc.y = float(KARMAN + 2)
            sc.vy = abs(sc.vy)
        if sc.y > GROUND_Y - 6:
            sc.y = float(GROUND_Y - 6)
            sc.vy = -abs(sc.vy)

    def update_drone(self, dr):
        s = self.ship
        if dr.cool > 0:
            dr.cool -= 1
        if s.in_space() and self.mode == "play":
            dx = dxw(dr.cx(), s.cx())
            dy = s.cy() - dr.cy()
            d = max(1.0, math.hypot(dx, dy))
            dr.vx = clamp(dr.vx + dx / d * 0.018, -0.75, 0.75)
            dr.vy = clamp(dr.vy + dy / d * 0.012, -0.4, 0.4)
            if dr.cool <= 0 and d < 30:
                dr.cool = self.rng.randint(100, 170)
                self.enemy_shot(dr.cx(), dr.cy(), 0.5)
        dr.x = wrap(dr.x + dr.vx)
        dr.y += dr.vy
        if dr.y < LOST_Y:
            dr.y = float(LOST_Y)
            dr.vy = abs(dr.vy)
        if dr.y > KARMAN - 3:            # drones burn up if they dip into the air
            dr.y = float(KARMAN - 3)
            dr.vy = -abs(dr.vy)

    def update_hunter(self, hu):
        s = self.ship
        if hu.cool > 0:
            hu.cool -= 1
        dx = dxw(hu.cx(), s.cx())
        dy = s.cy() - hu.cy()
        hu.vx = clamp(hu.vx + sign(dx) * 0.05, -1.05, 1.05)
        hu.vy = clamp(hu.vy + sign(dy) * 0.03, -0.45, 0.45)
        hu.x = wrap(hu.x + hu.vx)
        hu.y = clamp(hu.y + hu.vy, 3, GROUND_Y - 5)
        if hu.cool <= 0 and abs(dx) < 40 and self.mode == "play":
            hu.cool = 45
            self.enemy_shot(hu.cx(), hu.cy(), 0.7)

    def kill_enemy(self, e, group, key):
        if e in group:
            group.remove(e)
        e.alive = False
        self.explode(e.cx(), e.cy(), 8, e.in_space())
        self.add_score(SCORE[key])
        if key == "lander" and e.victim is not None and e.victim.state in ("beamed", "carried"):
            self.drop_person(e.victim, e.vx, e.vy)
            e.victim = None

    # ------------------------------------------------------------ projectiles
    def update_shots(self):
        for sh in list(self.shots):
            sh.life -= 1
            sh.x = wrap(sh.x + sh.vx)
            sh.y += sh.vy
            if sh.life <= 0 or sh.y < 0 or sh.y >= GROUND_Y:
                self.shots.remove(sh)

    def update_particles(self):
        for pt in list(self.particles):
            pt.life -= 1
            if pt.life <= 0:
                self.particles.remove(pt)
                continue
            if not pt.in_space():
                pt.vy += GRAVITY * 0.5
            pt.x = wrap(pt.x + pt.vx)
            pt.y += pt.vy
            if pt.y >= GROUND_Y:
                self.particles.remove(pt)

    def explode(self, x, y, n, in_space):
        for _ in range(n):
            a = self.rng.random() * math.tau
            sp = self.rng.uniform(0.15, 0.7)
            vx, vy = math.cos(a) * sp * 1.8, math.sin(a) * sp * 0.6
            life = self.rng.randint(10, 26) if in_space else self.rng.randint(8, 20)
            self.particles.append(Particle(x, y, vx, vy, life, self.rng.choice(BOOM_CHARS)))

    # ------------------------------------------------------------ collisions
    def collisions(self):
        s = self.ship
        m = self.mother
        # player bolts vs invaders
        for sh in list(self.shots):
            if sh.owner != "p":
                continue
            hit = False
            for group, key in ((self.landers, "lander"), (self.scouts, "scout"),
                               (self.drones, "drone"), (self.hunters, "hunter")):
                for e in group:
                    if overlap(sh, e):
                        self.kill_enemy(e, group, key)
                        hit = True
                        break
                if hit:
                    break
            if not hit and m.state != "dead" and overlap(sh, m):
                slot = m.state == "boss" and m.hatch_open and int(sh.y) == int(m.y) + 1
                if slot:
                    # the hull has split open: bolts fly through the slot unless they find the core
                    if overlap(sh, m.core_body()):
                        hit = True
                        m.hp -= 1
                        m.flash = 6
                        self.explode(sh.x, sh.y, 5, True)
                        if m.hp <= 0:
                            self.destroy_mother()
                        else:
                            self.say("Base: Core hit! %d to go." % m.hp, "msg_good", 2)
                else:
                    hit = True
                    self.explode(sh.x, sh.y, 2, True)
            if hit and sh in self.shots:
                self.shots.remove(sh)
        # enemy shots vs the interceptor
        for sh in list(self.shots):
            if sh.owner == "e" and overlap(sh, s):
                self.shots.remove(sh)
                self.hurt_ship()
                if self.mode != "play":
                    return
        # invaders vs the interceptor
        for group, key in ((self.landers, "lander"), (self.scouts, "scout"),
                           (self.drones, "drone"), (self.hunters, "hunter")):
            for e in list(group):
                if overlap(e, s):
                    self.kill_enemy(e, group, key)
                    if s.invuln <= 0:
                        self.kill_ship("Base: Mid-air collision! Interceptor destroyed.")
                        return
        if m.state != "dead" and overlap(m, s):
            self.kill_ship("Base: You flew into the mothership's hull. Ouch.")
            return
        # catching the fallen
        if s.carrying is None:
            for p in self.people:
                if p.loose() and overlap(p, s):
                    p.state = "rescued"
                    s.carrying = p
                    self.add_score(SCORE["catch"])
                    self.radio(RADIO_CATCH, "msg_good", name=p.name)
                    break

    def destroy_mother(self):
        m = self.mother
        m.state = "dead"
        self.boss_done = True
        self.mother_respawn = 8 * FPS
        for i in range(5):
            self.explode(m.x + 2 + i * 3, m.y + 1, 14, True)
        self.r.flash()
        self.add_score(SCORE["mothership"])
        # escape pods: the last few abductees come back down
        lost = [p for p in self.people if p.state == "lost"][-3:]
        for i, p in enumerate(lost):
            p.state = "drifting"
            p.pod = True
            p.x = wrap(m.x + 3 + i * 4)
            p.y = m.y + m.h + 1
            p.vx, p.vy = 0.0, 0.25
        if lost:
            self.say("Base: MOTHERSHIP DOWN! Escape pods: %s!" % ", ".join(p.name.split()[-1] for p in lost), "msg_good", 6)
        else:
            self.say("Base: MOTHERSHIP DESTROYED! Outstanding, Interceptor!", "msg_good", 6)

    # ------------------------------------------------------------ waves
    def check_wave_end(self):
        if self.mode != "play" or self.banner_t > 0:
            return
        m = self.mother
        landers_done = self.lander_spawned >= self.lander_quota and not self.landers
        if self.boss_wave:
            if self.boss_done:
                if not self.landers:
                    self.wave_cleared()
            elif landers_done and m.state == "orbit":
                m.state = "boss"
                m.hp = m.max_hp = 6 + self.wave // 3 * 2
                m.hatch_t = 60
                m.hatch_open = False
                self.banner = "MOTHERSHIP"
                self.banner_t = BANNER_TICKS
                self.say(RADIO_BOSS[0], "msg_alert", 6)
        elif landers_done:
            self.wave_cleared()

    def idle_chatter(self):
        self.idle_t -= 1
        if self.idle_t <= 0 and not self.messages:
            self.idle_t = FPS * 14
            self.say(self.rng.choice(RADIO_IDLE), "msg", 5)
