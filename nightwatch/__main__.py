"""Entry point: python3 -m nightwatch"""
import curses
import locale
import os
import sys


def main():
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    if not os.environ.get("TERM"):
        os.environ["TERM"] = "xterm-256color"
    from .engine import Game

    def run(stdscr):
        Game(stdscr).run()

    try:
        curses.wrapper(run)
    except KeyboardInterrupt:
        pass
    print("Nightwatch signing off. Keep watching the skies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
