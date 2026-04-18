#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZFALL v1.2 — Infinite ASCII Zombie-Maze DOOM  (single file)
Doomfall 0.1 engine · deep-end gunfire · procedural horror drone ·
ASCII gore · humanized TTS announcer with live subtitles.

Controls
  WASD        move
  Mouse       aim (captured)
  ← / →       keyboard turn
  SPACE / LMB fire (auto-rapid, bottomless)
  R           respawn
  ESC         quit
"""
import sys, subprocess, math, random, time, threading, queue

def _ins(p):
    try: __import__(p); return True
    except ImportError:
        try: subprocess.call([sys.executable,"-m","pip","install",p,"--user"])
        except Exception: pass
    try: __import__(p); return True
    except ImportError: return False

for _p in ("pygame","numpy"): _ins(_p)
_HAS_TTS = _ins("pyttsx3")

import pygame, numpy as np

# ── HARDWARE-ADAPTIVE DISPLAY ─────────────────────────────────────
pygame.display.init()
_i = pygame.display.Info()
DW, DH = _i.current_w, _i.current_h
_LOW = DW < 1280 or DH < 720
W, H = (90, 28) if _LOW else (120, 40)
S = max(4, min(int(DW*0.92)//W, int(DH*0.88)//H))
S = min(S, 22)
FPS = 20 if _LOW else 30

# ── CONFIG ────────────────────────────────────────────────────────
FOV, RAMP     = math.pi/3, " .:-=+*#%@"
MZ            = 19 if _LOW else 21
MAXZ          = 3
SPAWN_MIN_D   = 5
FIRE_DT, HIT_DT = 0.08, 0.8
ZSPEED, MOVE  = 0.028, 0.09
LEVEL_KILLS   = 10
HP_REGEN_DT, HP_REGEN_AMT, HP_REGEN_WAIT = 0.3, 5, 2.0
DMG           = 4
COMBO_WIN     = 2.5
SR            = 22050

# ── MAZE (recursive backtracker) ──────────────────────────────────
def gen_maze(n):
    sys.setrecursionlimit(max(1000, n*n*4))
    g = [['#']*n for _ in range(n)]
    def carve(x, y):
        g[y][x] = '.'
        d = [(2,0),(-2,0),(0,2),(0,-2)]; random.shuffle(d)
        for dx, dy in d:
            nx, ny = x+dx, y+dy
            if 0 < nx < n-1 and 0 < ny < n-1 and g[ny][nx] == '#':
                g[y+dy//2][x+dx//2] = '.'; carve(nx, ny)
    carve(1, 1); return g

def is_wall(m, x, y):
    ix, iy = int(x), int(y)
    if ix < 0 or iy < 0 or iy >= len(m) or ix >= len(m[0]): return True
    return m[iy][ix] == '#'

def free_cells(m):
    return [(x+0.5, y+0.5) for y, r in enumerate(m)
            for x, c in enumerate(r) if c == '.']

def cast(m, px, py, a):
    dx, dy = math.cos(a), math.sin(a); t = 0.0
    step = 0.05 if _LOW else 0.04
    while t < 25:
        if is_wall(m, px+dx*t, py+dy*t): return t
        t += step
    return 25

# ── AUDIO HELPERS ─────────────────────────────────────────────────
def _env(t, d, atk=40, rel=5):
    return np.clip(np.minimum(t*atk, (d-t)*rel), 0, 1)

def _snd(w, amp=25000):
    w = (np.clip(w, -1, 1) * amp).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack([w, w]))

def _mk(w, t, d, atk=40, rel=5, amp=25000):
    return _snd(w * _env(t, d, atk, rel), amp)

def synth_tone(freq, dur, kind='sine'):
    n = max(1, int(SR*dur)); t = np.linspace(0, dur, n, False)
    if kind == 'sine':     w = np.sin(2*math.pi*freq*t)
    elif kind == 'square': w = np.sign(np.sin(2*math.pi*freq*t))
    elif kind == 'noise':  w = np.random.uniform(-1,1,n) * np.exp(-t*12)
    else:
        f = freq * np.exp(-t*6); w = np.sin(2*math.pi*np.cumsum(f)/SR)
    return _mk(w, t, dur)

# ── DEEP GUNFIRE  (sub-heavy, minimal snap) ───────────────────────
def synth_gun():
    d = 0.25; n = int(SR*d); t = np.linspace(0, d, n, False)
    # Tamed broadband click (transient, not snap)
    crack = np.random.uniform(-1,1,n) * np.exp(-t*28) * 0.50
    high  = np.random.uniform(-1,1,n) * np.exp(-t*90) * 0.22
    # Warm mid (280 -> 70 Hz) — the gun's "body"
    mf    = 280 * np.exp(-t*12) + 70
    mid   = np.sin(2*math.pi*np.cumsum(mf)/SR) * np.exp(-t*8) * 0.75
    # Chest thump (90 Hz)
    cf    = 90 * np.exp(-t*5) + 55
    chest = np.sin(2*math.pi*np.cumsum(cf)/SR) * np.exp(-t*5) * 1.15
    # Sub-bass boom (50 -> 30 Hz), heavy and long
    lf    = 50 * np.exp(-t*1.4) + 30
    low   = np.sin(2*math.pi*np.cumsum(lf)/SR) * np.exp(-t*2.3) * 1.90
    return _mk(crack + high + mid + chest + low, t, d, 100, 4, 28000)

# ── GORE  (wet squelch + meat thud + bone) ────────────────────────
def synth_gore():
    d = 0.55; n = int(SR*d); t = np.linspace(0, d, n, False)
    noise = np.random.uniform(-1,1,n)
    lp    = np.convolve(noise, np.ones(40)/40, mode='same')
    mod   = 0.4 + 0.6*np.sin(2*math.pi*18*t*np.exp(-t*1.8))
    squelch = lp * mod * np.exp(-t*3.2)
    thud    = np.sin(2*math.pi*52*t) * np.exp(-t*6.5) * 0.9
    bone    = np.random.uniform(-1,1,n) * np.exp(-t*55) * 0.35
    return _mk(squelch + thud + bone, t, d, 70, 3.5, 26000)

# ── PROCEDURAL HORROR DRONE  (regenerates forever) ────────────────
def synth_drone(dur):
    n = int(SR*dur); t = np.linspace(0, dur, n, False)
    # Two detuned sub drones with slow LFO (foundation)
    f1 = 42 + 4*np.sin(2*math.pi*0.07*t)
    f2 = 63 + 6*np.sin(2*math.pi*0.05*t + 0.7)
    bed = (np.sin(2*math.pi*np.cumsum(f1)/SR) * 0.55 +
           np.sin(2*math.pi*np.cumsum(f2)/SR) * 0.35)
    # Wind rumble (lowpassed noise)
    rumble = np.convolve(np.random.uniform(-1,1,n),
                         np.ones(220)/220, mode='same') * 0.45
    bed += rumble
    # Scatter random textures through the buffer:
    def splice(buf, start, payload, gain=1.0):
        end = min(start + len(payload), n)
        buf[start:end] += payload[:end-start] * gain
    # distant shrieks — high freq sweeps
    for _ in range(int(dur*0.5)):
        i = int(random.uniform(0, dur-0.5)*SR)
        sd = random.uniform(0.18, 0.45); sn = int(sd*SR)
        st = np.linspace(0, sd, sn, False)
        fr = random.uniform(1400, 3200) * np.exp(-st*random.uniform(1.5,3))
        sh = np.sin(2*math.pi*np.cumsum(fr)/SR) * np.exp(-st*4) * random.uniform(0.08, 0.18)
        splice(bed, i, sh)
    # mid growls / groans — modulated low-mid sines
    for _ in range(int(dur*0.35)):
        i = int(random.uniform(0, dur-1)*SR)
        gd = random.uniform(0.4, 0.9); gn = int(gd*SR)
        st = np.linspace(0, gd, gn, False)
        fr = random.uniform(75, 170) + 18*np.sin(2*math.pi*random.uniform(5,11)*st)
        gr = np.sin(2*math.pi*np.cumsum(fr)/SR) * np.exp(-st*1.4) * random.uniform(0.18, 0.28)
        splice(bed, i, gr)
    # screams — mid-high cries
    for _ in range(int(dur*0.15)):
        i = int(random.uniform(0, dur-0.8)*SR)
        sd = random.uniform(0.35, 0.75); sn = int(sd*SR)
        st = np.linspace(0, sd, sn, False)
        fr = random.uniform(500, 900) * (1 + 0.3*np.sin(2*math.pi*7*st))
        sc = np.sin(2*math.pi*np.cumsum(fr)/SR)
        sc *= np.random.uniform(0.6, 1.0, sn)  # ragged
        sc *= np.exp(-st*2.2) * random.uniform(0.12, 0.2)
        splice(bed, i, sc)
    # thuds / thumps — low sine pops
    for _ in range(int(dur*0.4)):
        i = int(random.uniform(0, dur-0.3)*SR)
        td = 0.25; tn = int(td*SR); st = np.linspace(0, td, tn, False)
        th = np.sin(2*math.pi*(35+random.uniform(0,15))*st) * np.exp(-st*random.uniform(7,11))
        splice(bed, i, th, random.uniform(0.25, 0.45))
    # boom — occasional heavy sub hit
    for _ in range(int(dur*0.12)):
        i = int(random.uniform(0, dur-0.5)*SR)
        bd = 0.5; bn = int(bd*SR); st = np.linspace(0, bd, bn, False)
        bf = 45 * np.exp(-st*3) + 25
        bm = np.sin(2*math.pi*np.cumsum(bf)/SR) * np.exp(-st*3.5) * random.uniform(0.4, 0.7)
        splice(bed, i, bm)
    # seamless fade-in/out so loop transitions are inaudible
    fi = int(SR*0.4)
    bed[:fi]  *= np.linspace(0, 1, fi)
    bed[-fi:] *= np.linspace(1, 0, fi)
    return _snd(bed, 18000)

# ── TTS ANNOUNCER  (humanized, threaded, with subtitles) ──────────
_tts_q   = queue.Queue(maxsize=4)
_tts_ok  = _HAS_TTS
_sub_txt = ""
_sub_until = 0.0

def _tts_worker():
    global _tts_ok
    eng = None
    if _HAS_TTS:
        try:
            import pyttsx3
            eng = pyttsx3.init()
            eng.setProperty('rate', 155)      # slower, more human cadence
            eng.setProperty('volume', 0.82)
            # prefer a natural-sounding voice where available
            try:
                voices = eng.getProperty('voices')
                prefer = ('samantha','alex','victoria','daniel','karen',
                          'zira','david','mark','natural','neural','premium')
                for v in voices:
                    nm = (v.name or '').lower()
                    if any(p in nm for p in prefer):
                        eng.setProperty('voice', v.id); break
            except Exception: pass
        except Exception:
            _tts_ok = False; eng = None
    while True:
        m = _tts_q.get()
        if m is None: return
        if eng is None: continue
        try: eng.say(m); eng.runAndWait()
        except Exception: pass

threading.Thread(target=_tts_worker, daemon=True).start()

def speak(msg, sub_dur=3.2):
    """Queue TTS line + show on-screen subtitle."""
    global _sub_txt, _sub_until
    _sub_txt   = msg
    _sub_until = time.time() + sub_dur
    if not _tts_ok: return
    try: _tts_q.put_nowait(msg)
    except queue.Full:
        try: _tts_q.get_nowait(); _tts_q.put_nowait(msg)
        except Exception: pass

# ── PYGAME MAIN INIT ──────────────────────────────────────────────
pygame.mixer.pre_init(SR, -16, 2, 256)
pygame.init()
pygame.mixer.set_num_channels(16)
DRONE_CH = pygame.mixer.Channel(15)          # reserved for ambient

screen = pygame.display.set_mode((W*S, H*S))   # windowed near-fullscreen, OS chrome intact
pygame.display.set_caption("MAZFALL")
font   = pygame.font.SysFont("Courier", S+2, bold=True)
subfnt = pygame.font.SysFont("Courier", max(12, S), bold=True)
clock  = pygame.time.Clock()

S_SHOT  = synth_gun()
S_GORE  = synth_gore()
S_PICK  = synth_tone(1100, 0.14, 'sine')
S_OUCH  = synth_tone(140,  0.18, 'noise')
S_SPAWN = synth_tone(95,   0.35, 'sweep')
S_LEVEL = synth_tone(420,  0.45, 'sweep')
S_DIE   = synth_tone(55,   0.90, 'noise')

def refresh_drone():
    snd = synth_drone(random.uniform(13, 22))
    snd.set_volume(0.48)
    DRONE_CH.play(snd)
refresh_drone()

# ── STATE ─────────────────────────────────────────────────────────
M         = gen_maze(MZ)
px, py    = 1.5, 1.5
ang       = 0.0
hp, score = 100, 0
kills, kl_level, level = 0, 0, 1
spd_mult  = 1.0
zombies   = []          # [x, y]
powers    = []          # [x, y, 'H'|'S']
blood     = []          # [x, y, vx, vy, life, char]
last_shot = last_hit = last_spawn = last_regen = last_kill_t = 0.0
combo, muzzle = 0, 0
dead      = False

def place_powers():
    global powers
    cs = [c for c in free_cells(M) if math.hypot(c[0]-px, c[1]-py) > 4]
    random.shuffle(cs)
    powers = [[c[0], c[1], random.choice(['H','S'])] for c in cs[:5]]
place_powers()

def next_maze():
    global M, px, py, ang, zombies, kl_level, level, blood
    level += 1
    M = gen_maze(MZ)
    px, py = random.choice(free_cells(M))
    ang = random.uniform(0, 2*math.pi)
    zombies, blood, kl_level = [], [], 0
    place_powers(); S_LEVEL.play(); speak(f"Wave {level}")

def spawn_z():
    cs = [c for c in free_cells(M) if math.hypot(c[0]-px, c[1]-py) > SPAWN_MIN_D]
    if not cs:
        cs = [c for c in free_cells(M) if math.hypot(c[0]-px, c[1]-py) > 2.5]
    if not cs: return
    zombies.append(list(random.choice(cs))); S_SPAWN.play()

def splatter(x, y):
    for _ in range(26):
        a2 = random.uniform(0, 2*math.pi)
        sp = random.uniform(0.2, 1.4)
        blood.append([x + random.uniform(-0.15,0.15),
                      y + random.uniform(-0.15,0.15),
                      math.cos(a2)*sp, math.sin(a2)*sp,
                      random.uniform(0.5, 1.2),
                      random.choice('@%#*+:;,.~oO')])

pygame.event.set_grab(True)
pygame.mouse.set_visible(False)
speak("Mazfall online. Stay sharp.")

# ── MAIN LOOP ─────────────────────────────────────────────────────
run = True
while run:
    dt  = clock.tick(FPS) / 1000.0
    now = time.time()

    # Keep the procedural ambient bed alive forever, fresh each cycle.
    if not DRONE_CH.get_busy(): refresh_drone()

    for e in pygame.event.get():
        if e.type == pygame.QUIT: run = False
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE: run = False
            elif e.key == pygame.K_r and dead:
                hp, spd_mult, dead = 100, 1.0, False
                zombies, combo = [], 0
                last_hit = now; speak("Respawned")
        elif e.type == pygame.MOUSEMOTION and not dead:
            ang += e.rel[0] * 0.003

    # ── UPDATE ────────────────────────────────────────────────────
    if not dead:
        keys = pygame.key.get_pressed()
        mv = MOVE * spd_mult
        fx, fy   = math.cos(ang)*mv,  math.sin(ang)*mv
        sxv, syv = -math.sin(ang)*mv, math.cos(ang)*mv
        ddx = ddy = 0.0
        if keys[pygame.K_w]: ddx += fx;  ddy += fy
        if keys[pygame.K_s]: ddx -= fx;  ddy -= fy
        if keys[pygame.K_a]: ddx -= sxv; ddy -= syv
        if keys[pygame.K_d]: ddx += sxv; ddy += syv
        if keys[pygame.K_LEFT]:  ang -= 0.04
        if keys[pygame.K_RIGHT]: ang += 0.04
        if not is_wall(M, px+ddx, py): px += ddx
        if not is_wall(M, px, py+ddy): py += ddy

        firing = keys[pygame.K_SPACE] or pygame.mouse.get_pressed()[0]
        if firing and now - last_shot > FIRE_DT:
            last_shot = now; muzzle = 3; S_SHOT.play()
            wd = cast(M, px, py, ang)
            best, bd = -1, 1e9
            for i, (zx, zy) in enumerate(zombies):
                rx, ry = zx-px, zy-py
                d = math.hypot(rx, ry)
                if d > wd: continue
                a = math.atan2(ry, rx) - ang
                a = (a + math.pi) % (2*math.pi) - math.pi
                tol = 0.10 + 0.45/(d+0.5)
                if abs(a) < tol and d < bd: bd, best = d, i
            if best >= 0:
                zx, zy = zombies[best]; zombies.pop(best)
                splatter(zx, zy); S_GORE.play()
                kills += 1; kl_level += 1
                combo = combo + 1 if now - last_kill_t < COMBO_WIN else 1
                last_kill_t = now; score += 10 * combo
                if   combo == 2:  speak("Double kill")
                elif combo == 3:  speak("Triple kill")
                elif combo == 4:  speak("Massacre")
                elif combo == 5:  speak("Killing spree")
                elif combo == 7:  speak("Unstoppable")
                elif combo >= 10 and combo % 5 == 0: speak("Godlike")

        for z in zombies:
            dx, dy = px - z[0], py - z[1]
            d = math.hypot(dx, dy)
            if d > 0.01:
                vx, vy = dx/d*ZSPEED, dy/d*ZSPEED
                if not is_wall(M, z[0]+vx, z[1]): z[0] += vx
                if not is_wall(M, z[0], z[1]+vy): z[1] += vy
            if d < 0.7 and now - last_hit > HIT_DT:
                hp -= DMG; last_hit = now; S_OUCH.play()
                if hp <= 0:
                    hp, dead, combo = 0, True, 0
                    S_DIE.play(); speak("Eliminated")

        for p in powers[:]:
            if math.hypot(p[0]-px, p[1]-py) < 0.6:
                if p[2] == 'H': hp = 100; speak("Medkit acquired")
                else:           spd_mult = min(3.5, spd_mult + 0.3); speak("Speed boost")
                score += 5; powers.remove(p); S_PICK.play()
        if not powers: place_powers()

        # REBALANCED RAMP — denser early, still scales
        max_zom  = min(MAXZ, 2 + (level - 1) // 3)    # 2,2,2,3,3,3,3...
        interval = max(0.3, 2.0 - (level - 1) * 0.15) # 2.0s → 0.3s
        if len(zombies) < max_zom and now - last_spawn > interval:
            spawn_z(); last_spawn = now

        if hp < 100 and now - last_hit > HP_REGEN_WAIT and now - last_regen > HP_REGEN_DT:
            hp = min(100, hp + HP_REGEN_AMT); last_regen = now

        if kl_level >= LEVEL_KILLS: next_maze()
        if combo > 0 and now - last_kill_t > COMBO_WIN: combo = 0

    for b in blood[:]:
        b[0] += b[2] * dt; b[1] += b[3] * dt
        b[2] *= 0.90;      b[3] *= 0.90
        b[4] -= dt
        if b[4] <= 0: blood.remove(b)

    # ── RENDER ────────────────────────────────────────────────────
    buf  = [[' ']*W for _ in range(H)]
    zbuf = [25.0]*W

    for x in range(W):
        ra = ang - FOV/2 + (x/W)*FOV
        d  = cast(M, px, py, ra) * math.cos(ra - ang)
        zbuf[x] = d
        wh  = int(H / (d + 0.1)); top = (H - wh)//2
        si  = max(0, min(len(RAMP)-1, int((1 - d/15) * (len(RAMP)-1))))
        ch  = RAMP[si]
        for y in range(H):
            if y < top:         buf[y][x] = ' '
            elif y < top + wh:  buf[y][x] = ch
            else:
                fy = (y - H/2) / (H/2)
                if   fy > 0.7:  buf[y][x] = ':'
                elif fy > 0.4:  buf[y][x] = '.'
                elif fy > 0.15: buf[y][x] = ','
                else:           buf[y][x] = ' '

    sprites = [(z[0], z[1], 'Z') for z in zombies] + \
              [(p[0], p[1], p[2]) for p in powers]
    sprites.sort(key=lambda s: -((s[0]-px)**2 + (s[1]-py)**2))

    for sx, sy, kind in sprites:
        rx, ry = sx - px, sy - py
        d = math.hypot(rx, ry)
        if d < 0.2: continue
        a = math.atan2(ry, rx) - ang
        a = (a + math.pi) % (2*math.pi) - math.pi
        if abs(a) > FOV/2 + 0.15: continue
        col = int((a/FOV + 0.5) * W)
        sh  = int(H / (d + 0.1))
        sw  = max(1, int(sh * 0.55))
        top = max(0, (H - sh)//2); bot = min(H, top + sh)
        left = col - sw//2;         right = left + sw
        for x in range(max(0, left), min(W, right)):
            if d >= zbuf[x]: continue
            rx_r = (x - left) / max(1, sw)
            touched = False
            for y in range(top, bot):
                ry_r = (y - top) / max(1, sh)
                g = None
                if kind == 'Z':
                    if ry_r < 0.18:
                        if 0.35 < rx_r < 0.65: g = 'o'
                    elif ry_r < 0.72:
                        if 0.18 < rx_r < 0.82: g = 'Z'
                    else:
                        if   rx_r < 0.4: g = '/'
                        elif rx_r > 0.6: g = '\\'
                        else:            g = '|'
                else:
                    if   0.3 < rx_r < 0.7 and 0.3 < ry_r < 0.7:    g = kind
                    elif 0.15 < rx_r < 0.85 and 0.15 < ry_r < 0.85: g = '*'
                if g: buf[y][x] = g; touched = True
            if touched: zbuf[x] = d

    for b in blood:
        bx, by, _, _, life, bch = b
        rx, ry = bx - px, by - py
        d = math.hypot(rx, ry)
        if d < 0.15 or d > 20: continue
        a = math.atan2(ry, rx) - ang
        a = (a + math.pi) % (2*math.pi) - math.pi
        if abs(a) > FOV/2: continue
        col = int((a/FOV + 0.5) * W)
        if 0 <= col < W and d < zbuf[col]:
            sh = int(H / (d + 0.1))
            y = H//2 + int((1.0 - life) * sh * 0.3)
            if 0 <= y < H: buf[y][col] = bch

    if not dead: buf[H//2][W//2] = '+'

    if muzzle > 0:
        cx = W//2
        for dy in range(-2, 1):
            for dx_ in range(-3, 4):
                y, x = H-3+dy, cx+dx_
                if 0 <= y < H and 0 <= x < W and (dy == 0 or abs(dx_) < 2):
                    buf[y][x] = random.choice('*#@%')
        muzzle -= 1

    screen.fill((0, 0, 0))
    for y in range(H):
        line = ''.join(buf[y])
        col  = (200, 200, 200)
        if dead:       col = (120, 30, 30)
        elif hp < 25:  col = (220, 100, 100)
        screen.blit(font.render(line, True, col), (0, y*S))

    if 0 < now - last_hit < 0.25 and not dead:
        a = int(120 * (1 - (now-last_hit)/0.25))
        ov = pygame.Surface((W*S, H*S), pygame.SRCALPHA)
        ov.fill((160, 0, 0, a)); screen.blit(ov, (0, 0))

    # HUD
    hud_col = (120,255,120) if hp>50 else ((255,220,80) if hp>20 else (255,80,80))
    hud = f"HP:{hp:3d}  SPD:{spd_mult:.1f}x  K:{kills}  LVL:{level}  Z:{len(zombies)}  SCORE:{score}"
    if combo >= 2: hud += f"  x{combo} COMBO"
    screen.blit(font.render(hud, True, hud_col), (8, 4))

    # SUBTITLES — announcer captions, bottom-center, auto fade
    if _sub_txt and now < _sub_until:
        remain = _sub_until - now
        alpha  = min(240, int(remain*170)) if remain < 1.4 else 240
        ts = subfnt.render(f"» {_sub_txt}", True, (210, 240, 210))
        ts.set_alpha(alpha)
        tw, th = ts.get_width(), ts.get_height()
        bx = (W*S - tw)//2 - 12; by = H*S - th - 18
        bg = pygame.Surface((tw + 24, th + 10), pygame.SRCALPHA)
        bg.fill((0, 0, 0, min(170, alpha)))
        screen.blit(bg, (bx, by - 5)); screen.blit(ts, (bx + 12, by))

    if dead:
        msg = font.render("YOU DIED — PRESS R TO RESPAWN", True, (255, 60, 60))
        screen.blit(msg, (W*S//2 - msg.get_width()//2, H*S//2))

    pygame.display.flip()

# ── CLEANUP ───────────────────────────────────────────────────────
try: _tts_q.put_nowait(None)
except Exception: pass
pygame.quit(); sys.exit()


