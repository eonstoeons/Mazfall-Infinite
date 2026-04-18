#!/usr/bin/env python3
# MAZFALL_ZOMBIE_ALPHA_v0.5 · Doomfall-0.1 soul × Mazfall-α0.02 spine
# ∞ recursive chunks · ∞ zombie respawn · ∞ ammo · chaingun overheat
# WASD/arrows + mouse · SPACE/LMB fire · N new seed · R respawn · ESC quit
import sys,subprocess,math,random,time
def _i(p):
    try:__import__(p)
    except:subprocess.call([sys.executable,"-m","pip","install",p,"--user","-q"])
for p in("pygame","numpy"):_i(p)
import pygame,numpy as np
W,H,S=100,34,10;FV=math.pi/3;FH=FV*.5;P2=math.pi*2;MD=40.;RM=" .:-=+*#%@";RL=9
CZ=21;CM=10;SR=22050;MV=.18;TR=.08;MS=.005  # faster move/turn/mouse
# ── LCG doom P_Random soul ─────────────────────────────────────────
def _cs(w,x,y):return((w^(x*1664525+1013904223)^(y*22695477+1))*2654435761)&0xFFFFFFFF
def _gc(w,cx,cy):
    v=_cs(w,cx,cy);M=[[1]*CZ for _ in range(CZ)]
    M[0][CM]=M[CZ-1][CM]=M[CM][0]=M[CM][CZ-1]=0
    def r():
        nonlocal v;v=(1664525*v+1013904223)&0xFFFFFFFF;return v
    D=[(0,-2),(0,2),(-2,0),(2,0)]
    def sd():
        d=list(D)
        for i in range(3,0,-1):j=r()%(i+1);d[i],d[j]=d[j],d[i]
        return d
    M[1][1]=0;st=[(1,1,sd())]
    while st:
        x,y,ds=st[-1]
        if not ds:st.pop();continue
        dx,dy=ds.pop(0);nx,ny=x+dx,y+dy
        if 1<=nx<CZ-1 and 1<=ny<CZ-1 and M[ny][nx]:
            M[y+dy//2][x+dx//2]=0;M[ny][nx]=0;st.append((nx,ny,sd()))
    return M
CH={}
def cell(ws,wx,wy):
    cx,lx=divmod(int(wx),CZ);cy,ly=divmod(int(wy),CZ);k=(cx,cy)
    if k not in CH:
        if len(CH)>256:CH.pop(next(iter(CH)))
        CH[k]=_gc(ws,cx,cy)
    return CH[k][ly][lx]
def cast(ws,px,py,a):
    dx,dy=math.cos(a),math.sin(a);t=.04
    while t<MD:
        if cell(ws,px+dx*t,py+dy*t):return t
        t+=.04
    return MD
# ── audio ─────────────────────────────────────────────────────────
pygame.mixer.pre_init(SR,-16,1,256);pygame.init()
def _snd(w,A=18000):return pygame.sndarray.make_sound((np.clip(w,-1,1)*A).astype(np.int16))
def _gun():
    d=.08;n=int(SR*d);t=np.linspace(0,d,n,False)
    return _snd(np.random.uniform(-1,1,n)*np.exp(-t*30)*.6+np.sin(P2*np.cumsum(80*np.exp(-t*6)+40)/SR)*np.exp(-t*8))
def _hit():
    d=.22;n=int(SR*d);t=np.linspace(0,d,n,False)
    return _snd(np.random.uniform(-1,1,n)*np.exp(-t*10)*.8,22000)
def _hurt():
    d=.18;n=int(SR*d);t=np.linspace(0,d,n,False)
    return _snd(np.sin(P2*140*t)*np.exp(-t*7)*.7+np.random.uniform(-1,1,n)*np.exp(-t*20)*.3)
SG=_gun();SX=_hit();SH_=_hurt()
scr=pygame.display.set_mode((W*S,H*S));pygame.display.set_caption("MAZFALL_ZOMBIE_ALPHA_v0.5")
fn=pygame.font.SysFont("Courier",S+2,bold=True);clk=pygame.time.Clock()
GC={}
def G(c,v):
    k=(c,v>>3)
    if k not in GC:GC[k]=fn.render(c,True,(v,v,v))
    return GC[k]
CC=[math.cos(-FH+x/W*FV)for x in range(W)];CS_=[math.sin(-FH+x/W*FV)for x in range(W)]
FC=[' 'if abs(y-H/2)/(H/2)<.1 else'.'if(y-H/2)/(H/2)<.45 else':'for y in range(H)]
ws=random.randint(0,0xFFFFFFFF);px,py,ang=1.5,1.5,0.
hp=100;sc=kl=0;lv=1;heat=0.;OH=False
MAXH=100.;HPS=8.;COOL=72.;RES=16.;RATE=.035;ls=lh=0.
def _far(px,py):
    for r in range(4,30,3):
        for _ in range(24):
            a=random.uniform(0,P2);d=r+random.random()*3
            wx,wy=px+math.cos(a)*d,py+math.sin(a)*d
            if not cell(ws,wx,wy):return wx,wy
    return px+5,py+5
Z=[]
def _spawn():
    wx,wy=_far(px,py);Z.append([wx,wy,1+lv//3])
for _ in range(40):_spawn()
pygame.event.set_grab(True);pygame.mouse.set_visible(False)
run=True
while run:
    dt=clk.tick(30)/1000.;now=time.time()
    for e in pygame.event.get():
        if e.type==pygame.QUIT:run=False
        elif e.type==pygame.KEYDOWN:
            if e.key==pygame.K_ESCAPE:run=False
            elif e.key==pygame.K_n:
                ws=random.randint(0,0xFFFFFFFF);CH.clear();px,py=1.5,1.5;Z.clear()
                for _ in range(40+lv*4):_spawn()
            elif e.key==pygame.K_r and hp<=0:
                hp=100;Z.clear()
                for _ in range(40+lv*4):_spawn()
        elif e.type==pygame.MOUSEMOTION and hp>0:ang+=e.rel[0]*MS
    ks=pygame.key.get_pressed()
    if hp>0:
        ca,sa=math.cos(ang),math.sin(ang);fx,fy=ca*MV,sa*MV;rx_,ry_=-sa*MV,ca*MV;dx=dy=0.
        if ks[pygame.K_w]or ks[pygame.K_UP]:dx+=fx;dy+=fy
        if ks[pygame.K_s]or ks[pygame.K_DOWN]:dx-=fx;dy-=fy
        if ks[pygame.K_a]:dx-=rx_;dy-=ry_
        if ks[pygame.K_d]:dx+=rx_;dy+=ry_
        if ks[pygame.K_LEFT]:ang-=TR
        if ks[pygame.K_RIGHT]:ang+=TR
        if not cell(ws,px+dx,py):px+=dx
        if not cell(ws,px,py+dy):py+=dy
        # ── CHAINGUN · ∞ ammo · heat spine ──────────────────────
        if(ks[pygame.K_SPACE]or pygame.mouse.get_pressed()[0])and not OH and now-ls>RATE:
            ls=now;SG.play();heat=min(MAXH,heat+HPS)
            if heat>=MAXH:OH=True
            wd=cast(ws,px,py,ang);best=-1;bd=1e9
            for i,z in enumerate(Z):
                ex,ey=z[0]-px,z[1]-py;d2=ex*ex+ey*ey
                if d2>wd*wd:continue
                d=d2**.5;a=(math.atan2(ey,ex)-ang+math.pi)%P2-math.pi
                if abs(a)<.10+.40/(d+.5)and d<bd:best=i;bd=d
            if best>=0:
                Z[best][2]-=1
                if Z[best][2]<=0:
                    Z.pop(best);SX.play();sc+=10;kl+=1;_spawn();_spawn()  # ∞ recursive: 2-for-1
        if heat>0:heat=max(0.,heat-COOL*dt)
        if OH and heat<RES:OH=False
        # ── zombie AI — tier grows with lv ──────────────────────
        ZSP=.035+lv*.006
        for z in Z:
            ex,ey=px-z[0],py-z[1];d2=ex*ex+ey*ey
            if d2<.0001:continue
            d=d2**.5;vx,vy=ex/d*ZSP,ey/d*ZSP
            if not cell(ws,z[0]+vx,z[1]):z[0]+=vx
            if not cell(ws,z[0],z[1]+vy):z[1]+=vy
            if d2<.49 and now-lh>.8:hp-=2+lv//2;lh=now;SH_.play()
        if kl>=lv*20:lv+=1;[_spawn()for _ in range(3)]
        if hp<=0:SH_.play()
    # ── render · Doomfall-0.1 minimalist soul ─────────────────────
    scr.fill((0,0,0));ca_=math.cos(ang);sa_=math.sin(ang);zb=[MD]*W
    for x in range(W):
        co=CC[x];so=CS_[x];ra=math.atan2(sa_*co+ca_*so,ca_*co-sa_*so)
        d=cast(ws,px,py,ra)*co;zb[x]=d
        wh=int(H/(d+.1));top=(H-wh)>>1
        ch=RM[max(0,min(RL,int((1-d/MD)*RL)))];v=max(60,int(220*(1-d/MD)))
        for y in range(H):
            if top<=y<top+wh:scr.blit(G(ch,v),(x*S,y*S))
            elif y>top+wh and FC[y]!=' ':scr.blit(G(FC[y],95),(x*S,y*S))
    # sprites · painter-sorted · zbuf-gated
    for z in sorted(Z,key=lambda z:-((z[0]-px)**2+(z[1]-py)**2)):
        rx,ry=z[0]-px,z[1]-py;d=math.hypot(rx,ry)
        if d<.2:continue
        a=(math.atan2(ry,rx)-ang+math.pi)%P2-math.pi
        if abs(a)>FH+.15:continue
        col=int((a/FV+.5)*W);sh=int(H/(d+.1));sw=max(1,int(sh*.55))
        top=max(0,(H-sh)>>1);lft=col-(sw>>1)
        for xx in range(max(0,lft),min(W,lft+sw)):
            if d>=zb[xx]:continue
            rxr=(xx-lft)/max(1,sw)
            for yy in range(top,min(H,top+sh)):
                ryr=(yy-top)/max(1,sh)
                if ryr<.2 and.35<rxr<.65:g='o'
                elif ryr<.72 and.18<rxr<.82:g='z'
                elif ryr>=.72 and rxr<.4:g='/'
                elif ryr>=.72 and rxr>.6:g='\\'
                elif ryr>=.72:g='|'
                else:g=None
                if g:scr.blit(G(g,220),(xx*S,yy*S))
    if hp>0:scr.blit(G('+',220),(W*S//2,H*S//2))
    # heat bar · 8-slot eightfold soul
    bw=int(W*S*.22);bh=8;bx=(W*S-bw)//2;by=H*S//2+S*2
    pygame.draw.rect(scr,(40,40,40),(bx,by,bw,bh))
    hf=int(bw*heat/MAXH)
    if hf>0:
        c=(255,80,80)if OH else(255,200,60)if heat>60 else(80,220,80)
        if OH and int(now*8)%2:c=(255,200,50)
        pygame.draw.rect(scr,c,(bx,by,hf,bh))
    hud=f"HP:{hp:3d} SC:{sc} K:{kl} LV:{lv} Z:{len(Z)} {'[OVERHEAT]'if OH else f'[{int(heat):02d}%]'}"
    scr.blit(fn.render(hud,True,(120,255,120)if hp>50 else(255,220,80)if hp>20 else(255,80,80)),(8,4))
    if hp<=0:
        m=fn.render("ELIMINATED — R:RESPAWN  N:NEW SEED",True,(255,60,60))
        scr.blit(m,(W*S//2-m.get_width()//2,H*S//2+60))
    pygame.display.flip()
pygame.quit();sys.exit()
# .- ∞ recurse · the maze has no exit
