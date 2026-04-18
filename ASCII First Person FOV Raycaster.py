#ASCII First Person FOV Terminal Renderspace

#!/usr/bin/env python3
"""
DOOMFLOW  –  Pure Python · Single File · Zero Dependencies
A hyper-minimalist DOOM-style raycasting engine for the terminal.

Controls:
  W / ↑   Move forward
  S / ↓   Move backward
  A / ←   Rotate left
  D / →   Rotate right
  Q       Quit

Runs on any Python 3.6+ terminal that supports ANSI escape codes
(Linux, macOS, Windows Terminal / PowerShell with ANSI enabled).
"""

import math
import os
import sys
import time
import select
import tty
import termios
import threading

# ─────────────────────────────────────────────
#  MAP  (1 = wall, 0 = open, P = player start)
# ─────────────────────────────────────────────
RAW_MAP = [
    "####################",
    "#........#.........#",
    "#........#.........#",
    "#....#...#....#....#",
    "#....#.........#...#",
    "#....###########...#",
    "#..................#",
    "#....#.....#.......#",
    "#....#.....#.......#",
    "#..P.......#.......#",
    "#....#.....#.......#",
    "#....#.....#.......#",
    "#..................#",
    "#........#.........#",
    "####################",
]

MAP_W = len(RAW_MAP[0])
MAP_H = len(RAW_MAP)

WORLD  = []
PLAYER_START = (1.5, 1.5, 0.0)   # fallback

for row_idx, row in enumerate(RAW_MAP):
    WORLD.append([])
    for col_idx, ch in enumerate(row):
        if ch == 'P':
            PLAYER_START = (col_idx + 0.5, row_idx + 0.5, 0.0)
            WORLD[-1].append(0)
        elif ch == '#':
            WORLD[-1].append(1)
        else:
            WORLD[-1].append(0)

# ─────────────────────────────────────────────
#  RENDERER CONSTANTS
# ─────────────────────────────────────────────
SCREEN_W   = 80       # columns
SCREEN_H   = 24       # rows  (leave 1 for HUD)
FOV        = math.pi / 3.0          # 60 degrees
HALF_FOV   = FOV / 2.0
MAX_DEPTH  = 16.0
MOVE_SPEED = 0.07
ROT_SPEED  = 0.05

# ASCII shade palette – bright → dim
SHADE = "@#%*+=-:. "     # 10 levels

# ANSI colour helpers
def ansi(code): return f"\x1b[{code}m"
RESET   = ansi(0)
RED     = ansi("31;1")
GREEN   = ansi("32;1")
YELLOW  = ansi("33;1")
BLUE    = ansi(34)
CYAN    = ansi(36)
GRAY    = ansi(90)
WHITE   = ansi("37;1")

WALL_COLOURS = [RED, YELLOW, WHITE, CYAN, GREEN]   # cycle by column

# ─────────────────────────────────────────────
#  PLAYER STATE
# ─────────────────────────────────────────────
class Player:
    def __init__(self):
        self.x, self.y, self.angle = PLAYER_START
        self.health = 100
        self.ammo   = 50

    def move(self, dx, dy):
        nx = self.x + dx
        ny = self.y + dy
        if 0 <= int(nx) < MAP_W and WORLD[int(self.y)][int(nx)] == 0:
            self.x = nx
        if 0 <= int(ny) < MAP_H and WORLD[int(ny)][int(self.x)] == 0:
            self.y = ny

    def forward(self, speed=MOVE_SPEED):
        self.move(math.cos(self.angle) * speed, math.sin(self.angle) * speed)

    def backward(self, speed=MOVE_SPEED):
        self.move(-math.cos(self.angle) * speed, -math.sin(self.angle) * speed)

    def rotate_left(self):
        self.angle -= ROT_SPEED

    def rotate_right(self):
        self.angle += ROT_SPEED

