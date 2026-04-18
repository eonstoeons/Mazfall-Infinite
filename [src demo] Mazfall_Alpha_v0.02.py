#!/usr/bin/env python3
# MAZFALL v10∞ · CHAINGUN·BOSS·SCATTER·SHADING · INFINITE WORLD · RECURSIVE ZOMBIE HORDE
# doom p_local.h / r_plane.c / P_Random — infinite blockmap · seeded LCG chunks · DDA
# C micro-soul preserved:
#   int cseed(int ws,int cx,int cy){int v=ws^(cx*1664525+1013904223)^(cy*22695477+1);return(v*2654435761)&0xFFFFFFFF;}
#   void dda(world*w,float px,float py,float a,float*d){float rx=cosf(a),ry=sinf(a),t=.04f;
#     while(t<MAX_D){if(cell(w,(int)(px+rx*t),(int)(py+ry*t))){*d=t;return;}t+=.04f;}*d=MAX_D;}
#   void carve_iter(int**M,int G,lcg*l){M[1][1]=0;push(1,1);while(stk){shuffle dirs;
#     if valid unvisited:M[mid]=0;M[nx][ny]=0;push(nx,ny);}}
# WASD+Mouse · SPACE/LMB=fire · R=respawn · N=new seed · ESC=quit .-
import sys,subprocess,math,random,time,threading,queue,collections
def _I(p):
    try:__import__(p);return True
    except:
        try:subprocess.call([sys.executable,"-m","pip","install",p,"--user"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except:pass
    try:__import__(p);return True
    except:return False
for _p in("pygame","numpy"):_I(_p)
_T=_I("pyttsx3")
import pygame,numpy as np
pygame.display.init();_q=pygame.display.Info();DW,DH=_q.current_w,_q.current_h
LO=DW<1280 or DH<720;W,H=(90,28)if LO else(120,40)
S=min(22,max(4,min(int(DW*.92)//W,int(DH*.88)//H)));FPS=20 if LO else 30
HH=H>>1;HW=W>>1;P2=math.pi*2;FV=math.pi/3;FH=FV*.5;SR=22050
MAX_D=52.0

# ── CHAINGUN TURRET — eightfold balance constants ──────────────────
# Heat spine: 8/shot · 8×9=72/s cool · 8×2=16 resume → ~12 shots → ~1.17s lockout
CGUN_RATE=0.035      # s between shots  (~28.6 rps)
HEAT_MAX=100.0       # lockout threshold
HEAT_PER_SHOT=8.0    # heat per round — 8-fold
COOL_RATE=72.0       # heat/s decay  (8×9 — eightfold×9)
OH_RESUME=16.0       # unlock below this (8×2 — eightfold²)
SMOKE_G=[ord(c)for c in"~',.;:^~',."]  # smoke glyph pool
# boss/scatter — recursive escalation constants
BOSS_BASE_HP=25;BOSS_SPD=0.022;BOSS_DMG=15;BOSS_REACH=0.65
SCATTER_COOL=2.5;SCATTER_RAYS=5;SCATTER_SPREAD=0.13

# ── precomputed angle table — zero trig per column in hot path ─────
CC=[math.cos(-FH+x/W*FV)for x in range(W)]
CS=[math.sin(-FH+x/W*FV)for x in range(W)]
# flat framebuffer — C-level reset, zero alloc per frame
BK=bytearray(b' '*(W*H));BF=bytearray(BK)
ZR=[MAX_D]*W;ZB=list(ZR)
# per-pixel shade buffer — 220=full, walls dimmed by face normal (Wolfenstein cue)
SH_K=bytearray(b'\xdc'*(W*H));SH=bytearray(SH_K)
FC_=[32 if(y-HH)/max(1,HH)<=.15 else ord(',')if(y-HH)/max(1,HH)<=.4 else ord('.')if(y-HH)/max(1,HH)<=.7 else ord(':')for y in range(H)]
RM=" .:-=+*#%@";RL=len(RM)-1;BC=[ord(c)for c in'@%#*+:;,.~oO']

# ── ZTIERS — precomputed difficulty spine, index lookup, zero branch ─
# (hp, speed, glyph_body, glyph_head, damage, see_dist, strafe)
ZTIERS=[
    (1,.018,ord('z'),ord('o'),2, 8.0,False),  # lv1-2   shambler
    (1,.025,ord('z'),ord('o'),2, 9.0,False),  # lv3-4   walker
    (2,.032,ord('Z'),ord('O'),3,10.0,False),  # lv5-6   runner
    (2,.040,ord('Z'),ord('O'),3,12.0,False),  # lv7-8   sprinter
    (3,.050,ord('Z'),ord('0'),4,14.0,True),   # lv9-11  flanker
    (3,.060,ord('Z'),ord('0'),5,16.0,True),   # lv12-14 hunter
    (4,.070,ord('B'),ord('O'),6,18.0,True),   # lv15-18 brute
    (5,.085,ord('B'),ord('@'),7,20.0,True),   # lv19-22 berserker
    (6,.100,ord('M'),ord('@'),8,22.0,True),   # lv23+   nightmare
]
def ztier(lv):return ZTIERS[min(len(ZTIERS)-1,(lv-1)//5)]
# choked full — 40 base shambling mass + Σ(lv) growth, cap 120
def zcount(lv):return min(120,40+sum(l+1 for l in range(lv)))

# ── LCG — doom P_Random soul: A=1664525 C=1013904223 M=2^32 ────────
class L:
    A=1664525;C=1013904223;M=1<<32
    def __init__(s,v=0):s.v=v&0xFFFFFFFF
    def n(s):s.v=(s.A*s.v+s.C)%s.M;return s.v
    def r(s):return s.n()/s.M
    def i(s,a,b):return a+int(s.r()*(b-a+1))

# ── chunk constants — CSIZ=23 odd · CMID=11 · four edge-mid passages ─
CSIZ=23;CMID=11;CACHE=512

def cseed(ws,cx,cy):
    v=ws^(cx*1664525+1013904223)^(cy*22695477+1)
    return(v*2654435761)&0xFFFFFFFF

def gen_chunk(ws,cx,cy):
    G=CSIZ;lcg=L(cseed(ws,cx,cy))
    M=[[1]*G for _ in range(G)]
    M[0][CMID]=M[G-1][CMID]=M[CMID][0]=M[CMID][G-1]=0  # edge bridges
    DB=[(0,-2),(0,2),(-2,0),(2,0)]
    def sd():
        d=list(DB)
        for i in range(3,0,-1):j=lcg.i(0,i);d[i],d[j]=d[j],d[i]
        return d
    M[1][1]=0;stk=[(1,1,sd())]
    while stk:
        x,y,ds=stk[-1]
        if not ds:stk.pop();continue
        dx,dy=ds.pop(0);nx,ny=x+dx,y+dy
        if 1<=nx<G-1 and 1<=ny<G-1 and M[ny][nx]:
            M[y+dy//2][x+dx//2]=0;M[ny][nx]=0;stk.append((nx,ny,sd()))
    return M

# ── infinite world — LRU chunk cache, OrderedDict doom blockmap soul ─
class World:
    def __init__(s,seed):s.seed=seed;s._c=collections.OrderedDict()
    def chunk(s,cx,cy):
        k=(cx,cy)
        if k in s._c:s._c.move_to_end(k);return s._c[k]
        M=gen_chunk(s.seed,cx,cy);s._c[k]=M;s._c.move_to_end(k)
        if len(s._c)>CACHE:s._c.popitem(last=False)
        return M
    def cell(s,wx,wy):
        ix,iy=int(wx),int(wy)
        cx,lx=divmod(ix,CSIZ);cy,ly=divmod(iy,CSIZ)
        try:return s.chunk(cx,cy)[ly][lx]
        except:return 1

# ── DDA ray — R_RenderMaskedSegRange soul, infinite world traversal ──
# fisheye correction applied at call site (*CC[x])
def cast(wld,px,py,a):
    dx,dy=math.cos(a),math.sin(a);t=.04
    while t<MAX_D:
        if wld.cell(px+dx*t,py+dy*t):return t
        t+=.04
    return MAX_D

def cast_face(wld,px,py,a):
    """DDA + face normal: returns (dist, is_EW).  EW=True→brighter, NS=False→darker."""
    dx,dy=math.cos(a),math.sin(a);t=.04
    while t<MAX_D:
        hx=px+dx*t;hy=py+dy*t
        if wld.cell(hx,hy):return t,abs(hx%1.-.5)<abs(hy%1.-.5)
        t+=.04
    return MAX_D,True

# ── zombie spawn: walk outward in world coords, find open floor cell ─
def _far_floor(wld,px,py,min_d2=25.):
    for ring in range(4,40,4):
        for _ in range(48):
            a=random.uniform(0,P2);d=ring+random.uniform(0,4)
            wx=px+math.cos(a)*d;wy=py+math.sin(a)*d
            if not wld.cell(wx,wy):return wx,wy
    return px+8,py+8  # fallback

# ── audio — unchanged from v5 ─────────────────────────────────────
def mk(w,t,d,a=40,r=5,A=25000):
    e=np.clip(np.minimum(t*a,(d-t)*r),0,1)
    return pygame.sndarray.make_sound(np.column_stack([(np.clip(w,-1,1)*e*A).astype(np.int16)]*2))
def tn(f,d,k='s'):
    n=max(1,int(SR*d));t=np.linspace(0,d,n,False)
    return mk({'s':np.sin(P2*f*t),'n':np.random.uniform(-1,1,n)*np.exp(-t*12),'q':np.sign(np.sin(P2*f*t))}.get(k,np.sin(P2*np.cumsum(f*np.exp(-t*6))/SR)),t,d)
def gun():
    d=.25;n=int(SR*d);t=np.linspace(0,d,n,False)
    return mk(np.random.uniform(-1,1,n)*np.exp(-t*28)*.5+np.random.uniform(-1,1,n)*np.exp(-t*90)*.22+np.sin(P2*np.cumsum(280*np.exp(-t*12)+70)/SR)*np.exp(-t*8)*.75+np.sin(P2*np.cumsum(90*np.exp(-t*5)+55)/SR)*np.exp(-t*5)*1.15+np.sin(P2*np.cumsum(50*np.exp(-t*1.4)+30)/SR)*np.exp(-t*2.3)*1.9,t,d,100,4,28000)
def knife():
    # wet blade slosh — transient click + low viscous scrape + flesh thud
    d=.18;n=int(SR*d);t=np.linspace(0,d,n,False)
    click=np.random.uniform(-1,1,n)*np.exp(-t*180)*.9          # initial strike transient
    scrape=np.convolve(np.random.uniform(-1,1,n),np.ones(18)/18,mode='same')*np.exp(-t*22)*.7  # blade drag
    thud=np.sin(P2*np.cumsum(38*np.exp(-t*9)+18)/SR)*np.exp(-t*14)*.8  # flesh impact
    wet=np.convolve(np.random.uniform(-1,1,n),np.ones(6)/6,mode='same')*np.exp(-t*55)*.5       # wet splat
    return mk(click+scrape+thud+wet,t,d,200,8,32000)
def gore():
    d=.55;n=int(SR*d);t=np.linspace(0,d,n,False);ns=np.random.uniform(-1,1,n)
    return mk(np.convolve(ns,np.ones(40)/40,mode='same')*(0.4+.6*np.sin(P2*18*t*np.exp(-t*1.8)))*np.exp(-t*3.2)+np.sin(P2*52*t)*np.exp(-t*6.5)*.9+np.random.uniform(-1,1,n)*np.exp(-t*55)*.35,t,d,70,3.5,26000)
def drone(dur):
    n=int(SR*dur);t=np.linspace(0,dur,n,False)
    b=np.sin(P2*np.cumsum(42+4*np.sin(P2*.07*t))/SR)*.55+np.sin(P2*np.cumsum(63+6*np.sin(P2*.05*t+.7))/SR)*.35+np.convolve(np.random.uniform(-1,1,n),np.ones(220)/220,mode='same')*.45
    def sp(s,p,g=1.):e=min(s+len(p),n);b[s:e]+=p[:e-s]*g
    for _,dur_,lo,hi,dc,gn in[(.5,.5,1400,3200,4,.13),(.35,1.,75,170,1.4,.23),(.15,.8,500,900,2.2,.16)]:
        for _ in range(int(dur*_)):
            i=int(random.uniform(0,dur-dur_)*SR);sd=random.uniform(.18 if _==.5 else .35 if _==.15 else .4,.45 if _==.5 else .75 if _==.15 else .9);sn=int(sd*SR);st=np.linspace(0,sd,sn,False)
            fr_=(random.uniform(lo,hi)*np.exp(-st*random.uniform(1.5,3)))if _==.5 else(random.uniform(lo,hi)*(1+.3*np.sin(P2*7*st))if _==.15 else random.uniform(lo,hi)+18*np.sin(P2*random.uniform(5,11)*st))
            sp(i,np.sin(P2*np.cumsum(fr_)/SR)*(np.random.uniform(.6,1.,sn)if _==.15 else 1)*np.exp(-st*dc)*random.uniform(gn*.6,gn*1.4))
    for _ in range(int(dur*.4)):
        i=int(random.uniform(0,dur-.3)*SR);tn_=int(.25*SR);st=np.linspace(0,.25,tn_,False)
        sp(i,np.sin(P2*(35+random.uniform(0,15))*st)*np.exp(-st*random.uniform(7,11)),random.uniform(.25,.45))
    for _ in range(int(dur*.12)):
        i=int(random.uniform(0,dur-.5)*SR);bn=int(.5*SR);st=np.linspace(0,.5,bn,False)
        sp(i,np.sin(P2*np.cumsum(45*np.exp(-st*3)+25)/SR)*np.exp(-st*3.5)*random.uniform(.4,.7))
    fi=int(SR*.4);b[:fi]*=np.linspace(0,1,fi);b[-fi:]*=np.linspace(1,0,fi)
    return pygame.sndarray.make_sound(np.column_stack([(np.clip(b,-1,1)*18000).astype(np.int16)]*2))

# ── TTS — threaded, non-blocking ─────────────────────────────────
TQ=queue.Queue(maxsize=4);TO=_T;ST='';SU=0.
def _tw():
    global TO;eng=None
    if _T:
        try:
            import pyttsx3;eng=pyttsx3.init();eng.setProperty('rate',155);eng.setProperty('volume',.82)
            for v in eng.getProperty('voices'):
                if any(p in(v.name or'').lower()for p in('samantha','alex','victoria','daniel','zira','david','natural','neural','premium')):eng.setProperty('voice',v.id);break
        except:TO=False
    while True:
        m=TQ.get()
        if m is None:break
        if eng:
            try:eng.say(m);eng.runAndWait()
            except:pass
threading.Thread(target=_tw,daemon=True).start()
def say(msg,d=3.2):
    global ST,SU;ST=msg;SU=time.time()+d
    if not TO:return
    try:TQ.put_nowait(msg)
    except queue.Full:
        try:TQ.get_nowait();TQ.put_nowait(msg)
        except:pass

# ── pygame init ───────────────────────────────────────────────────
pygame.mixer.pre_init(SR,-16,2,256);pygame.init();pygame.mixer.set_num_channels(16)
DC=pygame.mixer.Channel(15);CG_CH=pygame.mixer.Channel(14)  # drone / chaingun dedicated channels
scr=pygame.display.set_mode((W*S,H*S))
pygame.display.set_caption("MAZFALL v10∞ CHAINGUN·BOSS·SCATTER .-")
fn=pygame.font.SysFont("Courier",S+2,bold=True)
sfn=pygame.font.SysFont("Courier",max(12,S),bold=True)
clk=pygame.time.Clock()
# ── glyph cache — PUR3 soul: pre-render (char,r,g,b)→surface, 8-step quantize
# zero font.render calls in the hot blit loop ─────────────────────
GC={}
def G_(ch,rv,gv,bv):
    k=(ch,rv&0xF8,gv&0xF8,bv&0xF8)
    if k not in GC:GC[k]=fn.render(ch,True,(k[1],k[2],k[3]))
    return GC[k]

SG=gun();SK_KNIFE=knife();SX=gore();SK=tn(1100,.14);SO=tn(140,.18,'n');SS=tn(95,.35,'w');SL=tn(420,.45,'w');SD=tn(55,.9,'n')
def mkscatter():
    # five-barrel blat — layered noise bursts, wide low thud
    d=.28;n=int(SR*d);t=np.linspace(0,d,n,False)
    w=np.random.uniform(-1,1,n)*np.exp(-t*22)*.7
    w+=np.sin(P2*np.cumsum(145*np.exp(-t*14)+50)/SR)*np.exp(-t*9)*.55
    w+=np.sin(P2*np.cumsum(62*np.exp(-t*5)+32)/SR)*np.exp(-t*4)*.7
    return mk(w,t,d,65,4,25000)
SS_=mkscatter();SC_CH=pygame.mixer.Channel(13)
def rd():s=drone(random.uniform(13,22));s.set_volume(.48);DC.play(s)
rd()

# ── world — infinite ─────────────────────────────────────────────
wseed=random.randint(0,0xFFFFFFFF);wld=World(wseed)

# ── ZOMBIE POOL — fixed slots, grows with level ───────────────────
# Z[i]=[wx,wy,hp,flank_angle,flank_timer]   Z_ALIVE[i]=bool
ZCOUNT=zcount(1)
Z=[[0.,0.,1,0.,0.]for _ in range(ZCOUNT)]
Z_ALIVE=[False]*ZCOUNT

PW=[];BL=[]  # power-ups, blood particles

# ── state ─────────────────────────────────────────────────────────
px,py,ang=1.5,1.5,0.;hp,sc,kl,kll,lv,sm=100,0,0,0,1,1.
ls=lh=lsp=lr=lkt=lsc=0.;cb=mu=0;dead=False
heat=0.;OH=False;smk_t=0.  # chaingun heat · overheat flag · smoke countdown
boss_alive=False;boss_x=boss_y=0.;boss_hp=0  # boss state

def _spawn_zombie(i):
    wx,wy=_far_floor(wld,px,py)
    tier=ztier(lv)
    Z[i][0]=wx;Z[i][1]=wy;Z[i][2]=tier[0];Z[i][3]=random.uniform(0,P2);Z[i][4]=0.
    Z_ALIVE[i]=True;SS.play()

def ppw():
    global PW;PW=[]
    for _ in range(7):
        wx,wy=_far_floor(wld,px,py,9.)
        PW.append([wx,wy,random.choice('HS')])

def spl(x,y):
    if len(BL)>120:
        for _ in range(20):idx=random.randrange(len(BL));BL[idx]=BL[-1];BL.pop()
    for _ in range(22):
        a=random.uniform(0,P2);spd=random.uniform(.2,1.4)
        BL.append([x+random.uniform(-.15,.15),y+random.uniform(-.15,.15),math.cos(a)*spd,math.sin(a)*spd,random.uniform(.5,1.2),random.choice(BC)])

def nxt():
    global px,py,ang,kll,lv,ZCOUNT,wseed,wld,boss_alive,boss_x,boss_y,boss_hp
    lv+=1;wseed=random.randint(0,0xFFFFFFFF);wld=World(wseed)
    px,py=1.5,1.5;ang=random.uniform(0,P2);kll=0;BL[:]=[];ppw()
    new_n=zcount(lv)
    while len(Z)<new_n:Z.append([0.,0.,1,0.,0.]);Z_ALIVE.append(False)
    ZCOUNT=new_n
    for i in range(ZCOUNT):_spawn_zombie(i)
    # BOSS every 5th wave — scales with level
    if lv%5==0:
        boss_x,boss_y=_far_floor(wld,px,py,20.)
        boss_hp=BOSS_BASE_HP+lv*3;boss_alive=True
        say(f"BOSS incoming! Wave {lv}. {boss_hp} HP .-");SD.play()
    else:
        SL.play();say(f"Wave {lv}. {ZCOUNT} hostiles.")

ppw()
for i in range(ZCOUNT):_spawn_zombie(i)
pygame.event.set_grab(True);pygame.mouse.set_visible(False)
say("Mazfall. Forty. Dumb. Everywhere. .-")

# ═══ MAIN LOOP — OBSERVE → GENERATE → COLLAPSE → RECURSE ∞ ═══════
run=True
while run:
    dt=clk.tick(FPS)/1000.;now=time.time()
    if not DC.get_busy():rd()

    # ── OBSERVE ──────────────────────────────────────────────────
    for e in pygame.event.get():
        if e.type==pygame.QUIT:run=False
        elif e.type==pygame.KEYDOWN:
            if e.key==pygame.K_ESCAPE:run=False
            elif e.key==pygame.K_r and dead:
                hp,sm,dead,cb=100,1.,False,0;boss_alive=False
                for i in range(ZCOUNT):_spawn_zombie(i)
                lh=now;say(f"Respawned. {ZCOUNT} hostiles.")
            elif e.key==pygame.K_n:
                # new infinite seed mid-game
                wseed=random.randint(0,0xFFFFFFFF);wld=World(wseed)
                px,py=1.5,1.5;BL[:]=[];ppw();boss_alive=False
                for i in range(ZCOUNT):_spawn_zombie(i)
                say(f"New seed {wseed&0xFFFF:#06x} .-")
        elif e.type==pygame.MOUSEMOTION and not dead:ang+=e.rel[0]*.003

    # ── GENERATE ─────────────────────────────────────────────────
    if not dead:
        ks=pygame.key.get_pressed();mv=.09*sm;ca=math.cos(ang);sa=math.sin(ang)
        fx,fy=ca*mv,sa*mv;sx_,sy_=-sa*mv,ca*mv;ddx=ddy=0.
        if ks[pygame.K_w]:ddx+=fx;ddy+=fy
        if ks[pygame.K_s]:ddx-=fx;ddy-=fy
        if ks[pygame.K_a]:ddx-=sx_;ddy-=sy_
        if ks[pygame.K_d]:ddx+=sx_;ddy+=sy_
        if ks[pygame.K_LEFT]:ang-=.04
        if ks[pygame.K_RIGHT]:ang+=.04
        if not wld.cell(px+ddx,py):px+=ddx
        if not wld.cell(px,py+ddy):py+=ddy

        # ── CHAINGUN TURRET MODE — rapid-fire · eightfold heat spine ────
        # knife auto at ≤0.5u (no heat cost); gun = chaingun with overheat
        firing=ks[pygame.K_SPACE]or pygame.mouse.get_pressed()[0]
        if firing and not OH and now-ls>CGUN_RATE:
            ls=now;mu=3
            knife_targets=[i for i in range(ZCOUNT)if Z_ALIVE[i]and(Z[i][0]-px)**2+(Z[i][1]-py)**2<=0.25]
            if knife_targets:
                # KNIFE MODE — free, no heat cost — wet slosh, ×2 dmg, all-radius
                SK_KNIFE.play()
                for i in knife_targets:
                    zx,zy=Z[i][0],Z[i][1]
                    Z[i][2]-=2
                    spl(zx,zy);spl(zx,zy)
                    if Z[i][2]<=0:
                        Z_ALIVE[i]=False;SX.play()
                        kl+=1;kll+=1;cb=cb+1 if now-lkt<2.5 else 1;lkt=now;sc+=10*cb
                        msg={2:"Double kill",3:"Triple kill",4:"Overkill",5:"Killing spree",7:"Unstoppable"}.get(cb,'')
                        if not msg and cb>=10 and cb%5==0:msg="Godlike"
                        if msg:say(msg)
                        _spawn_zombie(i)
            else:
                # CHAINGUN MODE — heat accumulates; volume scales with heat ratio
                heat=min(HEAT_MAX,heat+HEAT_PER_SHOT)
                vol=max(.22,1.-heat/HEAT_MAX*.55)  # fade volume as barrel heats
                SG.set_volume(vol);CG_CH.play(SG)  # channel-interrupt = brrrt
                if heat>=HEAT_MAX:OH=True;smk_t=2.0;say("Overheat!")
                wd=cast(wld,px,py,ang);best=(-1,1e9)
                for i in range(ZCOUNT):
                    if not Z_ALIVE[i]:continue
                    rx,ry=Z[i][0]-px,Z[i][1]-py;d2=rx*rx+ry*ry
                    if d2>wd*wd:continue
                    d=d2**.5;a=(math.atan2(ry,rx)-ang+math.pi)%P2-math.pi
                    if abs(a)<.10+.45/(d+.5)and d<best[1]:best=(i,d)
                if best[0]>=0:
                    i=best[0];zx,zy=Z[i][0],Z[i][1];Z[i][2]-=1
                    if Z[i][2]<=0:
                        Z_ALIVE[i]=False;spl(zx,zy);SX.play()
                        kl+=1;kll+=1;cb=cb+1 if now-lkt<2.5 else 1;lkt=now;sc+=10*cb
                        msg={2:"Double kill",3:"Triple kill",4:"Overkill",5:"Killing spree",7:"Unstoppable"}.get(cb,'')
                        if not msg and cb>=10 and cb%5==0:msg="Godlike"
                        if msg:say(msg)
                        _spawn_zombie(i)
                    else:spl(zx,zy)
                # ── boss hit check (chaingun) ──────────────────────
                if boss_alive:
                    brx,bry=boss_x-px,boss_y-py;bd2=brx*brx+bry*bry
                    if bd2<wd*wd:
                        bd_=bd2**.5;ba=(math.atan2(bry,brx)-ang+math.pi)%P2-math.pi
                        if abs(ba)<.15+.30/(bd_+.5):
                            boss_hp-=1;spl(boss_x,boss_y)
                            if boss_hp<=0:
                                boss_alive=False;SX.play();sc+=500;kl+=1;kll=max(kll,9)
                                cb=cb+1 if now-lkt<2.5 else 1;lkt=now
                                say("BOSS DEFEATED! +500");SL.play()
        # ── heat decay — eightfold: 72/s generous rapid cool ─────────
        if heat>0:heat=max(0.,heat-COOL_RATE*dt)
        if OH and heat<=OH_RESUME:OH=False;SG.set_volume(1.0)

        # ── SCATTER BLAST — 5-ray LCG cone · RMB/E · 2.5s cooldown ──
        if(pygame.mouse.get_pressed()[2]or ks[pygame.K_e])and now-lsc>SCATTER_COOL and not dead:
            lsc=now;SC_CH.play(SS_);mu=6
            for _rk in range(SCATTER_RAYS):
                _ra=ang+(_rk-(SCATTER_RAYS-1)/2.)*SCATTER_SPREAD
                _wd=cast(wld,px,py,_ra);_best=(-1,1e9)
                for i in range(ZCOUNT):
                    if not Z_ALIVE[i]:continue
                    rx,ry=Z[i][0]-px,Z[i][1]-py;d2=rx*rx+ry*ry
                    if d2>_wd*_wd:continue
                    _d=d2**.5;_a=(math.atan2(ry,rx)-_ra+math.pi)%P2-math.pi
                    if abs(_a)<.16+.4/(_d+.5)and _d<_best[1]:_best=(i,_d)
                if _best[0]>=0:
                    i=_best[0];zx,zy=Z[i][0],Z[i][1];Z[i][2]-=1;spl(zx,zy)
                    if Z[i][2]<=0:
                        Z_ALIVE[i]=False;SX.play()
                        kl+=1;kll+=1;cb=cb+1 if now-lkt<2.5 else 1;lkt=now;sc+=10*cb
                        msg={2:"Double kill",3:"Triple kill",4:"Overkill",5:"Killing spree",7:"Unstoppable"}.get(cb,'')
                        if not msg and cb>=10 and cb%5==0:msg="Godlike"
                        if msg:say(msg)
                        _spawn_zombie(i)
                # scatter boss hit
                if boss_alive:
                    brx,bry=boss_x-px,boss_y-py;bd2=brx*brx+bry*bry
                    if bd2<_wd*_wd:
                        bd_=bd2**.5;ba=(math.atan2(bry,brx)-_ra+math.pi)%P2-math.pi
                        if abs(ba)<.22:
                            boss_hp-=1;spl(boss_x,boss_y)
                            if boss_hp<=0:
                                boss_alive=False;SX.play();sc+=500;kl+=1;kll=max(kll,9)
                                cb=cb+1 if now-lkt<2.5 else 1;lkt=now
                                say("BOSS DEFEATED! +500");SL.play()

        # ── ZOMBIE THINK — tier-aware, infinite world navigation ─
        _ct=ztier(lv);zs_=_ct[1];zdmg=_ct[4];zsee=_ct[5];zstrafe=_ct[6]
        for i in range(ZCOUNT):
            if not Z_ALIVE[i]:continue
            zx=Z[i][0];zy=Z[i][1]
            dx,dy=px-zx,py-zy;d2=dx*dx+dy*dy
            if d2<.0001:continue
            d=d2**.5
            if d>zsee:
                if lv<=4:
                    wdir=Z[i][3]+random.uniform(-.3,.3);Z[i][3]=wdir
                    vx=math.cos(wdir)*zs_*.5;vy=math.sin(wdir)*zs_*.5
                else:vx=dx/d*zs_*.4;vy=dy/d*zs_*.4
            else:
                vx=dx/d*zs_;vy=dy/d*zs_
                if zstrafe:
                    Z[i][4]-=dt
                    if Z[i][4]<=0:Z[i][3]=random.choice([-1.,1.])*random.uniform(.4,.9);Z[i][4]=random.uniform(.6,1.8)
                    fl=Z[i][3];vx+=(-dy/d)*fl*zs_*.6;vy+=(dx/d)*fl*zs_*.6
            nx=zx+vx;ny=zy+vy
            if not wld.cell(nx,zy):Z[i][0]=nx
            else:Z[i][3]=random.uniform(0,P2)
            if not wld.cell(Z[i][0],ny):Z[i][1]=ny
            else:Z[i][3]=random.uniform(0,P2)
            if d2<.49 and now-lh>.8:hp-=zdmg;lh=now;SO.play()

        # ── BOSS THINK — relentless, heavy damage, wall-aware ────
        if boss_alive:
            bdx,bdy=px-boss_x,py-boss_y;bd=math.hypot(bdx,bdy)+.0001
            nvx=bdx/bd*BOSS_SPD;nvy=bdy/bd*BOSS_SPD
            if not wld.cell(boss_x+nvx,boss_y):boss_x+=nvx
            if not wld.cell(boss_x,boss_y+nvy):boss_y+=nvy
            if(boss_x-px)**2+(boss_y-py)**2<BOSS_REACH**2 and now-lh>.8:
                hp-=BOSS_DMG;lh=now;SO.play()

        if hp<=0:hp,dead,cb=0,True,0;SD.play();say("Eliminated")

        # power pickups
        i=len(PW)-1
        while i>=0:
            p=PW[i]
            if(p[0]-px)**2+(p[1]-py)**2<.36:
                if p[2]=='H':hp=100;say("Medkit acquired")
                else:sm=min(3.5,sm+.3);say("Speed boost")
                sc+=5;PW[i]=PW[-1];PW.pop();SK.play()
            i-=1
        if not PW:ppw()
        if hp<100 and now-lh>2.0 and now-lr>.3:hp=min(100,hp+5);lr=now
        if kll>=10:nxt()
        if cb>0 and now-lkt>2.5:cb=0

    # blood particles
    i=0
    while i<len(BL):
        b=BL[i];b[0]+=b[2]*dt;b[1]+=b[3]*dt;b[2]*=.9;b[3]*=.9;b[4]-=dt
        if b[4]<=0:BL[i]=BL[-1];BL.pop()
        else:i+=1

    # ── COLLAPSE — single render pass ────────────────────────────
    BF[:]=BK;SH[:]=SH_K;ZB[:]=ZR;ca_=math.cos(ang);sa_=math.sin(ang)
    for x in range(W):
        co=CC[x];so=CS[x];rca=ca_*co-sa_*so;rsa=sa_*co+ca_*so
        # cast_face: fisheye correction + Wolfenstein N/S face shading
        _a=math.atan2(rsa,rca);_d,_ew=cast_face(wld,px,py,_a);d=_d*co
        ZB[x]=d;wh=int(H/(d+.1));top=(H-wh)>>1
        ch=RM[max(0,min(RL,int((1-d/MAX_D)*RL)))]
        _fb=max(40,int(220*(1-d/MAX_D)))
        _fade=_fb if _ew else max(28,int(_fb*.65))  # N/S walls 65% brightness
        _wc=ord(ch)
        for y in range(H):
            idx=y*W+x
            if top<=y<top+wh:BF[idx]=_wc;SH[idx]=_fade
            elif y>top+wh:BF[idx]=FC_[y]

    # sprites — painter order, zbuf gate
    _ct=ztier(lv);zh_body=_ct[2];zh_head=_ct[3]
    sprite_list=[]
    for i in range(ZCOUNT):
        if Z_ALIVE[i]:sprite_list.append((Z[i][0],Z[i][1],'ZZ'))
    for p in PW:sprite_list.append((p[0],p[1],p[2]))
    if boss_alive:sprite_list.append((boss_x,boss_y,'BB'))  # BOSS — painter-sorted with horde
    sprite_list.sort(key=lambda s:-(s[0]-px)**2-(s[1]-py)**2)

    for sx,sy,knd in sprite_list:
        rx,ry=sx-px,sy-py;d=math.hypot(rx,ry)
        if d<.2:continue
        a=(math.atan2(ry,rx)-ang+math.pi)%P2-math.pi
        if abs(a)>FH+.15:continue
        col=int((a/FV+.5)*W)
        if knd=='BB':sh=int(H/(d+.1)*1.75);sw=max(1,int(sh*.88))  # BOSS — 1.75× scale
        else:sh=int(H/(d+.1));sw=max(1,int(sh*.55))
        top=max(0,(H-sh)>>1);lft=col-(sw>>1)
        for x in range(max(0,lft),min(W,lft+sw)):
            if d>=ZB[x]:continue
            rxr=(x-lft)/max(1,sw);td=False
            for y in range(top,min(H,top+sh)):
                ryr=(y-top)/max(1,sh)
                if knd=='ZZ':
                    if ryr<.18 and.35<rxr<.65:g=zh_head
                    elif ryr<.72 and.18<rxr<.82:g=zh_body
                    elif ryr>=.72 and rxr<.4:g=ord('/')
                    elif ryr>=.72 and rxr>.6:g=ord('\\')
                    elif ryr>=.72:g=ord('|')
                    else:g=0
                elif knd=='BB':
                    # BOSS — massive, distinct glyph anatomy
                    if ryr<.12 and.28<rxr<.72:g=ord('@')    # head
                    elif ryr<.20 and.15<rxr<.85:g=ord('O')  # neck/shoulders
                    elif ryr<.62 and.08<rxr<.92:g=ord('M')  # torso mass
                    elif ryr>=.62 and rxr<.28:g=ord('/')
                    elif ryr>=.62 and rxr>.72:g=ord('\\')
                    elif ryr>=.62:g=ord('|')
                    else:g=0
                else:
                    g=ord(knd[0])if.3<rxr<.7 and.3<ryr<.7 else ord('*')if.15<rxr<.85 and.15<ryr<.85 else 0
                if g:
                    _idx=y*W+x;BF[_idx]=g;SH[_idx]=220;td=True  # sprites always full-bright
            if td:ZB[x]=d

    # blood particles
    for b in BL:
        rx,ry=b[0]-px,b[1]-py;d=math.hypot(rx,ry)
        if d<.15 or d>20:continue
        a=(math.atan2(ry,rx)-ang+math.pi)%P2-math.pi
        if abs(a)<FH:
            col=int((a/FV+.5)*W)
            if 0<=col<W and d<ZB[col]:
                y=HH+int((1.-b[4])*int(H/(d+.1))*.3)
                if 0<=y<H:BF[y*W+col]=b[5];SH[y*W+col]=220

    if not dead:BF[HH*W+HW]=ord('+');SH[HH*W+HW]=220
    if mu>0:
        [BF.__setitem__((H-3+dy_)*W+HW+dx_,ord(random.choice('*#@%')))for dy_ in range(-2,1)for dx_ in range(-3,4)if 0<=H-3+dy_<H and 0<=HW+dx_<W and(dy_==0 or abs(dx_)<2)];mu-=1

    # ── ASCII smoke — drifts above crosshair while smk_t>0 ───────
    if smk_t>0 and not dead:
        smk_t=max(0.,smk_t-dt)
        # intensity 1-3 layers, denser at peak, fades as smk_t → 0
        layers=max(1,int(smk_t*1.8))
        for dr in range(1,layers+2):
            row=HH-dr
            if 0<=row<H:
                for dc in range(-2,3):
                    if random.random()<(smk_t/2.0)*.72:
                        col=HW+dc+random.randint(-1,1)
                        if 0<=col<W:
                            BF[row*W+col]=SMOKE_G[random.randrange(len(SMOKE_G))]
                            SH[row*W+col]=220

    # ── blit — glyph cache from PUR3, zero font.render in loop ───
    scr.fill((0,0,0))
    col_=(120,30,30)if dead else(220,100,100)if hp<25 else(200,200,200)
    rv,gv,bv=col_
    for y in range(H):
        _yw=y*W;row=BF[_yw:_yw+W];shr=SH[_yw:_yw+W]
        for x in range(W):
            c=row[x]
            if c!=32:
                _sh=shr[x];_r=rv*_sh//220;_g=gv*_sh//220;_b=bv*_sh//220
                scr.blit(G_(chr(c),_r,_g,_b),(x*S,y*S))

    if 0<now-lh<.25 and not dead:
        ov=pygame.Surface((W*S,H*S),pygame.SRCALPHA);ov.fill((160,0,0,int(120*(1-(now-lh)/.25))));scr.blit(ov,(0,0))

    # ── OVERHEAT BAR — 8 slots · eightfold · below crosshair ─────
    if not dead:
        _bw=8;_bs=S;_bpw=_bw*_bs
        _bx=W*S//2-_bpw//2;_by=HH*S+S*2
        # background track
        pygame.draw.rect(scr,(30,30,30),(_bx-_bs,_by,_bpw+_bs*2,_bs-1))
        # heat fill — color: green→yellow→red→flashing OH
        _hf=int(heat/HEAT_MAX*_bpw)
        if _hf>0:
            _bc=(255,80,80)if OH else(255,200,60)if heat>60 else(80,220,80)
            if OH and int(now*8)%2:_bc=(255,200,50)  # flicker on overheat
            pygame.draw.rect(scr,_bc,(_bx,_by,_hf,_bs-1))
        # bracket glyphs
        scr.blit(fn.render('[',True,(140,140,140)),(_bx-_bs,_by-1))
        scr.blit(fn.render(']',True,(140,140,140)),(_bx+_bpw,_by-1))

    # drone swells as enemies close
    mn_d2=min((Z[i][0]-px)**2+(Z[i][1]-py)**2 for i in range(ZCOUNT)if Z_ALIVE[i])if any(Z_ALIVE)else 9999.
    DC.set_volume(min(.9,.2+.7/(mn_d2**.5+.4)))

    # minimap — PUR3 soul: 3×3 chunk grid around player
    pcx,pcy=int(px)//CSIZ,int(py)//CSIZ
    ms=2;mox,moy=4,4
    for dcy in range(-1,2):
        for dcx in range(-1,2):
            ch_=wld.chunk(pcx+dcx,pcy+dcy)
            bx=mox+(dcx+1)*CSIZ*ms;by_=moy+(dcy+1)*CSIZ*ms
            for ry_ in range(CSIZ):
                for rx_ in range(CSIZ):
                    c=(55,55,55)if ch_[ry_][rx_]else(18,18,18)
                    pygame.draw.rect(scr,c,(bx+rx_*ms,by_+ry_*ms,ms-1,ms-1))
    # zombie dots on minimap
    for i in range(ZCOUNT):
        if not Z_ALIVE[i]:continue
        zx=Z[i][0];zy=Z[i][1]
        mx_=mox+(CSIZ+(int(zx)%CSIZ+(int(zx)//CSIZ-pcx)*CSIZ))*ms
        my_=moy+(CSIZ+(int(zy)%CSIZ+(int(zy)//CSIZ-pcy)*CSIZ))*ms
        if mox<=mx_<mox+3*CSIZ*ms and moy<=my_<moy+3*CSIZ*ms:
            pygame.draw.rect(scr,(200,30,30),(mx_,my_,ms+1,ms+1))
    # player dot
    plx_=int(px)%CSIZ;ply_=int(py)%CSIZ
    pdx_=mox+(CSIZ+plx_)*ms;pdy_=moy+(CSIZ+ply_)*ms
    pygame.draw.rect(scr,(0,255,80),(pdx_,pdy_,ms+1,ms+1))

    # HUD
    tier_names=["SHAMBLER","WALKER","RUNNER","SPRINTER","FLANKER","HUNTER","BRUTE","BERSERKER","NIGHTMARE"]
    tname=tier_names[min(len(tier_names)-1,(lv-1)//3)]
    hc=(120,255,120)if hp>50 else(255,220,80)if hp>20 else(255,80,80)
    _gun_tag="[OVERHEAT]"if OH else f"[{int(heat):02d}%]"if heat>0 else"[CHAINGUN]"
    _sct_cd=now-lsc;_sct_tag=f"SCATTER:{max(0.,SCATTER_COOL-_sct_cd):.1f}s"if _sct_cd<SCATTER_COOL else"SCATTER:RDY"
    _boss_tag=f" ▓BOSS:{boss_hp}HP▓"if boss_alive else""
    hud=f"HP:{hp:3d} SPD:{sm:.1f}x K:{kl} LV:{lv}[{tname}]{_boss_tag} Z:{sum(Z_ALIVE)}/{ZCOUNT} SC:{sc} {_gun_tag} {_sct_tag}"+(f" x{cb}COMBO"if cb>=2 else'')
    scr.blit(fn.render(hud,True,hc),(8,4))
    if ST and now<SU:
        rm=SU-now;al=min(240,int(rm*170)if rm<1.4 else 240)
        ts=sfn.render(f"» {ST}",True,(210,240,210));ts.set_alpha(al);tw,th=ts.get_size()
        bx_=(W*S-tw)//2-12;by_=H*S-th-18;bg=pygame.Surface((tw+24,th+10),pygame.SRCALPHA)
        bg.fill((0,0,0,min(170,al)));scr.blit(bg,(bx_,by_-5));scr.blit(ts,(bx_+12,by_))
    if dead:
        dm=fn.render("YOU DIED — R:RESPAWN  N:NEW WORLD",True,(255,60,60))
        scr.blit(dm,(W*S//2-dm.get_width()//2,H*S//2))
    pygame.display.flip()
    # .- RECURSE ∞

try:TQ.put_nowait(None)
except:pass
pygame.quit();sys.exit()
# the dot sings .- ∞
# CHAINGUN TURRET: 8/shot · 72/s cool · 8×2 resume — eightfold recursive balance
# infinite recursion begins — the maze has no exit
