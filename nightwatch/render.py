"""Curses renderer: HUD, long-range scanner, the scrolling sky, sprites and overlays."""
import curses
import math

from .constants import (
    VIEW_COLS, VIEW_ROWS, HUD_ROWS, SCAN_ROWS, PLAY_ROWS, PLAY_TOP, MSG_TOP,
    WORLD_W, WORLD_H, KARMAN, GROUND_Y, MAX_SHIELD, PALETTE, FONT,
    SHIP_R, SHIP_L, SHIP_CANOPY, LANDER, SCOUT, DRONE, HUNTER, MOTHERSHIP, MOTHER_HATCH,
    MOTHER_CORE, PERSON, PERSON_FALL, BOLT, ESHOT, PLASMA, BEAM, FLAME_ATMO, FLAME_SPACE,
)
from .world import sky_name, BASE_PAD

CONTROLS = [
    "ARROWS / WASD ...... thrust (left/right also turns the ship)",
    "SPACE or F ......... fire the pulse cannon the way you face",
    "B .................. smart bomb, clears the whole screen",
    "P .................. pause          ? ...... this briefing",
    "Q or ESC ........... quit (asks first)",
    "",
    "ATMOSPHERE: gravity pulls you down and drag bleeds off speed.",
    "Climb past the dotted line into ORBIT: zero-G, no drag. You",
    "keep all your momentum up there. Thrust the other way to stop.",
    "",
    "Saucers beam up townsfolk and ferry them to the mothership.",
    "Shoot a saucer mid-abduction and its victim falls. Fly into",
    "them to catch them, then get low and slow (or land) to set",
    "them down. In orbit they drift instead. Grab them before the",
    "mothership does.",
    "",
    "Land gently on the base pad to repair shields. Every third",
    "wave the mothership descends: shoot the core when it opens.",
]