# ─────────────────────────────────────────────
#  RAY-CASTER
# ─────────────────────────────────────────────
def cast_ray(px, py, angle):
    """DDA ray-cast. Returns (distance, wall_x_hit_fraction)."""
    ray_cos = math.cos(angle) or 1e-10
    ray_sin = math.sin(angle) or 1e-10

    # Step sizes along the ray for each axis
    delta_dist_x = abs(1 / ray_cos)
    delta_dist_y = abs(1 / ray_sin)

    map_x = int(px)
    map_y = int(py)

    step_x = 1 if ray_cos > 0 else -1
    step_y = 1 if ray_sin > 0 else -1

    side_dist_x = (map_x + 1 - px) * delta_dist_x if ray_cos > 0 else (px - map_x) * delta_dist_x
    side_dist_y = (map_y + 1 - py) * delta_dist_y if ray_sin > 0 else (py - map_y) * delta_dist_y

    hit  = False
    side = 0   # 0 = x-side, 1 = y-side
    for _ in range(int(MAX_DEPTH * 10)):
        if side_dist_x < side_dist_y:
            side_dist_x += delta_dist_x
            map_x += step_x
            side = 0
        else:
            side_dist_y += delta_dist_y
            map_y += step_y
            side = 1

        if map_x < 0 or map_x >= MAP_W or map_y < 0 or map_y >= MAP_H:
            break
        if WORLD[map_y][map_x] == 1:
            hit = True
            break

    if not hit:
        return MAX_DEPTH, 0.5

    if side == 0:
        perp = (map_x - px + (1 - step_x) / 2) / ray_cos
        wall_x = py + perp * ray_sin
    else:
        perp = (map_y - py + (1 - step_y) / 2) / ray_sin
        wall_x = px + perp * ray_cos

    wall_x -= math.floor(wall_x)
    return max(0.001, perp), wall_x

# ─────────────────────────────────────────────
#  FRAME BUILDER
# ─────────────────────────────────────────────
def render_frame(player):
    rows = []

    # Pre-compute for each screen column
    cols = []
    for col in range(SCREEN_W):
        ray_angle = player.angle - HALF_FOV + (col / SCREEN_W) * FOV
        dist, wall_x = cast_ray(player.x, player.y, ray_angle)
        cols.append((dist, wall_x))

    for row in range(SCREEN_H):
        line = []
        for col, (dist, wall_x) in enumerate(cols):
            # Wall height on screen
            wall_h = int(SCREEN_H / (dist + 0.0001))
            half   = SCREEN_H // 2

            if row < half - wall_h // 2:
                # Ceiling
                line.append(GRAY + "." + RESET)
            elif row > half + wall_h // 2:
                # Floor – shade by distance from centre
                floor_shade = min(9, int((row - half) / (SCREEN_H / 2) * 10))
                line.append(GRAY + SHADE[floor_shade] + RESET)
            else:
                # Wall – shade by distance
                shade_idx = min(9, int(dist / MAX_DEPTH * len(SHADE)))
                ch = SHADE[shade_idx]
                colour = WALL_COLOURS[col % len(WALL_COLOURS)]
                # Darken y-sides slightly
                line.append(colour + ch + RESET)

        rows.append("".join(line))

    # ── HUD ──────────────────────────────────
    hud = (
        f"{RED}HP:{player.health:3d}{RESET}  "
        f"{YELLOW}AMMO:{player.ammo:3d}{RESET}  "
        f"{CYAN}POS:({player.x:.1f},{player.y:.1f}){RESET}  "
        f"{GREEN}WASD/ARROWS=move  Q=quit{RESET}"
    )
    rows.append(hud[:SCREEN_W * 12])   # crude truncate for colour escape len

    return rows

# ─────────────────────────────────────────────
#  CROSSHAIR overlay (drawn after)
# ─────────────────────────────────────────────
CROSSHAIR_ROW = SCREEN_H // 2
CROSSHAIR_COL = SCREEN_W // 2

# ─────────────────────────────────────────────
#  TERMINAL UTILS
# ─────────────────────────────────────────────
def clear():   sys.stdout.write("\x1b[2J\x1b[H");  sys.stdout.flush()
def hide_cur(): sys.stdout.write("\x1b[?25l");      sys.stdout.flush()
def show_cur(): sys.stdout.write("\x1b[?25h");      sys.stdout.flush()
def goto(r, c): sys.stdout.write(f"\x1b[{r};{c}H"); sys.stdout.flush()

def draw_frame(rows):
    """Write the whole frame in one write() call for speed."""
    buf = ["\x1b[H"]   # cursor to home
    for i, row in enumerate(rows):
        buf.append(row)
        if i < len(rows) - 1:
            buf.append("\n")
    # Crosshair
    # We can't easily overwrite mid-row here without re-building; skip for perf
    sys.stdout.write("".join(buf))
    sys.stdout.flush()

