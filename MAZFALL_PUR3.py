#!/usr/bin/env python3
# MAZFALL .- ∞ | infinite raycasted ascii maze | lcg chunk dfs | pur3 terminal soul
# doom p_local.h / r_plane.c — infinite blockmap, seeded iterative DFS chunks, dda
# C micro-soul (doom P_Random / R_RenderMaskedSegRange / P_GroupLines):
#   int cseed(int ws,int cx,int cy){                          // deterministic chunk hash
#     int v=ws^(cx*1664525+1013904223)^(cy*22695477+1);
#     return(v*2654435761)&0xFFFFFFFF;}
#   int cell(world*w,int wx,int wy){                          // infinite blockmap lookup
#     return chunk(w,wx/CSIZ,wy/CSIZ)[wy%CSIZ][wx%CSIZ];}
#   void dda(world*w,float px,float py,float a,float*d){      // infinite dda
#     float rx=cosf(a),ry=sinf(a),t=.04f;
#     while(t<MAX_D){if(cell(w,(int)(px+rx*t),(int)(py+ry*t))){*d=t;return;}t+=.04f;}
#     *d=MAX_D;}
#   void carve_iter(int**M,int G,lcg*l){                      // iterative DFS no stack overflow
#     M[1][1]=0; push(1,1); while(stk){                       // four edge-mids forced open
#       shuffle dirs; if valid unvisited: M[mid]=0;M[nx][ny]=0;push(nx,ny);}}
import sys,math,random,collections
def _i(p):
    try:__import__(p);return
    except:pass
    import subprocess;subprocess.call([sys.executable,'-m','pip','install',p,'--user','--break-system-packages'],stderr=subprocess.DEVNULL)
_i('pygame');import pygame

# .- LCG — doom P_Random soul: A=1664525 C=1013904223 M=2^32
class L:
    A=1664525;C=1013904223;M=1<<32
    def __init__(s,v=0):s.v=v&0xFFFFFFFF
    def n(s):s.v=(s.A*s.v+s.C)%s.M;return s.v
    def r(s):return s.n()/s.M
    def i(s,a,b):return a+int(s.r()*(b-a+1))

# .- chunk constants — CSIZ=23 odd, CMID=11 (odd → guaranteed DFS visit)
# four forced edge-mid passages → adjacent chunks always connect seamlessly
CSIZ=23;CMID=11;MAX_D=52.0;CACHE=256

# .- deterministic per-chunk seed (doom-style hash mixing)
def cseed(ws,cx,cy):
    v=ws^(cx*1664525+1013904223)^(cy*22695477+1)
    return(v*2654435761)&0xFFFFFFFF

# .- iterative DFS perfect maze — P_GroupLines recursive soul, no recursion limit
# four edge midpoints forced open → seamless inter-chunk bridges at all borders
def gen_chunk(ws,cx,cy):
    G=CSIZ;lcg=L(cseed(ws,cx,cy))
    M=[[1]*G for _ in range(G)]
    M[0][CMID]=M[G-1][CMID]=M[CMID][0]=M[CMID][G-1]=0   # edge bridges
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

# .- infinite world: LRU chunk cache (OrderedDict) — doom blockmap soul
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

# .- DDA raycast — R_RenderMaskedSegRange soul, infinite world traversal
def cast(wld,px,py,a):
    dx,dy=math.cos(a),math.sin(a);t=0.04
    while t<MAX_D:
        if wld.cell(px+dx*t,py+dy*t):return t
        t+=0.04
    return MAX_D

# .- pur3 display constants — untouched
W,H=160,60;SC=7;FOV=math.pi/3;GL=" .:-=+*%#@"

