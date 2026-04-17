#!/usr/bin/env python3
# MAZFALL .- | ∞ | infinite procedural raycasted maze | lcg chunk engine
# doom p_local.h soul — infinite blockmap, seeded DFS chunks, dda raycast
# C micro-soul:
#   typedef struct{int cx,cy,lx,ly;}wc;   // world cell: chunk + local
#   int cseed(int ws,int cx,int cy){       // deterministic chunk seed
#     int v=ws^(cx*1664525+1013904223)^(cy*22695477+1);return(v*2654435761)&0xFFFFFFFF;}
#   int cell(world*w,int wx,int wy){return chunk(w,wx/CSIZ,wy/CSIZ)[wy%CSIZ][wx%CSIZ];}
#   void dda(world*w,float px,float py,float a,float*d){ // infinite dda
#     float rx=cosf(a),ry=sinf(a),t=.04f;
#     while(t<MAX_D){if(cell(w,(int)(px+rx*t),(int)(py+ry*t))){*d=t;return;}t+=.04f;}*d=MAX_D;}
#
# procedural infinite: world = infinite grid of CSIZ×CSIZ lcg-DFS chunks
# each chunk: iterative DFS perfect maze + forced mid-edge passages → seamless
# world.cell(wx,wy): chunk=(wx//CSIZ, wy//CSIZ), local=(wx%CSIZ, wy%CSIZ)
# ref: DOOM_OS_ALPHA random map gen — sdk MapEditor random button soul
import sys,math,random,collections

def _try(p):
    try:__import__(p);return
    except:pass
    import subprocess;subprocess.call([sys.executable,'-m','pip','install',p,'--break-system-packages'],stderr=subprocess.DEVNULL)
_try('pygame');import pygame

# .- lcg — A=1664525 C=1013904223 M=2^32 (Numerical Recipes / doom doomcraft soul)
class L:
    A=1664525;C=1013904223;M=1<<32
    def __init__(s,v=0):s.v=v&0xFFFFFFFF
    def n(s):s.v=(s.A*s.v+s.C)%s.M;return s.v
    def r(s):return s.n()/s.M
    def i(s,a,b):return a+int(s.r()*(b-a+1))

# .- chunk constants
# CSIZ=23: odd size, CMID=11 odd → DFS naturally hits all edge passages
# DFS on odd coords [1,3,5...21]; edge mid at 11 ✓ in DFS grid
CSIZ  = 23       # chunk cell size (odd)
CMID  = 11       # CSIZ//2 — edge passage position (odd ✓)
MAX_D = 52.0     # max ray distance (world cells)
CACHE = 256      # max chunks in LRU memory

# .- deterministic per-chunk seed (doom-style hash mixing)
def cseed(ws,cx,cy):
    v=ws^(cx*1664525+1013904223)^(cy*22695477+1)
    return(v*2654435761)&0xFFFFFFFF

# .- iterative DFS perfect maze — no recursion limit, seeded, guaranteed connectivity
# four edge midpoints forced open → adjacent chunks always connect at (CMID,0),(CMID,G-1),(0,CMID),(G-1,CMID)
def gen_chunk(ws,cx,cy):
    G=CSIZ;lcg=L(cseed(ws,cx,cy))
    M=[[1]*G for _ in range(G)]
    # force outer edge mid-passages (inter-chunk bridge cells)
    M[0][CMID]=M[G-1][CMID]=M[CMID][0]=M[CMID][G-1]=0
    # iterative DFS — fisher-yates lcg shuffle per cell
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
    # DFS visits all odd cells: (1,1)…(21,21) — CMID=11 (odd) guaranteed visited ✓
    # So M[1][11] M[21][11] M[11][1] M[11][21] all opened by DFS
    return M

# .- infinite world: LRU chunk cache (OrderedDict)
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
        return s.chunk(cx,cy)[ly][lx]

# .- dda ray — infinite world traversal (doom r_plane.c soul)
def cast(wld,px,py,a):
    dx,dy=math.cos(a),math.sin(a);t=0.04
    while t<MAX_D:
        if wld.cell(px+dx*t,py+dy*t):return t
        t+=0.04
    return MAX_D