# ─────────────────────────────────────────────
#  NON-BLOCKING KEYBOARD (UNIX)
# ─────────────────────────────────────────────
class InputHandler:
    """Thread-safe, non-blocking single-char reader."""
    def __init__(self):
        self._keys = set()
        self._lock  = threading.Lock()
        self._running = True
        self._old_settings = None
        self._thread = threading.Thread(target=self._read_loop, daemon=True)

    def start(self):
        try:
            self._old_settings = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())
        except Exception:
            pass
        self._thread.start()

    def stop(self):
        self._running = False
        if self._old_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_settings)
            except Exception:
                pass

    def _read_loop(self):
        while self._running:
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.02)
                if r:
                    ch = sys.stdin.read(1)
                    with self._lock:
                        self._keys.add(ch.lower())
                        # Detect arrow keys (ESC [ A/B/C/D)
                        if ch == '\x1b':
                            r2, _, _ = select.select([sys.stdin], [], [], 0.02)
                            if r2:
                                ch2 = sys.stdin.read(1)
                                if ch2 == '[':
                                    r3, _, _ = select.select([sys.stdin], [], [], 0.02)
                                    if r3:
                                        ch3 = sys.stdin.read(1)
                                        arrow_map = {'A':'w','B':'s','C':'d','D':'a'}
                                        self._keys.add(arrow_map.get(ch3, ''))
            except Exception:
                break

    def pressed(self, key):
        with self._lock:
            return key in self._keys

    def clear(self):
        with self._lock:
            self._keys.clear()

# ─────────────────────────────────────────────
#  TITLE / SPLASH
# ─────────────────────────────────────────────
TITLE = r"""
  ██████╗  ██████╗  ██████╗ ███╗   ███╗███████╗██╗      ██████╗ ██╗    ██╗
  ██╔══██╗██╔═══██╗██╔═══██╗████╗ ████║██╔════╝██║     ██╔═══██╗██║    ██║
  ██║  ██║██║   ██║██║   ██║██╔████╔██║█████╗  ██║     ██║   ██║██║ █╗ ██║
  ██║  ██║██║   ██║██║   ██║██║╚██╔╝██║██╔══╝  ██║     ██║   ██║██║███╗██║
  ██████╔╝╚██████╔╝╚██████╔╝██║ ╚═╝ ██║██║     ███████╗╚██████╔╝╚███╔███╔╝
  ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝
"""

def splash():
    clear()
    print(RED + TITLE + RESET)
    print(WHITE + "  Pure Python · Single File · Terminal Raycaster" + RESET)
    print()
    print(YELLOW + "  WASD or Arrow Keys  –  Move & Rotate" + RESET)
    print(YELLOW + "  Q                   –  Quit" + RESET)
    print()
    print(GRAY  + "  Press any key to start..." + RESET)
    sys.stdout.flush()

# ─────────────────────────────────────────────
#  MAIN GAME LOOP
# ─────────────────────────────────────────────
def main():
    # Check for TTY (won't work in piped contexts)
    if not sys.stdin.isatty():
        print("DOOMFLOW requires an interactive terminal. Run: python3 doomflow.py")
        sys.exit(1)

    splash()

    inp = InputHandler()
    inp.start()

    # Wait for keypress to start
    while not inp._keys:
        time.sleep(0.05)
    inp.clear()

    player = Player()
    hide_cur()
    clear()

    try:
        target_fps = 30
        frame_time = 1.0 / target_fps
        last = time.time()

        while True:
            # ── Input ──────────────────────────
            if inp.pressed('q') or inp.pressed('\x03'):   # q or Ctrl-C
                break

            if inp.pressed('w'):
                player.forward()
            if inp.pressed('s'):
                player.backward()
            if inp.pressed('a'):
                player.rotate_left()
            if inp.pressed('d'):
                player.rotate_right()

            inp.clear()

            # ── Render ─────────────────────────
            rows = render_frame(player)
            draw_frame(rows)

            # ── Timing ─────────────────────────
            now  = time.time()
            diff = frame_time - (now - last)
            if diff > 0:
                time.sleep(diff)
            last = time.time()

    except KeyboardInterrupt:
        pass
    finally:
        show_cur()
        clear()
        inp.stop()
        print(GREEN + "Thanks for playing DOOMFLOW. .-" + RESET)


if __name__ == "__main__":
    main()
