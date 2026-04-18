#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   DOOMFLOW PI  v1.0  —  Pure Python DOOM  ·  tkinter  ·  DDA Raycaster     ║
║   Zero external dependencies  ·  Runs on everything with Python 3.7+       ║
║   W/S=move  A/D=turn  Q/E=strafe  SPACE/F=shoot  1-4=weapon                ║
║   TAB=automap  R=use/door  ESC=menu                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
Based on DOOM by id Software  (Dec 10 1993)
John Carmack · John Romero · Sandy Petersen · Adrian Carmack
"""
import sys, os, math, time, random, struct, wave, io
import threading, subprocess, tempfile, platform
from collections import deque

try:
    import tkinter as tk
except ImportError:
    print("Doomflow requires tkinter.\nLinux: sudo apt-get install python3-tk")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════════════
# §1  AUDIO ENGINE  — PyAmby struct/wave pattern, zero deps
# ═══════════════════════════════════════════════════════════════════════════════
SR   = 22050
TAU  = math.tau
_RNG = random.Random()
_PLAT= platform.system()

def _wav(samples):
    packed = struct.pack(f'<{len(samples)}h',
        *(max(-32767, min(32767, int(s * 32767))) for s in samples))
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(packed)
    return buf.getvalue()

def _play_wav(data):
    if _PLAT == 'Windows':
        try:
            import winsound
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT | winsound.SND_ASYNC)
            return
        except: pass
    path = os.path.join(tempfile.gettempdir(), f'_df_{threading.get_ident()}.wav')
    try:
        with open(path, 'wb') as f: f.write(data)
        if _PLAT == 'Darwin':
            subprocess.Popen(['afplay', path], stderr=subprocess.DEVNULL)
        else:
            for p in ['aplay', 'paplay', 'play']:
                try: subprocess.Popen([p, '-q', path], stderr=subprocess.DEVNULL); return
                except FileNotFoundError: continue
    except: pass

def sfx(name):
    d = _SFX.get(name)
    if d: threading.Thread(target=_play_wav, args=(d,), daemon=True).start()

def _build_sfx():
    g = _RNG.gauss
    def shoot():
        n=int(SR*.14); return [g(0,.55)*math.exp(-i/n*8)+.3*math.sin(TAU*165*i/SR)*math.exp(-i/n*18) for i in range(n)]
    def shotgun():
        n=int(SR*.22); return [g(0,.7)*math.exp(-i/n*5)+.4*math.sin(TAU*100*i/SR)*math.exp(-i/n*10) for i in range(n)]
    def chaingun():
        n=int(SR*.08); return [g(0,.42)*math.exp(-i/n*13)+.22*math.sin(TAU*220*i/SR)*math.exp(-i/n*20) for i in range(n)]
    def hit():
        n=int(SR*.10); return [g(0,.38)*math.exp(-i/n*11) for i in range(n)]
    def death():
        n=int(SR*.45); return [(g(0,.32)+.4*math.sin(TAU*72*i/SR))*math.exp(-i/n*3.2) for i in range(n)]
    def pickup():
        n=int(SR*.16); return [.55*math.sin(TAU*(440+320*i/n)*i/SR)*math.exp(-i/n*2.8) for i in range(n)]
    def step():
        n=int(SR*.055); return [g(0,.32)*math.exp(-i/n*24) for i in range(n)]
    def door():
        n=int(SR*.30); return [.35*(math.sin(TAU*(48+90*i/n)*i/SR)+g(0,.08)) for i in range(n)]
    def pain():
        n=int(SR*.12); return [g(0,.55)*math.exp(-i/n*8) for i in range(n)]
    def beep():
        n=int(SR*.07); return [.4*math.sin(TAU*660*i/SR)*math.exp(-i/n*7) for i in range(n)]
    def lowammo():
        n=int(SR*.05); return [.3*math.sin(TAU*220*i/SR)*math.exp(-i/n*12) for i in range(n)]
    return {k:_wav(v()) for k,v in {
        'shoot':shoot,'shotgun':shotgun,'chaingun':chaingun,
        'hit':hit,'death':death,'pickup':pickup,
        'step':step,'door':door,'pain':pain,'menu':beep,'lowammo':lowammo
    }.items()}

_SFX = _build_sfx()

# ── TTS  (pyttsx3 optional; falls back to OS TTS; graceful silent fail) ────────
_tts = None
def _init_tts():
    global _tts
    try:
        import pyttsx3; e = pyttsx3.init()
        e.setProperty('rate', 148); e.setProperty('volume', .85); _tts = e
    except: pass
threading.Thread(target=_init_tts, daemon=True).start()

def speak(text):
    def _go():
        if _tts:
            try: _tts.say(text); _tts.runAndWait(); return
            except: pass
        try:
            if _PLAT == 'Darwin': subprocess.run(['say', '-r','145', text], timeout=14, capture_output=True)
            elif _PLAT == 'Windows': subprocess.run(['powershell','-c', f'Add-Type -A System.Speech;(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{text}")'], timeout=14, capture_output=True)
            else: subprocess.run(['espeak','-s','140', text], timeout=14, capture_output=True)
        except: pass
    threading.Thread(target=_go, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════════════════
# §2  LEVELS  — 3 hand-crafted E1 maps
# ═══════════════════════════════════════════════════════════════════════════════
# Tile legend:
#  # M R = solid walls (brick / metal / red)   D = closed door
#  P = player start    X = exit
#  Z = zombie (20hp)   I = imp (60hp)   N = demon/pinky (150hp)
#  + = bullets (10)    h = stim(+10hp)  H = medikit(+25hp)
#  a = armor shard     A = green armor  S = shotgun   G = chaingun

LEVELS = [
# ── E1M1: Hangar ──────────────────────────────────────────────────────────────
"""
########################
#P....Z.....#..........#
#...........#....ZZZZ..#
#...........#..........#
#..######...#...#####..#
#...........MMM.#...#..#
#...........M...#...D..X
#...........MMM.#...#..#
#..######...#...#####..#
#....h.......h..H......#
#..........+.+.........#
#...........#..........#
#..######...#...A......#
#..#.........I..ZZZ....#
#..#R........#...#.....#
#..#RRRR.....#...#..I..#
#..#R........#...#.....#
#..######....#...#.....#
#...........Z#...######
########################
""",
# ── E1M2: Nuclear Plant ───────────────────────────────────────────────────────
"""
##############################
#P.........................##.#
#..MMMMMM..###..MMMMMM..#....#
#..M......Z#.#Z.......M.#....#
#..M..##...#.#...##...M.#....#
#..MMMMMM..#.#..MMMMMM..#....#
#..........#.#..........#....#
##.########D.D########..#....#
#..#....R..#.#..R....#..#....#
#..#.RR.R..#.#..R.RR.#..I....#
#..#....R..#.#..R....#..#....#
##.########D.D########..#....#
#..........#.#..........S....#
#..MMMMMM..#.#..MMMMMM..#....#
#..M.HHHH.Z#.#Z+.++...M.#....#
#..M......Z#.#Z.......M.#....#
#..MMMMMM..#.#..MMMMMM..#....#
#..........#.#..........#....#
#..####NNNN#.#NNNN####..#....#
#.................h......#....#
##########D..D########..#....#
#..A.......................G..#
#.............I.......I..X...#
##############################
""",
# ── E1M3: Toxin Refinery ──────────────────────────────────────────────────────
"""
##################################
#P..............................##
#.MMMMMMMMMMMMMMMMMMMMMMMMMM....##
#.M......................M......##
#.M..RRRRRRRRRRRRRRRR...M......##
#.M..R..............R...M......##
#.M..R..ZZ.....IIN..R...M......##
#.M..R..............R...M......##
#.M..RRRR####RRRRRRR....M......##
#.M......Z#..#Z.........M..S...##
#.M......Z#..#Z.........M......##
#.MMMMMMM#....#MMMMMMMMM.......##
#........D....D................##
#.MMMMMMM#....#MMMMMMMMM.......##
#.M......N#..#N.........M......##
#.M......N#..#N.........M..G...##
#.M..RRRR####RRRRRRR....M......##
#.M..R..............R...M......##
#.M..R...NNN...NNN..R...M..A...##
#.M..R..............R...M......##
#.M..RRRRRRRRRRRRRRRR...M......##
#.M.........H...........M......##
#.MMMMMMMMMMMMMMMMMMMMMM.......##
#.H..HHH..++.++.AA...........X.#
##################################
""",
]

LEVEL_NAMES = ["E1M1: Hangar", "E1M2: Nuclear Plant", "E1M3: Toxin Refinery"]
LEVEL_LORE  = [
    "UAC Phobos Base — all radio contact lost. You are the last marine standing.",
    "The processing plant hums with something that isn't machinery. Push deeper.",
    "Toxic corridors. Demonic reinforcements. The portal is somewhere ahead.",
]

# ═══════════════════════════════════════════════════════════════════════════════
# §3  GAME CONSTANTS  (authentic DOOM id Software values)
# ═══════════════════════════════════════════════════════════════════════════════
MAXHEALTH   = 100
MAXARMOR    = 200
FOV         = math.pi / 2.8     # ~64°
MAX_DEPTH   = 24
MOVE_SPD    = 0.090
STRAFE_SPD  = 0.072
ROT_SPD     = 0.058
PICKUP_R2   = 0.60 ** 2
ENEMY_ALERT = 7.5               # sight radius
MELEE_RANGE = 1.45
BULLET_RANGE= 14.0
SIDE_DIM    = 0.55              # N/S wall darkening, matches DOOM feel

# WEAPONS: name, dmg_min, dmg_max, pellets, fire_delay, ammo_cost, ammo_type, sfx
WEAPONS = {
    0: ('FIST',     2, 20, 1, 0.48, 0, None,      'hit'),
    1: ('PISTOL',   5, 15, 1, 0.27, 1, 'bullets',  'shoot'),
    2: ('SHOTGUN',  5, 15, 7, 0.68, 1, 'shells',   'shotgun'),
    3: ('CHAINGUN', 5, 15, 1, 0.09, 1, 'bullets',  'chaingun'),
}

# ENEMIES: name, hp, speed, dps, pts, color_rgb, sprite_scale
ENEMIES = {
    'Z': ('ZOMBIE',  20, 0.010,  5.0, 100, (190,165,140), 0.85),
    'I': ('IMP',     60, 0.013,  9.0, 200, (168, 80, 38), 1.00),
    'N': ('DEMON',  150, 0.016, 19.0, 400, (210,100,165), 1.20),
}

# PICKUPS: name, hp, armor, bullets, shells, weapon_unlock
PICKUPS = {
    'h': ('STIM',    10,   0,  0, 0, -1),
    'H': ('MEDIKIT', 25,   0,  0, 0, -1),
    'a': ('SHARD',    0,   1,  0, 0, -1),
    'A': ('ARMOR',    0, 100,  0, 0, -1),
    '+': ('BULLETS',  0,   0, 10, 0, -1),
    'S': ('SHOTGUN',  0,   0,  0, 8,  2),
    'G': ('CHAINGUN', 0,   0, 20, 0,  3),
}

# Wall base colors RGB
WALL_RGB = {
    '#': (178, 118, 62),
    'M': (118, 122, 132),
    'R': (148,  38, 38),
    'D': ( 88, 130, 88),
}
SOLID_TILES = set('#MRD')

# Ceiling / floor gradient anchors (RGB)
CEIL_TOP  = ( 2,  2, 18)
CEIL_BOT  = (10, 10, 36)
FLR_TOP   = (12, 10,  5)
FLR_BOT   = (28, 22, 10)

# View dimensions
VIEW_W  = 800
VIEW_H  = 480
HUD_H   = 44
COLS    = 160           # ray columns
COL_W   = VIEW_W // COLS   # 5 px / column
MAX_SPR = 32

# ═══════════════════════════════════════════════════════════════════════════════
# §4  GAME STATE
# ═══════════════════════════════════════════════════════════════════════════════
class Player:
    __slots__ = ('x','y','ang','hp','armor','ammo','weapon','weapons_owned',
                 'kills','score','fire_t','hurt_t','step_acc','bob')
    def __init__(self):
        self.x=self.y=1.5; self.ang=0.0
        self.hp=100; self.armor=0
        self.ammo={'bullets':50,'shells':0}
        self.weapon=1; self.weapons_owned={0,1}
        self.kills=0; self.score=0
        self.fire_t=self.hurt_t=self.step_acc=self.bob=0.0

class Enemy:
    __slots__=('x','y','kind','hp','alert','dmg_acc','dead_t')
    def __init__(self,x,y,kind):
        self.x=x; self.y=y; self.kind=kind
        self.hp=ENEMIES[kind][1]; self.alert=False
        self.dmg_acc=0.0; self.dead_t=0.0

class Pickup:
    __slots__=('x','y','kind','alive')
    def __init__(self,x,y,kind): self.x=x; self.y=y; self.kind=kind; self.alive=True

class Level:
    def __init__(self, raw):
        rows = [r for r in raw.strip().split('\n') if r.strip()]
        self.rows = rows; self.H = len(rows); self.W = max(len(r) for r in rows)
        self.player  = Player()
        self.enemies : list[Enemy]  = []
        self.pickups : list[Pickup] = []
        self.doors   : dict         = {}
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if   c == 'P': self.player.x, self.player.y = x+.5, y+.5
                elif c == 'D': self.doors[(x,y)] = False
                elif c in ENEMIES: self.enemies.append(Enemy(x+.5, y+.5, c))
                elif c in PICKUPS: self.pickups.append(Pickup(x+.5, y+.5, c))

    def tile(self, x, y):
        mx,my = int(x),int(y)
        if 0<=mx<self.W and 0<=my<self.H and mx<len(self.rows[my]):
            return self.rows[my][mx]
        return '#'

    def is_solid(self, x, y):
        return self.tile(x,y) in SOLID_TILES

    def wall_rgb(self, x, y):
        return WALL_RGB.get(self.tile(x,y), WALL_RGB['#'])

    def open_door(self, x, y):
        row = list(self.rows[y]); row[x] = ' '; self.rows[y] = ''.join(row)
        self.doors.pop((x,y), None); sfx('door')

# ═══════════════════════════════════════════════════════════════════════════════
# §5  DDA RAYCASTER  (perpendicular distance, fisheye-free)
# ═══════════════════════════════════════════════════════════════════════════════
def cast_ray(lv, px, py, ray_ang):
    ca = math.cos(ray_ang); sa = math.sin(ray_ang)
    if abs(ca)<1e-9: ca=1e-9
    if abs(sa)<1e-9: sa=1e-9
    mx,my = int(px),int(py)
    ddx,ddy = abs(1/ca),abs(1/sa)
    sx = 1 if ca>0 else -1; sy = 1 if sa>0 else -1
    sdx=(mx+(1 if ca>0 else 0)-px)/ca; sdy=(my+(1 if sa>0 else 0)-py)/sa
    side=0
    for _ in range(MAX_DEPTH*3):
        if sdx<sdy: sdx+=ddx; mx+=sx; side=0
        else:       sdy+=ddy; my+=sy; side=1
        c = lv.tile(mx,my)
        if c in SOLID_TILES:
            perp = ((mx-px+(1-sx)*.5)/ca if side==0 else (my-py+(1-sy)*.5)/sa)
            return max(perp,0.01), side, lv.wall_rgb(mx,my)
    return float(MAX_DEPTH), 0, WALL_RGB['#']

# ═══════════════════════════════════════════════════════════════════════════════
# §6  PHYSICS / COMBAT / AI
# ═══════════════════════════════════════════════════════════════════════════════
def slide_move(lv, px, py, dx, dy):
    nx,ny=px+dx,py+dy
    rx = nx if not lv.is_solid(nx,py) else px
    ry = ny if not lv.is_solid(rx,ny) else py
    return rx,ry

def do_use(lv, pl):
    reach=1.9
    ax=pl.x+math.cos(pl.ang)*reach; ay=pl.y+math.sin(pl.ang)*reach
    mx,my=int(ax),int(ay)
    if (mx,my) in lv.doors: lv.open_door(mx,my)

def do_shoot(lv, pl):
    wdat = WEAPONS[pl.weapon]
    _,dmin,dmax,pellets,fdelay,cost,atype,sfxname = wdat
    if atype and pl.ammo.get(atype,0)<cost:
        sfx('lowammo'); return
    if atype: pl.ammo[atype] -= cost
    pl.fire_t = fdelay; sfx(sfxname)
    cone = 0.20/max(pellets,1)
    for _ in range(pellets):
        spread = _RNG.uniform(-cone,cone) if pellets>1 else 0.0
        sang = pl.ang + spread
        best,hit = BULLET_RANGE,None
        for e in lv.enemies:
            if e.hp<=0: continue
            dx,dy=e.x-pl.x,e.y-pl.y; d=math.sqrt(dx*dx+dy*dy)
            if d>BULLET_RANGE: continue
            da=(math.atan2(dy,dx)-sang+math.pi)%(TAU)-math.pi
            if abs(da)<0.22 and d<best: best,hit=d,e
        if hit:
            hit.hp -= _RNG.randint(dmin,dmax); hit.alert=True
            if hit.hp<=0:
                hit.dead_t=1.2
                pl.kills+=1; pl.score+=ENEMIES[hit.kind][4]; sfx('death')
            else: sfx('hit')

def damage_player(pl, dmg):
    if pl.armor>0:
        absorb=min(dmg*pl.armor//200, dmg); pl.armor=max(0,pl.armor-absorb*2); dmg-=absorb
    pl.hp=max(0,pl.hp-dmg); pl.hurt_t=0.38; sfx('pain')

def update_enemies(lv, pl, dt):
    for e in lv.enemies:
        if e.hp<=0:
            if e.dead_t>0: e.dead_t=max(0,e.dead_t-dt)
            continue
        _,_,spd,dps,*_ = ENEMIES[e.kind]
        dx,dy=e.x-pl.x,e.y-pl.y; d=math.sqrt(dx*dx+dy*dy)
        if d<ENEMY_ALERT: e.alert=True
        if e.alert and d>0.55:
            s=spd*min(2.8,3.5/max(d,.5))
            ex=e.x-(dx/d)*s; ey=e.y-(dy/d)*s
            if not lv.is_solid(ex,e.y): e.x=ex
            if not lv.is_solid(e.x,ey): e.y=ey
        if e.alert and d<MELEE_RANGE:
            e.dmg_acc+=dps*dt
            n=int(e.dmg_acc)
            if n>0: damage_player(pl,n); e.dmg_acc-=n

def update_pickups(lv, pl):
    for p in lv.pickups:
        if not p.alive: continue
        dx,dy=p.x-pl.x,p.y-pl.y
        if dx*dx+dy*dy<PICKUP_R2:
            _,hp,arm,bul,sh,wid=PICKUPS[p.kind]
            pl.hp   = min(MAXHEALTH, pl.hp+hp)
            pl.armor= min(MAXARMOR,  pl.armor+arm)
            pl.ammo['bullets'] = min(300, pl.ammo['bullets']+bul)
            pl.ammo['shells']  = min(50,  pl.ammo.get('shells',0)+sh)
            if wid>=0: pl.weapons_owned.add(wid); pl.weapon=wid
            p.alive=False; sfx('pickup')

# ═══════════════════════════════════════════════════════════════════════════════
# §7  RENDERER  (tkinter Canvas + pre-allocated rect items)
# ═══════════════════════════════════════════════════════════════════════════════
def _rgb(r,g,b): return f"#{int(max(0,min(255,r))):02x}{int(max(0,min(255,g))):02x}{int(max(0,min(255,b))):02x}"
def _lerp3(a,b,t): return (a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]),a[2]+t*(b[2]-a[2]))
def _shade(rgb,dist,side): f=max(.07,1-dist/MAX_DEPTH)*(SIDE_DIM if side else 1.); return _rgb(*(c*f for c in rgb))

GUN_IDLE  = {'FIST':"   | |\n   | |\n___|_|___",'PISTOL':"   |_|\n   | |\n___|_|___",'SHOTGUN':"  =====\n   | |\n___|_|_____",'CHAINGUN':"  ======\n  |  |\n__|__|____"}
GUN_FIRE  = {'FIST':"  \\  /\n   ==\n  /  \\",'PISTOL':"  _|_\n  |#|\n__|_|__",'SHOTGUN':" ===*=\n  |*|\n__|_|____",'CHAINGUN':"=======\n  |##|\n__|##|____"}

class Renderer:
    def __init__(self, cv):
        self.cv=cv; half=VIEW_H//2
        # Column rects: ceil / wall / floor
        self._cr,self._wr,self._fr=[],[],[]
        for c in range(COLS):
            x1,x2=c*COL_W,(c+1)*COL_W
            self._cr.append(cv.create_rectangle(x1,0,   x2,half,fill='#02020e',outline=''))
            self._wr.append(cv.create_rectangle(x1,half,x2,half,fill='#7a5e2a',outline=''))
            self._fr.append(cv.create_rectangle(x1,half,x2,VIEW_H,fill='#0e0b04',outline=''))
        # Sprite rects
        self._spr=[cv.create_rectangle(0,0,0,0,fill='#cc2200',outline='#ff4422') for _ in range(MAX_SPR)]
        # Crosshair
        cx,cy=VIEW_W//2,VIEW_H//2
        self._xh=cv.create_line(cx-12,cy,cx+12,cy,fill='#cccccc',width=1)
        self._xv=cv.create_line(cx,cy-9,cx,cy+9,fill='#cccccc',width=1)
        # Gun sprite
        self._gun=cv.create_text(VIEW_W//2,VIEW_H-60,text='',fill='#aaaaaa',font=('Courier',10,'bold'),anchor='center')
        # Message overlay
        self._msg=cv.create_text(VIEW_W//2,36,text='',fill='#00ff88',font=('Courier',13,'bold'),anchor='center')
        # Hurt flash
        self._hurt=cv.create_rectangle(0,0,VIEW_W,VIEW_H,fill='#bb0000',outline='',state='hidden')
        try: cv.itemconfig(self._hurt,stipple='gray25')
        except: pass
        # Minimap bg
        self._mm_bg=cv.create_rectangle(VIEW_W-102,4,VIEW_W-4,92,fill='#070707',outline='#222222')
        self._mm_pl=cv.create_oval(0,0,2,2,fill='#00ff88',outline='')
        self._mm_di=cv.create_line(0,0,1,1,fill='#00ff88',width=1)
        self._mm_shown=False

    def draw(self, lv, pl, zbuf, msg, show_map):
        cv=self.cv; half=VIEW_H//2

        # ── Walls / ceil / floor ────────────────────────────────────────────
        for col in range(COLS):
            ra = pl.ang - FOV*.5 + FOV*col/COLS
            dist,side,wrgb = cast_ray(lv,pl.x,pl.y,ra)
            zbuf[col]=dist
            bob=int(math.sin(pl.bob)*2)
            wh=min(int(VIEW_H/max(dist,.01)),VIEW_H)
            top=max((VIEW_H-wh)>>1,0)+bob; bot=min(top+wh,VIEW_H-1)
            x1,x2=col*COL_W,(col+1)*COL_W
            # ceiling
            ct=max(0.,min(1.,(top/half) if top>0 else 0.))
            cv.coords(self._cr[col],x1,0,x2,max(top,1))
            cv.itemconfig(self._cr[col],fill=_rgb(*_lerp3(CEIL_TOP,CEIL_BOT,ct)))
            # wall
            cv.coords(self._wr[col],x1,top,x2,bot)
            cv.itemconfig(self._wr[col],fill=_shade(wrgb,dist,side))
            # floor
            ft=max(0.,min(1.,(VIEW_H-bot)/max(VIEW_H-half,1)))
            cv.coords(self._fr[col],x1,bot,x2,VIEW_H)
            cv.itemconfig(self._fr[col],fill=_rgb(*_lerp3(FLR_TOP,FLR_BOT,ft)))

        # ── Sprites ─────────────────────────────────────────────────────────
        sprites=[]
        for e in lv.enemies:
            dx,dy=e.x-pl.x,e.y-pl.y
            if e.hp>0:
                rgb=ENEMIES[e.kind][5]; col=(200,50,50) if e.alert else rgb
                sprites.append((dx*dx+dy*dy,dx,dy,_rgb(*col),'#ff4422',ENEMIES[e.kind][6]))
            elif e.dead_t>0:
                sprites.append((dx*dx+dy*dy,dx,dy,'#3a1508','#2a1005',.35))
        for p in lv.pickups:
            if p.alive:
                dx,dy=p.x-pl.x,p.y-pl.y
                c={'h':'#00aaff','H':'#0055ff','+':'#ffcc00','a':'#44ff44','A':'#22cc22','S':'#ff8800','G':'#ff4400'}.get(p.kind,'#888888')
                sprites.append((dx*dx+dy*dy,dx,dy,c,'#ffffff',.55))
        sprites.sort(reverse=True)
        zlen=len(zbuf)
        for r in self._spr: cv.coords(r,0,0,0,0)
        for si,(d2,dx,dy,fill,out,sz) in enumerate(sprites):
            if si>=MAX_SPR: break
            dist=math.sqrt(d2)
            if dist<.35: continue
            ra=(math.atan2(dy,dx)-pl.ang+math.pi)%TAU-math.pi
            if abs(ra)>FOV*.58: continue
            sx=int((ra/FOV+.5)*COLS)
            if not(0<=sx<COLS and sx<zlen) or zbuf[sx]<=dist: continue
            spH=min(int(VIEW_H*sz/max(dist,.01)),VIEW_H-2)
            spW=max(int(spH*COL_W//5),COL_W*2)
            pxc=sx*COL_W+COL_W//2; ty=max(half-spH//2,0); by=min(half+spH//2,VIEW_H-2)
            cv.coords(self._spr[si],pxc-spW//2,ty,pxc+spW//2,by)
            cv.itemconfig(self._spr[si],fill=fill,outline=out)

        # ── Gun ──────────────────────────────────────────────────────────────
        wname=WEAPONS[pl.weapon][0]
        if pl.fire_t>0:
            cv.itemconfig(self._gun,text=GUN_FIRE.get(wname,'|*|'),fill='#ff6622')
        else:
            cv.itemconfig(self._gun,text=GUN_IDLE.get(wname,'| |'),fill='#999999')

        # ── Crosshair ────────────────────────────────────────────────────────
        xc='#ff4400' if pl.fire_t>0 else '#cccccc'
        cv.itemconfig(self._xh,fill=xc); cv.itemconfig(self._xv,fill=xc)
        # ── Hurt flash ────────────────────────────────────────────────────────
        cv.itemconfig(self._hurt,state='normal' if pl.hurt_t>0 else 'hidden')
        # ── Message ───────────────────────────────────────────────────────────
        cv.itemconfig(self._msg,text=msg)

        # ── Minimap ───────────────────────────────────────────────────────────
        if show_map:
            cv.itemconfig(self._mm_bg,state='normal')
            cv.itemconfig(self._mm_pl,state='normal')
            cv.itemconfig(self._mm_di,state='normal')
            MM=5; mmx=VIEW_W-102; mmy=6
            ppx=mmx+int(pl.x*MM); ppy=mmy+int(pl.y*MM)
            cv.coords(self._mm_pl,ppx-2,ppy-2,ppx+2,ppy+2)
            cv.coords(self._mm_di,ppx,ppy,ppx+int(math.cos(pl.ang)*MM*2),ppy+int(math.sin(pl.ang)*MM*2))
        else:
            cv.itemconfig(self._mm_bg,state='hidden')
            cv.itemconfig(self._mm_pl,state='hidden')
            cv.itemconfig(self._mm_di,state='hidden')

# ═══════════════════════════════════════════════════════════════════════════════
# §8  DIALOGUE BOX
# ═══════════════════════════════════════════════════════════════════════════════
class DialogueBox:
    def __init__(self, cv):
        self.cv=cv; self.active=False
        self._bg  =cv.create_rectangle(38,VIEW_H-138,VIEW_W-38,VIEW_H-6,fill='#08081a',outline='#3355bb',width=2,state='hidden')
        self._txt =cv.create_text(VIEW_W//2,VIEW_H-86,text='',fill='#cce0ff',font=('Courier',11),anchor='center',width=VIEW_W-100,state='hidden')
        self._cont=cv.create_text(VIEW_W//2,VIEW_H-20,text='Press SPACE or ENTER to continue',fill='#334477',font=('Courier',9),anchor='center',state='hidden')

    def show(self, text, voice=True):
        self.active=True
        for i in (self._bg,self._txt,self._cont): self.cv.itemconfig(i,state='normal')
        self.cv.itemconfig(self._txt,text=text)
        if voice: speak(text)

    def hide(self):
        self.active=False
        for i in (self._bg,self._txt,self._cont): self.cv.itemconfig(i,state='hidden')

# ═══════════════════════════════════════════════════════════════════════════════
# §9  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
TITLE_ART="""
 ██████╗  ██████╗  ██████╗ ███╗   ███╗███████╗██╗      ██████╗ ██╗    ██╗
 ██╔══██╗██╔═══██╗██╔═══██╗████╗ ████║██╔════╝██║     ██╔═══██╗██║    ██║
 ██║  ██║██║   ██║██║   ██║██╔████╔██║█████╗  ██║     ██║   ██║██║ █╗ ██║
 ██║  ██║██║   ██║██║   ██║██║╚██╔╝██║██╔══╝  ██║     ██║   ██║██║███╗██║
 ██████╔╝╚██████╔╝╚██████╔╝██║ ╚═╝ ██║██║     ███████╗╚██████╔╝╚███╔███╔╝
 ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝
                                PI  v1.0"""

class DoomflowPi:
    def __init__(self,root):
        self.root=root
        root.title("DOOMFLOW PI v1.0"); root.configure(bg='#000')
        root.resizable(False,False); root.geometry(f"{VIEW_W}x{VIEW_H+HUD_H}")
        self.cv=tk.Canvas(root,width=VIEW_W,height=VIEW_H,bg='#000',highlightthickness=0,cursor='none')
        self.cv.pack()
        hf=tk.Frame(root,bg='#0d0d0d',height=HUD_H); hf.pack(fill='x'); hf.pack_propagate(False)
        self._hudv=tk.StringVar(value=''); self._hudl=tk.Label(hf,textvariable=self._hudv,bg='#0d0d0d',fg='#00ff44',font=('Courier',11,'bold'),anchor='w'); self._hudl.pack(fill='x',padx=10,pady=7)
        # State
        self.state='title'; self.lv=None; self.pl=None; self.level_idx=0
        self.zbuf=[0.0]*COLS; self.renderer=None; self.dlg=None
        self.keys=set(); self.last_t=time.perf_counter()
        self.msg=''; self.msg_t=0.0; self.show_map=False
        self._msel=0; self._mitems=[]; self._mtxt=[]
        self._next_lvl_pending=False
        root.bind('<KeyPress>',self._kp); root.bind('<KeyRelease>',self._kr)
        root.protocol('WM_DELETE_WINDOW',self._quit); root.focus_set()
        self._title(); root.after(16,self._loop)

    # ── Screens ─────────────────────────────────────────────────────────────
    def _title(self):
        cv=self.cv; cv.delete('all'); self.state='title'; sfx('menu')
        cv.create_rectangle(0,0,VIEW_W,VIEW_H,fill='#000',outline='')
        cv.create_text(VIEW_W//2,130,text=TITLE_ART,fill='#cc2200',font=('Courier',7,'bold'),anchor='center',justify='center')
        cv.create_text(VIEW_W//2,256,text="December 10, 1993",fill='#332211',font=('Courier',9),anchor='center')
        self._mitems=["NEW GAME","ABOUT","QUIT"]; self._msel=0; self._mtxt=[]
        for i,itm in enumerate(self._mitems):
            t=cv.create_text(VIEW_W//2,305+i*40,text=itm,fill='#ff2200' if i==0 else '#884422',font=('Courier',16,'bold'),anchor='center')
            self._mtxt.append(t)
        cv.create_text(VIEW_W//2,VIEW_H-16,text="W/S = select    ENTER/SPACE = confirm",fill='#333',font=('Courier',9),anchor='center')
        self._hudv.set("  DOOMFLOW PI v1.0  —  id Software  Dec 10 1993"); self._hudl.config(fg='#cc4400')

    def _about(self):
        cv=self.cv; cv.delete('all')
        cv.create_rectangle(0,0,VIEW_W,VIEW_H,fill='#000',outline='')
        lines=["DOOMFLOW PI v1.0","","Pure Python DOOM recreation · Dec 10 1993","","DDA raycasting · 3 E1 levels · 4 weapons · 3 enemy types",
               "Authentic id Software damage/speed values","Procedural audio synthesis · TTS narration · Zero dependencies","",
               "id Software: John Carmack · John Romero · Sandy Petersen","","Press ESC or SPACE to return"]
        for i,l in enumerate(lines):
            col='#ff4400' if i==0 else '#00aa55' if i==2 else '#555555'
            cv.create_text(VIEW_W//2,90+i*30,text=l,fill=col,font=('Courier',11,'bold' if i<3 else 'normal'),anchor='center')
        self.state='about'; speak("DOOMFLOW PI. Pure Python DOOM. Zero dependencies. December 10 1993.")

    def _msel_update(self):
        for i,t in enumerate(self._mtxt):
            self.cv.itemconfig(t,fill='#ff2200' if i==self._msel else '#884422')
        sfx('menu')

    def _menu_confirm(self):
        sel=self._mitems[self._msel]
        if sel=="NEW GAME": self._start(0)
        elif sel=="ABOUT": self._about()
        elif sel=="QUIT": self._quit()

    def _start(self, idx):
        self.level_idx=idx; self.lv=Level(LEVELS[idx]); self.pl=self.lv.player
        self.cv.delete('all'); self.renderer=Renderer(self.cv)
        self.dlg=DialogueBox(self.cv)
        self.zbuf=[0.0]*COLS; self.show_map=False; self.state='game'
        self._next_lvl_pending=False
        lore=LEVEL_LORE[idx]; self.msg=LEVEL_NAMES[idx]+' — '+lore; self.msg_t=4.5
        speak(lore); sfx('door')
        self._hudv.set(''); self._hudl.config(fg='#00ff44')

    def _game_over(self):
        cv=self.cv; cv.delete('all')
        cv.create_rectangle(0,0,VIEW_W,VIEW_H,fill='#000',outline='')
        cv.create_text(VIEW_W//2,170,text="YOU DIED",fill='#cc2200',font=('Courier',52,'bold'),anchor='center')
        cv.create_text(VIEW_W//2,270,text=f"Score: {self.pl.score}   Kills: {self.pl.kills}",fill='#888',font=('Courier',14),anchor='center')
        cv.create_text(VIEW_W//2,330,text="R = retry level    ESC = title",fill='#444',font=('Courier',12),anchor='center')
        self.state='dead'; speak("You died. Press R to retry.")
        self._hudv.set(f"  DEAD  —  Score: {self.pl.score}  Kills: {self.pl.kills}"); self._hudl.config(fg='#cc2200')

    def _victory(self):
        cv=self.cv; cv.delete('all')
        cv.create_rectangle(0,0,VIEW_W,VIEW_H,fill='#000',outline='')
        cv.create_text(VIEW_W//2,160,text="MISSION COMPLETE",fill='#00ff44',font=('Courier',36,'bold'),anchor='center')
        cv.create_text(VIEW_W//2,250,text="Knee Deep in the Dead — CLEARED",fill='#00aa44',font=('Courier',16),anchor='center')
        cv.create_text(VIEW_W//2,300,text=f"Final Score: {self.pl.score}   Total Kills: {self.pl.kills}",fill='#ffffff',font=('Courier',14),anchor='center')
        cv.create_text(VIEW_W//2,360,text="R = new game    ESC = title",fill='#555',font=('Courier',12),anchor='center')
        self.state='victory'; speak(f"Mission complete. Score {self.pl.score}. {self.pl.kills} kills. Well done, marine.")
        self._hudv.set(f"  VICTORY  —  Score: {self.pl.score}  Kills: {self.pl.kills}"); self._hudl.config(fg='#00ff44')

    def _show_notif(self, text, t=3.0): self.msg=text; self.msg_t=t

    # ── Pause overlay ────────────────────────────────────────────────────────
    def _pause(self):
        cv=self.cv
        cv.create_rectangle(220,140,580,320,fill='#08080f',outline='#333355',width=2,tags='pause')
        cv.create_text(VIEW_W//2,170,text="— PAUSED —",fill='#ff4422',font=('Courier',18,'bold'),anchor='center',tags='pause')
        self._pitems=["RESUME","RESTART","TITLE"]; self._psel=0; self._ptxt=[]
        for i,o in enumerate(self._pitems):
            t=cv.create_text(VIEW_W//2,210+i*32,text=o,fill='#ff2200' if i==0 else '#664422',font=('Courier',13,'bold'),anchor='center',tags='pause')
            self._ptxt.append(t)
        self.state='pause'; sfx('menu')

    def _psel_update(self):
        for i,t in enumerate(self._ptxt):
            self.cv.itemconfig(t,fill='#ff2200' if i==self._psel else '#664422')
        sfx('menu')

    def _pause_confirm(self):
        o=self._pitems[self._psel]; self.cv.delete('pause')
        if o=="RESUME": self.state='game'; sfx('menu')
        elif o=="RESTART": self._start(self.level_idx)
        elif o=="TITLE": self._title()

    # ── Input ────────────────────────────────────────────────────────────────
    def _kp(self,ev):
        k=ev.keysym.lower(); self.keys.add(k)
        s=self.state
        if s=='title':
            if k in('w','up'):   self._msel=max(0,self._msel-1);      self._msel_update()
            elif k in('s','down'): self._msel=min(len(self._mitems)-1,self._msel+1); self._msel_update()
            elif k in('return','space'): self._menu_confirm()
            elif k=='escape': self._quit()
        elif s=='about':
            if k in('escape','space','return'): self._title()
        elif s=='game':
            if k=='escape': self._pause()
            elif k=='tab': self.show_map=not self.show_map
            elif k=='r': do_use(self.lv,self.pl)
            elif k in('space','f') and self.pl.fire_t<=0: do_shoot(self.lv,self.pl)
            elif k=='1': self.pl.weapon=0
            elif k=='2' and 1 in self.pl.weapons_owned: self.pl.weapon=1
            elif k=='3' and 2 in self.pl.weapons_owned: self.pl.weapon=2
            elif k=='4' and 3 in self.pl.weapons_owned: self.pl.weapon=3
        elif s=='pause':
            if k in('w','up'):   self._psel=max(0,self._psel-1);              self._psel_update()
            elif k in('s','down'): self._psel=min(len(self._pitems)-1,self._psel+1); self._psel_update()
            elif k in('return','space'): self._pause_confirm()
            elif k=='escape': self.cv.delete('pause'); self.state='game'; sfx('menu')
        elif s=='dialogue':
            if k in('space','return','escape'):
                self.dlg.hide(); self.state='game'
                if self._next_lvl_pending:
                    self._next_lvl_pending=False
                    if self.level_idx>=len(LEVELS): self._victory()
                    else: self._start(self.level_idx)
        elif s in('dead','victory'):
            if k=='r': self._start(self.level_idx if s=='dead' else 0)
            elif k=='escape': self._title()

    def _kr(self,ev): self.keys.discard(ev.keysym.lower())
    def _quit(self):
        try: self.root.destroy()
        except: pass

    # ── Main loop ────────────────────────────────────────────────────────────
    def _loop(self):
        if not self.root.winfo_exists(): return
        now=time.perf_counter(); dt=min(now-self.last_t,.1); self.last_t=now

        if self.state=='game' and self.pl:
            pl=self.pl; lv=self.lv
            pl.fire_t=max(0.,pl.fire_t-dt); pl.hurt_t=max(0.,pl.hurt_t-dt)
            self.msg_t=max(0.,self.msg_t-dt)
            K=self.keys; ca=math.cos(pl.ang); sa=math.sin(pl.ang)
            moved=False
            if 'w' in K or 'up'    in K: pl.x,pl.y=slide_move(lv,pl.x,pl.y, ca*MOVE_SPD*2,   sa*MOVE_SPD*2);  moved=True
            if 's' in K or 'down'  in K: pl.x,pl.y=slide_move(lv,pl.x,pl.y,-ca*MOVE_SPD*1.4,-sa*MOVE_SPD*1.4);moved=True
            if 'a' in K or 'left'  in K: pl.ang-=ROT_SPD*2
            if 'd' in K or 'right' in K: pl.ang+=ROT_SPD*2
            if 'q' in K: pl.x,pl.y=slide_move(lv,pl.x,pl.y, sa*STRAFE_SPD,-ca*STRAFE_SPD); moved=True
            if 'e' in K: pl.x,pl.y=slide_move(lv,pl.x,pl.y,-sa*STRAFE_SPD, ca*STRAFE_SPD); moved=True
            if 'f' in K and pl.fire_t<=0: do_shoot(lv,pl)
            if moved:
                pl.step_acc+=dt; pl.bob+=dt*4.5
                if pl.step_acc>=0.40: pl.step_acc=0; sfx('step')
            else: pl.bob*=0.82
            update_enemies(lv,pl,dt); update_pickups(lv,pl)
            # Exit check
            if lv.tile(pl.x,pl.y)=='X' and not self._next_lvl_pending:
                self._next_lvl_pending=True
                self.level_idx+=1
                if self.level_idx>=len(LEVELS):
                    dlg_text="All levels cleared! Mission complete. You are the last marine."
                else:
                    dlg_text=f"{LEVEL_NAMES[self.level_idx]} — {LEVEL_LORE[self.level_idx]}"
                self.state='dialogue'; self.dlg.show(dlg_text,voice=True)
            # Death
            if pl.hp<=0: self._game_over(); self.root.after(max(1,int((0.016-(time.perf_counter()-now))*1000)),self._loop); return
            # Render
            self.renderer.draw(lv,pl,self.zbuf,self.msg if self.msg_t>0 else '',self.show_map)
            # HUD
            hp=max(pl.hp,0); bw=20; filled=hp*bw//100
            bar='\u2588'*filled+'\u2591'*(bw-filled)
            wdat=WEAPONS[pl.weapon]; wname=wdat[0]; atype=wdat[6]
            ac=pl.ammo.get(atype,0) if atype else '-'
            self._hudv.set(f"  HP[{bar}]{hp:3d}  ARM:{pl.armor:3d}  {wname}:{ac}  SCORE:{pl.score:6d}  K:{pl.kills}/{len(lv.enemies)}")
            self._hudl.config(fg='#ff2200' if pl.hurt_t>0 else '#00ff44')

        self.root.after(max(1,int((0.016-(time.perf_counter()-now))*1000)),self._loop)

# ═══════════════════════════════════════════════════════════════════════════════
# §10  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    root=tk.Tk(); DoomflowPi(root); root.mainloop()

if __name__=='__main__':
    main()