class Renderer:
    def __init__(self, stdscr):
        self.scr = stdscr
        self.pairs = {}
        self.colors_ok = curses.has_colors()
        if self.colors_ok:
            curses.start_color()
            try:
                curses.use_default_colors()
            except curses.error:
                pass
        self.many = self.colors_ok and curses.COLORS >= 256
        self.max_pairs = curses.COLOR_PAIRS if self.colors_ok else 0
        self.oy = self.ox = 0
        self.flash_t = 0

    # ------------------------------------------------------------ colours
    def cidx(self, name):
        full, basic = PALETTE[name]
        return full if self.many else basic

    def attr(self, fg, bg, bold=False):
        if not self.colors_ok:
            return curses.A_BOLD if bold else 0
        key = (self.cidx(fg), self.cidx(bg))
        if key not in self.pairs:
            n = len(self.pairs) + 1
            if n >= self.max_pairs:
                return 0
            try:
                curses.init_pair(n, key[0], key[1])
            except curses.error:
                return 0
            self.pairs[key] = n
        a = curses.color_pair(self.pairs[key])
        return a | curses.A_BOLD if bold else a

    def flash(self):
        self.flash_t = 2

    def put(self, y, x, s, attr=0):
        try:
            self.scr.addstr(y, x, s, attr)
        except curses.error:
            pass

    def fill(self, y0, x0, rows, cols, attr):
        for y in range(y0, y0 + rows):
            self.put(y, x0, " " * cols, attr)

    def center(self, y, text, attr=0):
        self.put(y, self.ox + (VIEW_COLS - len(text)) // 2, text, attr)

    def big(self, y, x, text, attr):
        for i, ch in enumerate(text.upper()):
            glyph = FONT.get(ch, FONT[" "])
            for r, row in enumerate(glyph):
                for c, px in enumerate(row):
                    if px == "█":
                        self.put(y + r, x + i * 4 + c, "█", attr)

    def big_center(self, y, text, attr):
        w = len(text) * 4 - 1
        self.big(y, self.ox + (VIEW_COLS - w) // 2, text, attr)

    # ------------------------------------------------------------ world -> screen
    def blit(self, g, wx, wy, rows, fg, legend=None, bold=False, bg=None):
        """Draw a multi-row sprite at world (wx, wy), wrapping horizontally."""
        cam_x, cam_y = g.cam_xi, g.cam_yi
        wx = int(wx)
        wy = int(wy)
        for r, row in enumerate(rows):
            y = wy + r
            if y < cam_y or y >= cam_y + PLAY_ROWS:
                continue
            sy = self.oy + PLAY_TOP + (y - cam_y)
            row_bg = bg or sky_name(y)
            for c, ch in enumerate(row):
                if ch == " ":
                    continue
                col = (wx + c - cam_x) % WORLD_W
                if col >= VIEW_COLS:
                    continue
                f, b = fg, bold
                if legend and ch in legend:
                    ch, f = legend[ch]
                    if ch is None:
                        continue
                self.put(sy, self.ox + col, ch, self.attr(f, row_bg, b))

    def cell(self, g, wx, wy, ch, fg, bold=False):
        self.blit(g, wx, wy, (ch,), fg, bold=bold)

    # ------------------------------------------------------------ frame
    def draw(self, g):
        self.scr.erase()
        rows, cols = self.scr.getmaxyx()
        if rows < VIEW_ROWS or cols < VIEW_COLS:
            self.put(0, 0, "Nightwatch 1985 needs a terminal of at least %dx%d (you have %dx%d)."
                     % (VIEW_COLS, VIEW_ROWS, cols, rows))
            self.put(1, 0, "Enlarge the window.")
            self.scr.refresh()
            return
        self.oy = (rows - VIEW_ROWS) // 2
        self.ox = (cols - VIEW_COLS) // 2
        if g.mode == "title" or (g.mode == "help" and g.prev_mode == "title"):
            self.draw_title(g)
        else:
            self.draw_hud(g)
            self.draw_scanner(g)
            self.draw_play(g)
            self.draw_messages(g)
        if g.mode == "help":
            self.draw_help()
        elif g.mode == "pause":
            self.overlay(["PAUSED", "", "P to resume   Q to quit   ? for the briefing"])
        elif g.mode == "quit":
            self.overlay(["ABANDON THE TOWN?", "", "Y to quit, any other key to keep flying"])
        elif g.mode == "gameover":
            self.draw_gameover(g)
        if g.banner_t > 0 and g.mode in ("play", "clear") and g.banner:
            self.draw_banner(g)
        if self.flash_t > 0:
            self.flash_t -= 1
            self.fill(self.oy + PLAY_TOP, self.ox, PLAY_ROWS, VIEW_COLS, self.attr("hud", "hud"))
        self.scr.refresh()

    # ------------------------------------------------------------ HUD + scanner
    def draw_hud(self, g):
        y = self.oy
        self.fill(y, self.ox, HUD_ROWS, VIEW_COLS, self.attr("hud", "hud_bg"))
        self.put(y, self.ox + 1, "SCORE", self.attr("hud_dim", "hud_bg"))
        self.put(y, self.ox + 7, "%06d" % g.score, self.attr("hud", "hud_bg", True))
        self.put(y, self.ox + 15, "HI", self.attr("hud_dim", "hud_bg"))
        self.put(y, self.ox + 18, "%06d" % max(g.high, g.score), self.attr("hud_gold", "hud_bg"))
        self.put(y, self.ox + 26, "WAVE", self.attr("hud_dim", "hud_bg"))
        self.put(y, self.ox + 31, "%02d" % g.wave, self.attr("hud", "hud_bg", True))
        ships = "▲" * max(0, g.lives)
        self.put(y, self.ox + 35, "SHIPS", self.attr("hud_dim", "hud_bg"))
        self.put(y, self.ox + 41, ships.ljust(5), self.attr("ship", "hud_bg", True))
        self.put(y, self.ox + 47, "BOMB", self.attr("hud_dim", "hud_bg"))
        self.put(y, self.ox + 52, ("◆" * g.bombs).ljust(5), self.attr("hud_red", "hud_bg", True))
        alive = len(g.people_alive())
        self.put(y, self.ox + 58, "%2d" % alive, self.attr("person", "hud_bg", True))
        self.put(y, self.ox + 60, "ppl", self.attr("hud_dim", "hud_bg"))

    def scan_pos(self, x, y):
        col = int((x % WORLD_W) * VIEW_COLS / WORLD_W)
        if y < KARMAN:
            row = 0
        elif y < KARMAN + 21:
            row = 1
        else:
            row = 2
        return row, col

    def draw_scanner(self, g):
        y0 = self.oy + HUD_ROWS
        self.fill(y0, self.ox, SCAN_ROWS, VIEW_COLS, self.attr("scan_line", "scan"))
        # the viewport
        vc = int(g.cam_xi * VIEW_COLS / WORLD_W)
        vw = max(1, VIEW_COLS * VIEW_COLS // WORLD_W)
        for r in range(SCAN_ROWS):
            for c in range(vw + 1):
                self.put(y0 + r, self.ox + (vc + c) % VIEW_COLS, " ", self.attr("scan_line", "scan_view"))
        # the ground line and karman hint
        for c in range(VIEW_COLS):
            bg = "scan_view" if (c - vc) % VIEW_COLS <= vw else "scan"
            self.put(y0 + 2, self.ox + c, "_", self.attr("grass", bg))

        def mark(x, y, ch, fg, bold=False):
            r, c = self.scan_pos(x, y)
            bg = "scan_view" if (c - vc) % VIEW_COLS <= vw else "scan"
            self.put(y0 + r, self.ox + c, ch, self.attr(fg, bg, bold))

        for p in g.people:
            if p.state == "ground":
                mark(p.x, p.y, ".", "person")
            elif p.state in ("beamed", "carried", "falling", "drifting"):
                mark(p.x, p.y, "!", "panic", True)
        for sc in g.scouts:
            mark(sc.x, sc.y, "▪", "scout")
        for dr in g.drones:
            mark(dr.x, dr.y, "▪", "drone")
        for ld in g.landers:
            mark(ld.x, ld.y, "▪", "lamp" if ld.state in ("beam", "carry") else "lander", True)
        for hu in g.hunters:
            mark(hu.x, hu.y, "▪", "hunter", True)
        m = g.mother
        if m.state != "dead":
            r, c = self.scan_pos(m.x, m.y)
            for i in range(3):
                self.put(y0 + r, self.ox + (c + i) % VIEW_COLS, "▬", self.attr("core" if m.state == "boss" else "mother", "scan", True))
        if g.mode != "dead":
            mark(g.ship.x + 3, g.ship.y, "▲" if g.ship.facing > 0 else "▲", "ship", True)

    # ------------------------------------------------------------ the sky
    def draw_play(self, g):
        cam_x, cam_y = g.cam_xi, g.cam_yi
        top = self.oy + PLAY_TOP
        # sky bands
        for r in range(PLAY_ROWS):
            wy = cam_y + r
            name = sky_name(wy)
            a = self.attr(name, name)
            if wy == GROUND_Y:
                self.put(top + r, self.ox, "▀" * VIEW_COLS, self.attr("grass", "ground"))
            elif wy == KARMAN:
                self.put(top + r, self.ox, "·   " * (VIEW_COLS // 4), self.attr("karman", name))
            else:
                self.put(top + r, self.ox, " " * VIEW_COLS, a)
            for sx, ch, fg in g.world.stars.get(wy, ()):
                col = (sx - cam_x) % WORLD_W
                if col < VIEW_COLS:
                    if ch == "+" and (g.tick // 8 + sx) % 3 == 0:
                        ch = "·"
                    self.put(top + r, self.ox + col, ch, self.attr(fg, name))
        # the moon
        mx, my = g.world.moon
        self.blit(g, mx, my, ("▟██▙", "▜██▛"), "moon")
        # the town
        blink = (g.tick // 12) % 2 == 0
        legend = {
            "o": ("▪", "window"),
            "r": ("●" if blink else "·", "beacon"),
            "~": ("▓", "screen"),
            ":": ("▒", "corn"),
        }
        for fx, fy, rows, colour in g.world.feature_rows():
            self.blit(g, fx, fy, rows, colour, legend=legend)
        # base pad beacons
        for bx in (BASE_PAD[0], BASE_PAD[1] - 1):
            self.cell(g, bx, GROUND_Y - 1, "▲" if blink else "▬", "padlight" if blink else "pad", True)
        # tractor beams
        for ld in g.landers:
            if ld.state == "beam" and ld.victim is not None:
                ch = BEAM[(g.tick // 3) % 2]
                for y in range(int(ld.y) + ld.h, int(ld.victim.y)):
                    self.cell(g, ld.victim.x, y, ch, "beam" if (y + g.tick // 2) % 2 else "beam2", True)
        # townsfolk
        for p in g.people:
            if p.gone():
                continue
            if p.state == "rescued":
                if g.mode == "dead":
                    continue
                self.blit(g, p.x, p.y, PERSON, "person", bold=True)
            elif p.state in ("falling", "drifting"):
                self.blit(g, p.x, p.y, PERSON_FALL, "person", bold=True)
            else:
                self.blit(g, p.x, p.y, PERSON, "person", bold=True)
                if p.panic > 0 and blink:
                    self.cell(g, p.x, p.y - 1, "!", "panic", True)
        # shots
        for sh in g.shots:
            if sh.kind == "bolt":
                self.blit(g, sh.x, sh.y, (BOLT,), "bolt", bold=True)
            elif sh.kind == "plasma":
                self.cell(g, sh.x, sh.y, PLASMA, "plasma", True)
            else:
                self.cell(g, sh.x, sh.y, ESHOT, "eshot", True)
        # invaders
        for sc in g.scouts:
            self.blit(g, sc.x, sc.y, SCOUT, "scout", bold=True)
        for dr in g.drones:
            self.blit(g, dr.x, dr.y, DRONE, "drone", bold=True)
        for hu in g.hunters:
            self.blit(g, hu.x, hu.y, HUNTER, "hunter", bold=True)
        frame = LANDER[(g.tick // 6) % 2]
        for ld in g.landers:
            self.blit(g, ld.x, ld.y, frame, "lander", legend={"▪": ("▪", "lamp")}, bold=True)
        self.draw_mother(g)
        # explosions
        for pt in g.particles:
            t = 1.0 - pt.life / float(pt.max_life)
            fg = "boom%d" % min(4, int(t * 5))
            self.cell(g, pt.x, pt.y, pt.ch, fg, True)
        # the interceptor
        if g.mode != "dead":
            self.draw_ship(g)

    def draw_mother(self, g):
        m = g.mother
        if m.state == "dead":
            return
        rows = list(MOTHERSHIP)
        hr, hc, hw = MOTHER_HATCH
        fg = "core_hit" if m.flash > 0 else "mother"
        legend = {"▓": ("▓", "hatch")}
        if m.state == "boss" and m.hatch_open:
            # the hull splits: the middle row becomes an open slot with the core inside
            rows[hr] = "▝" + " " * (m.w - 2) + "▘"
        self.blit(g, m.x, m.y, rows, fg, legend=legend, bold=True)
        if m.state == "boss" and m.hatch_open:
            cr, cc = MOTHER_CORE
            ch = "◉" if (g.tick // 4) % 2 else "●"
            self.cell(g, m.x + cc, m.y + cr, ch, "core_hit" if m.flash > 0 else "core", True)
            self.cell(g, m.x + cc - 2, m.y + cr, "·", "hatch")
            self.cell(g, m.x + cc + 2, m.y + cr, "·", "hatch")
        if m.state == "boss":
            # health bar over the hull
            bar = int(m.hp * 9 / float(m.max_hp))
            self.blit(g, m.x + 3, m.y - 1, ("▬" * bar,), "core", bold=True)

    def draw_ship(self, g):
        s = g.ship
        if s.invuln > 0 and (g.tick // 3) % 2 == 0 and s.shield > 0:
            return
        rows = SHIP_R if s.facing > 0 else SHIP_L
        canopy = SHIP_CANOPY if s.facing > 0 else {(r, s.w - 1 - c) for r, c in SHIP_CANOPY}
        cam_x, cam_y = g.cam_xi, g.cam_yi
        for r, row in enumerate(rows):
            y = int(s.y) + r
            if y < cam_y or y >= cam_y + PLAY_ROWS:
                continue
            sy = self.oy + PLAY_TOP + (y - cam_y)
            bg = sky_name(y)
            for c, ch in enumerate(row):
                if ch == " ":
                    continue
                col = (int(s.x) + c - cam_x) % WORLD_W
                if col >= VIEW_COLS:
                    continue
                fg = "canopy" if (r, c) in canopy else "ship"
                self.put(sy, self.ox + col, ch, self.attr(fg, bg, True))
        if s.thrust_ticks > 0 and not s.landed:
            flames = FLAME_SPACE if s.in_space() else FLAME_ATMO
            ch = flames[g.tick % len(flames)]
            fg = "flame_space" if s.in_space() else ("flame" if g.tick % 2 else "flame2")
            dx, dy = s.thrust_dir
            if dx != 0:
                fx = s.x - 1 if dx > 0 else s.x + s.w
                self.cell(g, fx, s.y + 1, ch, fg, True)
            elif dy < 0:
                self.cell(g, s.x + 3, s.y + 2, "▲" if s.in_space() else "▴", fg, True)
                self.cell(g, s.x + 4, s.y + 2, "▲" if s.in_space() else "▴", fg, True)
            else:
                self.cell(g, s.x + 3, s.y - 1, "▾", fg, True)

    # ------------------------------------------------------------ messages
    def draw_messages(self, g):
        y = self.oy + MSG_TOP
        self.fill(y, self.ox, 2, VIEW_COLS, self.attr("hud", "hud_bg"))
        if g.messages:
            text, kind = g.messages[-1]
            self.put(y, self.ox + 1, text[:VIEW_COLS - 2], self.attr(kind, "hud_bg", kind != "msg"))
        s = g.ship
        regime = "ORBIT  ZERO-G" if s.in_space() else "ATMOSPHERE"
        if s.landed:
            regime = "LANDED" + ("  REPAIRING" if s.shield < MAX_SHIELD and BASE_PAD[0] - 4 <= s.x <= BASE_PAD[1] - 3 else "")
        self.put(y + 1, self.ox + 1, regime.ljust(22), self.attr("title" if s.in_space() else "hud_dim", "hud_bg", s.in_space()))
        self.put(y + 1, self.ox + 24, "SHIELD", self.attr("hud_dim", "hud_bg"))
        self.put(y + 1, self.ox + 31, ("▮" * s.shield).ljust(MAX_SHIELD), self.attr("shield", "hud_bg", True))
        if s.carrying is not None:
            self.put(y + 1, self.ox + 36, ("CARRYING " + s.carrying.name.upper())[:27], self.attr("person", "hud_bg", True))
        elif g.mode == "play":
            spd = math.hypot(s.vx, s.vy)
            self.put(y + 1, self.ox + 36, "ALT %2d  SPD %.1f" % (GROUND_Y - int(s.y) - 2, spd * 10), self.attr("hud_dim", "hud_bg"))

    # ------------------------------------------------------------ overlays
    def draw_banner(self, g):
        y = self.oy + PLAY_TOP + 4
        text = g.banner
        w = len(text) * 4 + 3
        x = self.ox + (VIEW_COLS - w) // 2
        self.fill(y - 1, x, 7, w, self.attr("panel_fg", "panel"))
        fg = "core" if text == "MOTHERSHIP" else ("title3" if "CLEAR" in text else "title")
        self.big(y, x + 2, text, self.attr(fg, "panel", True))
        if text == "MOTHERSHIP":
            self.center(y + 6, "IT'S COMING DOWN. HIT THE CORE WHEN THE HATCH OPENS.", self.attr("hud", "panel", True))

    def overlay(self, lines):
        w = max(len(l) for l in lines) + 6
        h = len(lines) + 2
        y = self.oy + PLAY_TOP + (PLAY_ROWS - h) // 2
        x = self.ox + (VIEW_COLS - w) // 2
        self.fill(y, x, h, w, self.attr("panel_fg", "panel"))
        for i, l in enumerate(lines):
            self.put(y + 1 + i, x + (w - len(l)) // 2, l, self.attr("title" if i == 0 else "panel_fg", "panel", i == 0))

    def draw_help(self):
        self.fill(self.oy, self.ox, VIEW_ROWS, VIEW_COLS, self.attr("panel_fg", "panel"))
        self.center(self.oy + 1, "NIGHTWATCH BRIEFING", self.attr("title", "panel", True))
        for i, line in enumerate(CONTROLS):
            self.put(self.oy + 3 + i, self.ox + 2, line, self.attr("panel_fg", "panel"))
        self.center(self.oy + VIEW_ROWS - 2, "any key to return", self.attr("hud_dim", "panel"))

    def draw_gameover(self, g):
        y = self.oy + PLAY_TOP + 2
        self.fill(y - 1, self.ox + 4, 13, VIEW_COLS - 8, self.attr("panel_fg", "panel"))
        self.big_center(y, g.banner, self.attr("core", "panel", True))
        alive = len(g.people_alive())
        self.center(y + 6, "FINAL SCORE %06d     WAVE %d" % (g.score, g.wave), self.attr("hud", "panel", True))
        if g.score >= g.high and g.score > 0:
            self.center(y + 7, "NEW HIGH SCORE", self.attr("title3", "panel", True))
        else:
            self.center(y + 7, "HIGH SCORE %06d" % g.high, self.attr("hud_gold", "panel"))
        if alive:
            self.center(y + 8, "%d of %d townsfolk lived to tell the tabloids." % (alive, len(g.people)), self.attr("person", "panel"))
        else:
            self.center(y + 8, "Nobody was left to tell the tabloids.", self.attr("hud_dim", "panel"))
        self.center(y + 10, "N  new game        Q  quit", self.attr("hud_dim", "panel"))

    def draw_title(self, g):
        self.fill(self.oy, self.ox, VIEW_ROWS, VIEW_COLS, self.attr("star", "space"))
        # starfield
        for wy, stars in g.world.stars.items():
            if wy >= KARMAN:
                continue
            for sx, ch, fg in stars:
                r = (wy * 7) % 20
                c = (sx * 3 + wy) % VIEW_COLS
                if 1 <= r < 19:
                    self.put(self.oy + r, self.ox + c, ch, self.attr(fg, "space"))
        t = g.title_t
        self.big_center(self.oy + 1, "NIGHTWATCH", self.attr("title", "space", True))
        self.big_center(self.oy + 7, "1985", self.attr("title2", "space", True))
        # a saucer over the town, beaming somebody up
        gy = self.oy + 18
        self.put(gy, self.ox, "▀" * VIEW_COLS, self.attr("grass", "ground"))
        town = ("▐o█o▌  ▄▄▄▄▄▄▄▄▄▄   ▐o█o▌    ▄▄▄▄▄▄▄▄▄  ▐o█o▌   ▄███▄ ",
                "▐███▌  █o██o██o██   ▐███▌    ▌  ▐o█  ▐  ▐███▌   ▀███▀ ")
        for r, row in enumerate(town):
            for c, ch in enumerate(row):
                if ch == " ":
                    continue
                fg = "window" if ch == "o" else "silhouette"
                ch = "▪" if ch == "o" else ch
                self.put(gy - 2 + r, self.ox + 4 + c, ch, self.attr(fg, "atmo6", True))
        sx = self.ox + 30 + int(3 * math.sin(t / 25.0))
        frame = LANDER[(t // 6) % 2]
        for r, row in enumerate(frame):
            for c, ch in enumerate(row):
                if ch != " ":
                    self.put(gy - 8 + r, sx + c, ch, self.attr("lamp" if ch == "▪" else "lander", "space", True))
        if (t // 3) % 2:
            for yy in range(gy - 6, gy - 2):
                self.put(yy, sx + 2, BEAM[yy % 2], self.attr("beam", "space", True))
        py = gy - 3 - ((t // 10) % 4)
        self.put(py, sx + 2, "●", self.attr("person", "space", True))
        self.put(py + 1, sx + 2, "█", self.attr("person", "space", True))
        # the interceptor streaks past
        ix = self.ox + (t * 2 // 3) % (VIEW_COLS + 20) - 10
        for r, row in enumerate(SHIP_R):
            for c, ch in enumerate(row):
                if ch != " " and 0 <= ix + c - self.ox < VIEW_COLS:
                    self.put(gy - 12 + r, ix + c, ch, self.attr("canopy" if (r, c) in SHIP_CANOPY else "ship", "space", True))
        self.center(self.oy + 13, "SAUCERS ARE ABDUCTING THE TOWN OF CEDAR HOLLOW", self.attr("hud", "space"))
        self.center(self.oy + 14, "FLY THE INTERCEPTOR.  FROM THE DIRT TO ORBIT.  SAVE THEM.", self.attr("hud_dim", "space"))
        self.center(self.oy + 20, "HIGH SCORE %06d" % g.high, self.attr("hud_gold", "space", True))
        if (t // 15) % 2:
            self.center(self.oy + 22, "N  SCRAMBLE       ?  BRIEFING       Q  QUIT", self.attr("title3", "space", True))
        else:
            self.center(self.oy + 22, "N  SCRAMBLE       ?  BRIEFING       Q  QUIT", self.attr("hud_dim", "space"))
