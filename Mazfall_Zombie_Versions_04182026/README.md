# Mazfall_Zombie_Alpha_v0.5

> *Doomfall 0.1's soul · Mazfall α0.02's spine · infinite recursive corridors, infinite undead, one overheating chaingun.*

A hyper‑minimalist ASCII Doom‑mod raycaster. Three implementations of the same engine — **Python**, **C**, and **x86_64 Assembly** — each as small as the target platform allows.

---

## Lineage

- **Doomfall 0.1** (ASCII raycaster aesthetic) — the ramp `" .:-=+*#%@"`, column-stride render, the deliberately small screen.
- **Mazfall Alpha 0.02** (algorithmic skeleton) — LCG-seeded chunked maze, recursive chunk hashing, zombie tiers, the eightfold chaingun heat spine.
- **Pure Doom logic** — tile walls, DDA ray step, axis-separated slide collision, shoot-the-thing-in-the-crosshair.

The merge strips both parents to their load-bearing bones and fuses them into a single organism that generates itself forever.

---

## Core mechanics (all versions)

- **Infinite maze** — space is tiled in `21×21` chunks. Each chunk's seed is derived from the world seed + `(cx, cy)` via a Knuth multiplicative hash; chunks are carved by iterative DFS over an LCG (`A=1664525, C=1013904223, M=2^32`) and cached LRU (cap 256). Walk in any direction forever, deterministically.
- **Infinite zombies** — a bounded active pool. Every kill spawns **two** replacements at the far edge of the currently visible chunk ring. Population never decreases. Difficulty tier `= 1 + level//3`.
- **Chaingun with overheat** — infinite ammo, but a hard thermal budget. `HEAT_MAX=100`, `HEAT_PER_SHOT=8`, `COOL=72/s`, fire rate `.035s`, post-lockout recovery gate `RES=16`. Hold to spray; pace to survive.
- **Faster feel** — move `0.18 u/frame`, turn `0.08 rad/frame`, mouse `0.005 rad/px`. Noticeably quicker than the parents.
- **ASCII ramp** — `" .:-=+*#%@"`, distance-shaded. Untouched from Doomfall.

---

## Files

| File | Lines | Size | Runs on |
|---|---|---|---|
| `Mazfall_Zombie_Alpha_v0.5.py`  | 181 | 8.4 KB | Any OS with Python 3 + pygame |
| `Mazfall_Zombie_Alpha_v0.5.c`   | 324 | 14 KB  | POSIX terminal (Linux/macOS) |
| `Mazfall_Zombie_Alpha_v0.5.asm` | 380 | 12 KB  | Linux x86_64, NASM, no libc   |

---

## Build & run

### Python (full game — maze, zombies, chaingun, audio)
```bash
python3 Mazfall_Zombie_Alpha_v0.5.py
```
Auto-installs `pygame` + `numpy` on first run.

### C (full game — terminal ANSI, no audio)
```bash
cc -O2 -Wall Mazfall_Zombie_Alpha_v0.5.c -o mz05 -lm
./mz05
```
Renders with ANSI 256-gray in any POSIX terminal. Termios raw mode; restores on exit.

### Assembly (engine kernel — raycaster + movement on a 16×16 hand-carved cell)
```bash
nasm -f elf64 Mazfall_Zombie_Alpha_v0.5.asm -o mz.o
ld mz.o -o mz_asm
./mz_asm
```
No libc. Raw syscalls only (`read`/`write`/`ioctl`/`nanosleep`/`fcntl`/`exit`). SSE2 for arithmetic, x87 `fsincos` for trig. The asm version demonstrates the raycast engine itself at the metal — zombies and chaingun are omitted by design (they would balloon this to ~1500 lines of asm; the kernel is the point).

---

## Controls

| Action         | Python / C     | Asm            |
|----------------|----------------|----------------|
| Move           | `WASD` / arrows| `WASD`         |
| Turn           | mouse / `J L`  | `J L`          |
| Fire chaingun  | `SPACE` / LMB  | —              |
| New world seed | `N`            | —              |
| Respawn        | `R`            | —              |
| Quit           | `ESC` / `Q`    | `Q` / `ESC`    |

---

## Engine constants (shared)

```
CHUNK_SIZE    = 21        chaingun RATE    = 0.035 s
CACHE_CAP     = 256       chaingun HEAT_MAX= 100
ZOMBIE_POOL   = 40–256    chaingun HPS     = 8
RAY_STEP      = 0.04      chaingun COOL    = 72/s
RAY_MAX       = 20        chaingun RESUME  = 16
FOV           = π/3       move speed       = 0.18
ASCII ramp    = " .:-=+*#%@"
```

---

## Why three languages

Because the same engine reads differently at each altitude. The Python is the readable spec. The C is the embodiment — a full playable ASCII Doom-mod in one terminal. The asm is the reduction proof — this is what the raycaster actually is when you strip every runtime.

*Keep walking. The corridors never end and neither do they.*
