# Nightwatch 1985

Saucers are snatching people off the back roads of Cedar Hollow, and you fly
the only thing that can stop them: an experimental interceptor that works just
as well in the dirt as it does in orbit. Atari 2600 looks, Defender-style
play, running entirely inside your terminal.

<p align="center">
<img width="560" height="418" alt="nightwatch_1985" src="https://github.com/user-attachments/assets/134a4908-497b-48b1-ae65-59ae5908207a" />
</p>

```bash
./play.sh
```

or `python3 -m nightwatch` from this folder. Needs Python 3 (ships with macOS)
and a terminal at least 64 columns by 24 rows. A 256-colour terminal gives the
dusk-to-black sky gradient; 8-colour terminals still work. Hold a key to keep
thrusting; a fast key-repeat rate in your OS settings makes flying smoother.

## The game

The world is five screens wide and wraps around. At the bottom is the town:
Nightwatch Base, Elm Street, the church, the Route 9 Diner, Gus's Garage,
Miller Farm, the water tower, the KRUX radio tower, a trailer park, the
drive-in, the motel and Lookout Hill, with ten named townsfolk wandering
between them. Above the town is the night sky, and above a dotted line, orbit.

- **Two flight regimes.** In the atmosphere gravity pulls you down and drag
  bleeds off speed, so you fly like a jet: nose it around, thrust to climb,
  ease off to sink. Climb through the dotted line and you are in zero-G. No
  gravity, no drag. Every bit of momentum stays with you until you thrust the
  other way. The status line tells you which regime you are in.
- **The abduction.** Green saucers drop from the mothership, find someone on
  the ground, lock a tractor beam on them and haul them up toward orbit. Shoot
  the saucer and its victim falls. Fly into them to catch them, then get low
  and slow (or land) to set them down. In orbit a dropped person drifts
  instead, so you have to chase them down before they float into the
  mothership's field. Anyone carried above the mothership is gone.
- **The rest of the invasion.** Red scouts patrol and dive at you in the
  atmosphere but cannot fly in vacuum. Magenta drones hunt you in orbit and
  burn up if they dip too low. Take too long on a wave and a hunter comes for
  you wherever you are.
- **The mothership.** It sits in orbit spawning saucers and is armoured. Every
  third wave, once its saucers are gone, it descends and its hull splits open
  on a cycle. Line up with the slot and put bolts through the core. Kill it
  and up to three abductees come back down in escape pods.
- **Waves.** A wave ends when every saucer is destroyed. Bonus points for each
  townsperson still on the ground. Smart bombs (B) wipe every invader on
  screen; you get one back each wave.
- **Shields and landing.** Three hits and you are down. Set down gently on the
  Nightwatch Base pad to repair. Come in too fast anywhere and you crash.
- **Game over** when you run out of ships, or when the town is empty.

The high score is saved to `highscore.json` in this folder.

## Controls

| Key | Action |
| --- | --- |
| Arrows / WASD | Thrust. Left and right also turn the ship |
| Space / F | Fire the pulse cannon the way you face |
| B | Smart bomb |
| P | Pause |
| ? | Briefing (controls and tactics) |
| Q / Esc | Quit (asks first) |

## Layout

```
nightwatch/
  constants.py   layout, physics tuning, palette, sprites, block font, radio lines
  world.py       the town silhouettes, townsfolk, stars and sky bands
  entities.py    Ship, Person, Lander, Scout, Drone, Hunter, Mothership, Shot, Particle
  render.py      curses drawing: HUD, long-range scanner, sky, sprites, overlays
  engine.py      game loop, input, flight physics, invader AI, waves, collisions
  __main__.py    entry point
highscore.json   created after your first game
```

Physics constants live at the top of `constants.py`; `GRAVITY`, `DRAG` and the
`IMPULSE_*` values set how the atmosphere feels, and `KARMAN` is the row where
space begins. To add a building, add a sprite and a `FEATURES` entry in
`world.py`. To add a townsperson, add a name and home x to `TOWNSFOLK`.