def main():
    pygame.init()
    scr=pygame.display.set_mode((W*SC,H*SC))
    pygame.display.set_caption('MAZFALL .- ∞')
    fnt=pygame.font.SysFont('Courier',SC,bold=True)
    clk=pygame.time.Clock()

    # .- glyph cache: pre-render (char,r,g,b) → surface, quantized 8-step palette
    # avoids redundant font.render calls; critical for floor/ceiling char density
    GC={}
    def G_(ch,r,g,b):
        k=(ch,r&0xF8,g&0xF8,b&0xF8)
        if k not in GC:GC[k]=fnt.render(ch,True,(k[1],k[2],k[3]))
        return GC[k]

    wseed=random.randint(0,0xFFFFFFFF)
    wld=World(wseed);px,py,ang=1.5,1.5,0.0

    while True:
        for e in pygame.event.get():
            if e.type==pygame.QUIT or(e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE):
                pygame.quit();return
            # .- N: new world seed — infinite recursion restarts
            if e.type==pygame.KEYDOWN and e.key==pygame.K_n:
                wseed=random.randint(0,0xFFFFFFFF);wld=World(wseed);px,py,ang=1.5,1.5,0.0

        k=pygame.key.get_pressed()
        # .- pur3 movement feel preserved — shift sprint for infinite traversal
        sp=(0.12 if k[pygame.K_LSHIFT]or k[pygame.K_RSHIFT] else 0.06)
        tr=0.04
        if k[pygame.K_a]or k[pygame.K_LEFT]:ang-=tr
        if k[pygame.K_d]or k[pygame.K_RIGHT]:ang+=tr
        mx,my=math.cos(ang)*sp,math.sin(ang)*sp
        if k[pygame.K_w]or k[pygame.K_UP]:
            if not wld.cell(px+mx,py):px+=mx
            if not wld.cell(px,py+my):py+=my
        if k[pygame.K_s]or k[pygame.K_DOWN]:
            if not wld.cell(px-mx,py):px-=mx
            if not wld.cell(px,py-my):py-=my

        # .- render — pur3 terminal scheme untouched
        scr.fill((0,0,0))

        # walls: dda per ray column — pur3 grayscale fade, no fish-eye (pur3 authentic)
        for col in range(W):
            ra=ang-FOV/2+(col/W)*FOV
            d=cast(wld,px,py,ra)
            wh=max(1,int(H/(d+0.001)))
            mid=H//2;top=mid-wh//2;bot=mid+wh//2
            fade=max(40,int(220*(1-d/MAX_D)))
            ch=GL[max(0,min(len(GL)-1,int((1-d/MAX_D)*(len(GL)-1))))]
            surf=G_(ch,fade,fade,fade)
            for row in range(max(0,top),min(H,bot)):scr.blit(surf,(col*SC,row*SC))

        # floor/ceiling gradient — R_DrawSpan soul, pur3 char scheme preserved
        for row in range(H//2):
            cv=int(row/(H//2)*28)
            for col in range(0,W,3):
                scr.blit(G_('.',cv,cv,cv+15),(col*SC,row*SC))
                scr.blit(G_(',',cv+8,cv+4,0),(col*SC,(H-1-row)*SC))

        # minimap — doom automap soul: 3×3 chunk grid around player
        pcx,pcy=int(px)//CSIZ,int(py)//CSIZ
        ms=3;mox,moy=4,4
        for dcy in range(-1,2):
            for dcx in range(-1,2):
                ch_=wld.chunk(pcx+dcx,pcy+dcy)
                bx=mox+(dcx+1)*CSIZ*ms;by_=moy+(dcy+1)*CSIZ*ms
                for ry_ in range(CSIZ):
                    for rx_ in range(CSIZ):
                        c=(70,70,70)if ch_[ry_][rx_]else(25,25,25)
                        pygame.draw.rect(scr,c,(bx+rx_*ms,by_+ry_*ms,ms-1,ms-1))
        # chunk grid lines
        for dc in range(4):
            pygame.draw.line(scr,(40,60,40),(mox+dc*CSIZ*ms,moy),(mox+dc*CSIZ*ms,moy+3*CSIZ*ms-1))
            pygame.draw.line(scr,(40,60,40),(mox,moy+dc*CSIZ*ms),(mox+3*CSIZ*ms-1,moy+dc*CSIZ*ms))
        # player dot — pur3 green
        plx_=int(px)%CSIZ;ply_=int(py)%CSIZ
        pdx_=mox+(CSIZ+plx_)*ms;pdy_=moy+(CSIZ+ply_)*ms
        pygame.draw.rect(scr,(0,255,80),(pdx_,pdy_,ms+1,ms+1))

        # hud — pur3 green label, world coords, seed, controls
        wxd,wyd=int(px),int(py)
        scr.blit(fnt.render(f'MAZFALL .- ∞  [{wxd},{wyd}]  seed:{wseed&0xFFFF:#06x}  N:SEED  SHIFT:SPRINT  ESC',True,(0,210,80)),(3*CSIZ*ms+mox+4,4))

        pygame.display.flip();clk.tick(60)

main()
# the dot sings .- ∞
# infinite recursion begins — the maze has no exit