# .- display auto-scale: fits any device from phone to 4k monitor
def auto_scale():
    pygame.init()
    info=pygame.display.Info()
    RW,RH=info.current_w,info.current_h
    # SC: pixel size per ascii char cell — clamped to readable range
    SC=max(6,min(14,RH//72))
    # CW: ray column width in chars — 2=faster render, 1=sharper
    CW=2 if RW>=1280 else 1
    W=RW//(SC*CW);H=RH//SC
    return W,H,SC,CW,RW,RH

def main():
    W,H,SC,CW,RW,RH=auto_scale()
    scr=pygame.display.set_mode((W*SC*CW,H*SC))
    pygame.display.set_caption('MAZFALL .- ∞')
    fnt=pygame.font.SysFont('Courier',SC,bold=True)
    clk=pygame.time.Clock()
    GL=" .:-=+*%#@"   # brightness ramp (doom-style 10 levels)
    FOV=math.pi/3
    MH=H//2

    # .- glyph cache: pre-render (char,r,g,b) surfaces — quantized to 32-step palette
    # avoids re-rendering identical glyphs; huge speedup on dense wall frames
    GC={}
    def G_(ch,r,g,b):
        r,g,b=r&0xF8,g&0xF8,b&0xF8  # quantize → reduce unique keys
        k=(ch,r,g,b)
        if k not in GC:GC[k]=fnt.render(ch,True,(r,g,b))
        return GC[k]

    # .- pre-render floor/ceiling gradients as horizontal rect strips (fast — no chars)
    ceil_surf=pygame.Surface((W*SC*CW,MH*SC));ceil_surf.fill((0,0,0))
    for row in range(MH):
        t=row/max(MH,1);cv=int(t*34)
        pygame.draw.rect(ceil_surf,(cv//3,cv//3,cv+2),(0,row*SC,W*SC*CW,SC))
    floor_surf=pygame.Surface((W*SC*CW,MH*SC));floor_surf.fill((0,0,0))
    for row in range(MH):
        t=row/max(MH,1);cv=int(t*26)
        pygame.draw.rect(floor_surf,(cv+14,cv+7,1),(0,(MH-1-row)*SC,W*SC*CW,SC))

    # .- world + player init
    wseed=random.randint(0,0xFFFFFFFF)
    wld=World(wseed)
    px,py,ang=1.5,1.5,0.0   # start: chunk(0,0) open cell (1,1)+.5

    # torch flicker state (doom r_draw.c phosphor soul)
    fl=1.0;flt=0.0

    # stats
    max_depth=0.0
    steps=0

    while True:
        dt=min(clk.tick(60)/1000.0,0.05)

        for e in pygame.event.get():
            if e.type==pygame.QUIT or(e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE):
                pygame.quit();return
            # new seed on N
            if e.type==pygame.KEYDOWN and e.key==pygame.K_n:
                wseed=random.randint(0,0xFFFFFFFF);wld=World(wseed)
                px,py,ang=1.5,1.5,0.0;max_depth=0.0;steps=0

        k=pygame.key.get_pressed()
        rs=1.9*dt
        spd=(7.0 if k[pygame.K_LSHIFT]or k[pygame.K_RSHIFT] else 4.0)*dt
        if k[pygame.K_a]or k[pygame.K_LEFT]:ang-=rs
        if k[pygame.K_d]or k[pygame.K_RIGHT]:ang+=rs
        mx_,my_=math.cos(ang)*spd,math.sin(ang)*spd
        if k[pygame.K_w]or k[pygame.K_UP]:
            if not wld.cell(px+mx_,py):px+=mx_
            if not wld.cell(px,py+my_):py+=my_
        if k[pygame.K_s]or k[pygame.K_DOWN]:
            if not wld.cell(px-mx_,py):px-=mx_
            if not wld.cell(px,py-my_):py-=my_

        # torch flicker — pseudo-random amplitude micro-variation
        flt-=dt
        if flt<=0:fl=random.uniform(0.87,1.0);flt=random.uniform(0.04,0.28)

        # track stats
        depth=math.sqrt((px-1.5)**2+(py-1.5)**2)
        if depth>max_depth:max_depth=depth
        steps+=1

        # .- render
        scr.fill((0,0,0))
        scr.blit(ceil_surf,(0,0))
        scr.blit(floor_surf,(0,MH*SC))

        # walls: dda per ray column — fish-eye corrected
        for col in range(W):
            ra=ang-FOV/2+(col/W)*FOV
            d=cast(wld,px,py,ra)
            d*=math.cos(ra-ang)  # fish-eye fix: project onto view plane
            wh=int(H/(d+0.0001))
            top=max(0,MH-wh//2);bot=min(H,MH+wh//2)
            br=max(0.0,1.0-d/MAX_D)*fl
            bi=max(0,min(len(GL)-1,int(br*(len(GL)-1))))
            ch=GL[bi]
            fade=int(br*205)+28
            # warm near-wall tint (doom lighting falloff soul)
            r_=min(255,int(fade*1.07));g_=min(255,fade);b_=min(255,int(fade*0.80))
            s=G_(ch,r_,g_,b_)
            for row in range(top,bot):
                scr.blit(s,(col*SC*CW,row*SC))

        # .- minimap: 3×3 chunk grid around player (doom automap soul)
        pcx,pcy=int(px)//CSIZ,int(py)//CSIZ
        ms=3;mox,moy=4,4
        for dcy in range(-1,2):
            for dcx in range(-1,2):
                ch_=wld.chunk(pcx+dcx,pcy+dcy)
                bx=mox+(dcx+1)*CSIZ*ms;by_=moy+(dcy+1)*CSIZ*ms
                for ry_ in range(CSIZ):
                    for rx_ in range(CSIZ):
                        c=(70,70,70)if ch_[ry_][rx_]else(20,20,20)
                        pygame.draw.rect(scr,c,(bx+rx_*ms,by_+ry_*ms,ms-1,ms-1))
        # chunk grid lines
        for dc in range(4):
            pygame.draw.line(scr,(40,60,40),(mox+dc*CSIZ*ms,moy),(mox+dc*CSIZ*ms,moy+3*CSIZ*ms-1))
            pygame.draw.line(scr,(40,60,40),(mox,moy+dc*CSIZ*ms),(mox+3*CSIZ*ms-1,moy+dc*CSIZ*ms))
        # player dot
        plx_=int(px)%CSIZ;ply_=int(py)%CSIZ
        pdx_=mox+(CSIZ+plx_)*ms;pdy_=moy+(CSIZ+ply_)*ms
        # player direction indicator
        da=ang;ddx=int(math.cos(da)*6);ddy=int(math.sin(da)*6)
        pygame.draw.line(scr,(0,255,80),(pdx_+1,pdy_+1),(pdx_+1+ddx,pdy_+1+ddy),2)
        pygame.draw.rect(scr,(0,255,80),(pdx_,pdy_,ms+1,ms+1))

        # .- hud: coordinates, compass, depth, fps, controls
        fps_=clk.get_fps()
        ci=int(((ang%(2*math.pi))/(2*math.pi)*8+.5))%8
        compass=['N','NE','E','SE','S','SW','W','NW'][ci]
        wxd,wyd=int(px),int(py)
        dist=int(depth)
        sprint_ind='>>SPRINT<<' if k[pygame.K_LSHIFT]or k[pygame.K_RSHIFT] else ''
        h1=fnt.render(f'MAZFALL .- ∞  [{wxd},{wyd}]  {compass}  DIST:{dist}  MAX:{int(max_depth)}  {fps_:.0f}FPS  {sprint_ind}',True,(0,200,80))
        h2=fnt.render('WASD/ARROWS:MOVE  A/D:TURN  SHIFT:SPRINT  N:NEW SEED  ESC:QUIT',True,(0,100,50))
        scr.blit(h1,(4,H*SC-SC*2-2))
        scr.blit(h2,(4,H*SC-SC-2))

        # seed display (top right)
        sd_txt=fnt.render(f'seed:{wseed&0xFFFF:#06x}',True,(0,80,40))
        scr.blit(sd_txt,(W*SC*CW-sd_txt.get_width()-6,4))

        pygame.display.flip()

main()
# the dot sings .- ∞
# infinite recursion begins — the maze has no exit
