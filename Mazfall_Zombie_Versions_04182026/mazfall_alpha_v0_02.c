/* MAZFALL_ALPHA_v0.02 — pure C · POSIX terminal · ANSI 256-color
 * Faithful port of _src__Mazfall_Alpha_v0_02.py
 * Infinite chunked LCG maze · DDA raycaster · ZTIERS · boss · scatter
 * chaingun overheat · blood particles · minimap · combo kills · powerups
 *
 * build:  cc -O2 -lm mazfall_alpha_v0_02.c -o mazfall
 * run:    ./mazfall
 *
 * Controls: WASD move · JL turn · SPACE fire · E scatter · R respawn
 *           N new seed · Q/ESC quit
 * .- ∞ recurse · the maze has no exit
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <unistd.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <fcntl.h>

/* ── screen / world constants ──────────────────────────────────── */
#define W       120
#define H       40
#define HH      (H/2)
#define HW      (W/2)
#define MAX_D   52.0
#define FV      1.0471975511965976   /* pi/3  */
#define FH      0.5235987755982988   /* pi/6  */
#define P2      6.28318530717958648
#define SR      22050

/* chunk constants */
#define CSIZ    23
#define CMID    11
#define CACHE   512

/* zombie pool */
#define ZMAX_POOL   512
#define PW_MAX      8
#define BL_MAX      128

/* chaingun */
#define CGUN_RATE       0.035
#define HEAT_MAX        100.0
#define HEAT_PER_SHOT   8.0
#define COOL_RATE       72.0
#define OH_RESUME       16.0

/* boss */
#define BOSS_BASE_HP    25
#define BOSS_SPD        0.022
#define BOSS_DMG        15
#define BOSS_REACH      0.65

/* scatter */
#define SCATTER_COOL    2.5
#define SCATTER_RAYS    5
#define SCATTER_SPREAD  0.13

static const char RM[] = " .:-=+*#%@";
#define RL 9

/* ── LCG — doom P_Random soul ──────────────────────────────────── */
typedef struct { unsigned int v; } LCG;
static void lcg_init(LCG *l, unsigned int v) { l->v = v & 0xFFFFFFFF; }
static unsigned int lcg_next(LCG *l) {
    l->v = (1664525u * l->v + 1013904223u) & 0xFFFFFFFF;
    return l->v;
}
static double lcg_rf(LCG *l)  { return lcg_next(l) / 4294967296.0; }
static int    lcg_ri(LCG *l, int a, int b) { return a + (int)(lcg_rf(l)*(b-a+1)); }

/* ── chunk cache ───────────────────────────────────────────────── */
typedef unsigned char cell_t;
typedef struct {
    int cx, cy;
    cell_t m[CSIZ][CSIZ];
    int lru;
} Chunk;

static Chunk CHUNKS[CACHE];
static int   CH_N = 0;
static int   CH_TICK = 0;

static unsigned int cseed(unsigned int ws, int cx, int cy) {
    unsigned int v = ws ^ ((unsigned)cx*1664525u+1013904223u)
                       ^ ((unsigned)cy*22695477u+1u);
    return (v * 2654435761u) & 0xFFFFFFFF;
}

static void gen_chunk(unsigned int ws, int cx, int cy, Chunk *dst) {
    LCG lcg; lcg_init(&lcg, cseed(ws, cx, cy));
    dst->cx = cx; dst->cy = cy;
    int G = CSIZ;
    for (int y = 0; y < G; y++)
        for (int x = 0; x < G; x++) dst->m[y][x] = 1;
    /* four edge bridges */
    dst->m[0][CMID] = dst->m[G-1][CMID] = 0;
    dst->m[CMID][0] = dst->m[CMID][G-1] = 0;

    /* iterative DFS carver */
    static int sx[CSIZ*CSIZ], sy_[CSIZ*CSIZ];
    static int dirs[CSIZ*CSIZ][4][2];
    static int dptr[CSIZ*CSIZ];
    int sp = 0;
    /* shuffle helper — Fisher-Yates via LCG */
    int DD[4][2] = {{0,-2},{0,2},{-2,0},{2,0}};
    dst->m[1][1] = 0;
    sx[0]=1; sy_[0]=1;
    /* copy dirs for frame 0 */
    for (int k=0;k<4;k++){dirs[0][k][0]=DD[k][0];dirs[0][k][1]=DD[k][1];}
    for (int i=3;i>0;i--){int j=lcg_ri(&lcg,0,i);int t0=dirs[0][i][0],t1=dirs[0][i][1];dirs[0][i][0]=dirs[0][j][0];dirs[0][i][1]=dirs[0][j][1];dirs[0][j][0]=t0;dirs[0][j][1]=t1;}
    dptr[0]=0; sp=1;

    while (sp > 0) {
        int top = sp-1;
        int x = sx[top], y = sy_[top];
        if (dptr[top] >= 4) { sp--; continue; }
        int dx = dirs[top][dptr[top]][0];
        int dy = dirs[top][dptr[top]][1];
        dptr[top]++;
        int nx = x+dx, ny = y+dy;
        if (nx>=1 && nx<G-1 && ny>=1 && ny<G-1 && dst->m[ny][nx]) {
            dst->m[y+dy/2][x+dx/2] = 0;
            dst->m[ny][nx] = 0;
            sx[sp]=nx; sy_[sp]=ny;
            for (int k=0;k<4;k++){dirs[sp][k][0]=DD[k][0];dirs[sp][k][1]=DD[k][1];}
            for (int i=3;i>0;i--){int j=lcg_ri(&lcg,0,i);int t0=dirs[sp][i][0],t1=dirs[sp][i][1];dirs[sp][i][0]=dirs[sp][j][0];dirs[sp][i][1]=dirs[sp][j][1];dirs[sp][j][0]=t0;dirs[sp][j][1]=t1;}
            dptr[sp]=0; sp++;
        }
    }
}

static Chunk *get_chunk(unsigned int ws, int cx, int cy) {
    for (int i=0;i<CH_N;i++)
        if (CHUNKS[i].cx==cx && CHUNKS[i].cy==cy)
            { CHUNKS[i].lru=++CH_TICK; return &CHUNKS[i]; }
    int slot;
    if (CH_N < CACHE) slot=CH_N++;
    else {
        int lo=CHUNKS[0].lru, li=0;
        for (int i=1;i<CH_N;i++) if(CHUNKS[i].lru<lo){lo=CHUNKS[i].lru;li=i;}
        slot=li;
    }
    gen_chunk(ws, cx, cy, &CHUNKS[slot]);
    CHUNKS[slot].lru=++CH_TICK;
    return &CHUNKS[slot];
}

static int ifloor(double v) { return (int)floor(v); }

static int world_cell(unsigned int ws, double wx, double wy) {
    int ix=ifloor(wx), iy=ifloor(wy);
    int cx=ix/CSIZ, cy=iy/CSIZ;
    int lx=ix%CSIZ, ly=iy%CSIZ;
    if (lx<0){cx--;lx+=CSIZ;} if(ly<0){cy--;ly+=CSIZ;}
    Chunk *ch = get_chunk(ws,cx,cy);
    if (lx<0||lx>=CSIZ||ly<0||ly>=CSIZ) return 1;
    return ch->m[ly][lx];
}

/* ── DDA ────────────────────────────────────────────────────────── */
static double cast(unsigned int ws, double px, double py, double a) {
    double dx=cos(a), dy=sin(a), t=0.04;
    while (t < MAX_D) {
        if (world_cell(ws, px+dx*t, py+dy*t)) return t;
        t += 0.04;
    }
    return MAX_D;
}

static double cast_face(unsigned int ws, double px, double py, double a, int *ew) {
    double dx=cos(a), dy=sin(a), t=0.04;
    while (t < MAX_D) {
        double hx=px+dx*t, hy=py+dy*t;
        if (world_cell(ws,hx,hy)) {
            double fx=fmod(hx,1.)-0.5, fy=fmod(hy,1.)-0.5;
            if(fx<0)fx=-fx; if(fy<0)fy=-fy;
            *ew = fx < fy;
            return t;
        }
        t += 0.04;
    }
    *ew=1; return MAX_D;
}

/* ── floor spawn ────────────────────────────────────────────────── */
static void far_floor(unsigned int ws, double px, double py, double *ox, double *oy) {
    for (int ring=4; ring<40; ring+=4) {
        for (int k=0; k<48; k++) {
            double a = ((double)rand()/RAND_MAX)*P2;
            double d = ring + ((double)rand()/RAND_MAX)*4.0;
            double wx=px+cos(a)*d, wy=py+sin(a)*d;
            if (!world_cell(ws,wx,wy)) { *ox=wx; *oy=wy; return; }
        }
    }
    *ox=px+8; *oy=py+8;
}

/* ── ZTIERS ─────────────────────────────────────────────────────── */
typedef struct { int hp; double spd; char body,head; int dmg; double see; int strafe; } ZTier;
static const ZTier ZTIERS[] = {
    {1,.018,'z','o',2, 8.0,0},
    {1,.025,'z','o',2, 9.0,0},
    {2,.032,'Z','O',3,10.0,0},
    {2,.040,'Z','O',3,12.0,0},
    {3,.050,'Z','0',4,14.0,1},
    {3,.060,'Z','0',5,16.0,1},
    {4,.070,'B','O',6,18.0,1},
    {5,.085,'B','@',7,20.0,1},
    {6,.100,'M','@',8,22.0,1},
};
#define NTIERS 9
static const ZTier *ztier(int lv) { return &ZTIERS[(lv-1)/5 < NTIERS ? (lv-1)/5 : NTIERS-1]; }
static int zcount(int lv) {
    int s=40; for(int l=0;l<lv;l++) s+=l+1;
    return s>120?120:s;
}

/* ── terminal raw mode ──────────────────────────────────────────── */
static struct termios orig_tio;
static void tio_restore(void) {
    tcsetattr(STDIN_FILENO,TCSANOW,&orig_tio);
    printf("\x1b[?25h\x1b[0m\x1b[2J\x1b[H"); fflush(stdout);
}
static void tio_raw(void) {
    tcgetattr(STDIN_FILENO,&orig_tio);
    struct termios t=orig_tio;
    t.c_lflag &= ~(ICANON|ECHO);
    t.c_cc[VMIN]=0; t.c_cc[VTIME]=0;
    tcsetattr(STDIN_FILENO,TCSANOW,&t);
    printf("\x1b[?25l\x1b[2J"); fflush(stdout);
    atexit(tio_restore);
}
static int kb_read(char *c) { return read(STDIN_FILENO,c,1)==1; }
static double now_s(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts); return ts.tv_sec+ts.tv_nsec*1e-9; }

/* ── framebuffer ────────────────────────────────────────────────── */
static char BF[H][W+1];
static unsigned char SH[H][W];     /* shade 0–220 */
static double ZBuf[W];

/* precomputed angle offsets */
static double CC[W], CS_[W];

/* floor char table */
static char FC[H];

/* ── zombie pool ─────────────────────────────────────────────────── */
typedef struct { double x,y; int hp; double fa,ft; } Zombie;
static Zombie Z[ZMAX_POOL];
static int    Z_ALIVE[ZMAX_POOL];
static int    ZCOUNT=0;

/* ── blood particles: [x,y,vx,vy,life,glyph] ─────────────────────── */
typedef struct { double x,y,vx,vy,life; char g; } Blood;
static Blood BL[BL_MAX];
static int BL_N=0;
static const char BC[]="@%#*+:;,.~oO";
#define NBC 12

static void spl(double x, double y) {
    for (int i=0;i<22;i++) {
        if (BL_N>=BL_MAX) { /* evict random */ BL[rand()%BL_MAX]=BL[BL_N-1]; BL_N--; }
        double a=((double)rand()/RAND_MAX)*P2;
        double spd=0.2+((double)rand()/RAND_MAX)*1.2;
        BL[BL_N++]=(Blood){
            x+((double)rand()/RAND_MAX)*.3-.15,
            y+((double)rand()/RAND_MAX)*.3-.15,
            cos(a)*spd, sin(a)*spd,
            0.5+((double)rand()/RAND_MAX)*.7,
            BC[rand()%NBC]
        };
    }
}

/* ── powerups ────────────────────────────────────────────────────── */
typedef struct { double x,y; char kind; } PUp;
static PUp PW[PW_MAX];
static int PW_N=0;

static unsigned int wseed=0;

static void ppw(double px, double py) {
    PW_N=0;
    for (int i=0;i<7 && i<PW_MAX;i++) {
        double wx,wy; far_floor(wseed,px,py,&wx,&wy);
        PW[PW_N++]=(PUp){wx,wy,(rand()%2)?'H':'S'};
    }
}

/* ── combo message table ──────────────────────────────────────────── */
static const char *combo_msg(int cb) {
    switch(cb) {
        case 2: return "Double kill";
        case 3: return "Triple kill";
        case 4: return "Overkill";
        case 5: return "Killing spree";
        case 7: return "Unstoppable";
        default: if(cb>=10&&cb%5==0) return "Godlike"; return NULL;
    }
}

/* ── minimap ──────────────────────────────────────────────────────── */
static void draw_minimap(double px, double py) {
    int pcx=(int)px/CSIZ, pcy=(int)py/CSIZ;
    int ms=2, mox=4, moy=4;
    for (int dcy=-1;dcy<=1;dcy++) {
        for (int dcx=-1;dcx<=1;dcx++) {
            Chunk *ch=get_chunk(wseed,pcx+dcx,pcy+dcy);
            for (int ry=0;ry<CSIZ;ry++) {
                for (int rx=0;rx<CSIZ;rx++) {
                    int bx=mox+(dcx+1)*CSIZ*ms+rx*ms;
                    int by=moy+(dcy+1)*CSIZ*ms+ry*ms;
                    if (bx>=0&&bx<W-1&&by>=0&&by<H-1) {
                        char c=ch->m[ry][rx]?'#':'.';
                        BF[by][bx]=c;
                        SH[by][bx]=ch->m[ry][rx]?55:18;
                    }
                }
            }
        }
    }
    /* zombie dots */
    for (int i=0;i<ZCOUNT;i++) {
        if (!Z_ALIVE[i]) continue;
        int zxc=(int)Z[i].x/CSIZ, zyc=(int)Z[i].y/CSIZ;
        int mx=mox+(CSIZ+(int)Z[i].x%CSIZ+(zxc-pcx)*CSIZ)*ms;
        int my=moy+(CSIZ+(int)Z[i].y%CSIZ+(zyc-pcy)*CSIZ)*ms;
        if (mx>=0&&mx<W&&my>=0&&my<H) { BF[my][mx]='*'; SH[my][mx]=200; }
    }
    /* player dot */
    int plx=mox+(CSIZ+(int)px%CSIZ)*ms;
    int ply=moy+(CSIZ+(int)py%CSIZ)*ms;
    if (plx>=0&&plx<W&&ply>=0&&ply<H) { BF[ply][plx]='@'; SH[ply][plx]=220; }
}

/* ── ANSI flush ───────────────────────────────────────────────────── */
static void flush_frame(int dead, int hp) {
    /* color tint based on health */
    int rv=200, gv=200, bv=200;
    if (dead)       { rv=120; gv=30; bv=30; }
    else if (hp<25) { rv=220; gv=100; bv=100; }

    printf("\x1b[H");
    for (int y=0;y<H;y++) {
        int last_sh=-1;
        for (int x=0;x<W;x++) {
            char c=BF[y][x]; if(!c)c=' ';
            int sh=SH[y][x];
            if (sh!=last_sh) {
                if (sh==0) printf("\x1b[0m");
                else {
                    int r=rv*sh/220, g=gv*sh/220, b=bv*sh/220;
                    if(r>255)r=255; if(g>255)g=255; if(b>255)b=255;
                    printf("\x1b[38;2;%d;%d;%dm",r,g,b);
                }
                last_sh=sh;
            }
            putchar(c);
        }
        printf("\x1b[0m\n"); last_sh=-1;
    }
}

/* ── spawn zombie ────────────────────────────────────────────────── */
static void spawn_zombie(int i, double px, double py) {
    double wx,wy; far_floor(wseed,px,py,&wx,&wy);
    const ZTier *t=ztier(1); /* tier set at think time */
    Z[i].x=wx; Z[i].y=wy; Z[i].hp=t->hp;
    Z[i].fa=((double)rand()/RAND_MAX)*P2; Z[i].ft=0.;
    Z_ALIVE[i]=1;
}

/* ── next wave ──────────────────────────────────────────────────────── */
static int lv=1;
static void nxt_wave(double *px, double *py, double *ang,
                     int *kll,
                     double *boss_x, double *boss_y, int *boss_hp, int *boss_alive) {
    lv++;
    wseed=(unsigned int)(((unsigned long)rand()<<16)^rand()^(unsigned)time(NULL));
    *px=1.5; *py=1.5; *ang=((double)rand()/RAND_MAX)*P2;
    *kll=0;
    BL_N=0;
    int new_n=zcount(lv);
    if(new_n>ZMAX_POOL)new_n=ZMAX_POOL;
    ZCOUNT=new_n;
    for(int i=0;i<ZCOUNT;i++) spawn_zombie(i,*px,*py);
    ppw(*px,*py);
    if (lv%5==0) {
        far_floor(wseed,*px,*py,boss_x,boss_y);
        *boss_hp=BOSS_BASE_HP+lv*3; *boss_alive=1;
        fprintf(stderr,"[BOSS] Wave %d — %d HP\n",lv,*boss_hp);
    }
}

/* ══════════════════════════════════════════════════════════════════
   MAIN
   ══════════════════════════════════════════════════════════════════ */
int main(void) {
    srand((unsigned)time(NULL));
    wseed=(unsigned int)(((unsigned long)rand()<<16)^rand()^(unsigned)time(NULL));

    /* precompute angle LUT */
    for (int x=0;x<W;x++) {
        CC[x]=cos(-FH+(double)x/W*FV);
        CS_[x]=sin(-FH+(double)x/W*FV);
    }
    /* floor char table */
    for (int y=0;y<H;y++) {
        double f=(double)(y-HH)/(double)HH;
        if(f<=.15) FC[y]=' ';
        else if(f<=.4) FC[y]=',';
        else if(f<=.7) FC[y]='.';
        else FC[y]=':';
    }

    double px=1.5, py=1.5, ang=0.;
    int hp=100, sc=0, kl=0, kll=0;
    double sm=1.;
    int cb=0, mu=0, dead=0;
    double ls=0,lh=0,lsp=0,lr=0,lkt=0,lsc=0;
    double heat=0.; int OH=0;
    double smk_t=0.;
    int boss_alive=0; double boss_x=0,boss_y=0; int boss_hp=0;

    ZCOUNT=zcount(1); if(ZCOUNT>ZMAX_POOL)ZCOUNT=ZMAX_POOL;
    for (int i=0;i<ZCOUNT;i++) spawn_zombie(i,px,py);
    ppw(px,py);

    tio_raw();
    double last=now_s();
    int run=1;

    while (run) {
        double t_now=now_s();
        double dt=t_now-last; last=t_now;
        if(dt>0.1)dt=0.1;

        /* ── INPUT ──────────────────────────────────────────────── */
        char c;
        while (kb_read(&c)) {
            if (c==27||c=='q'||c=='Q') run=0;
            if (c=='r'||c=='R') {
                if (dead) {
                    hp=100; sm=1.; dead=0; cb=0; boss_alive=0;
                    for(int i=0;i<ZCOUNT;i++) spawn_zombie(i,px,py);
                    lh=t_now;
                }
            }
            if (c=='n'||c=='N') {
                wseed=(unsigned int)(((unsigned long)rand()<<16)^rand()^(unsigned)time(NULL));
                BL_N=0; boss_alive=0;
                for(int i=0;i<ZCOUNT;i++) spawn_zombie(i,px,py);
                ppw(px,py);
            }
        }
        if (!dead) {
            /* poll held keys via /dev/stdin select with zero timeout */
            fd_set fds; FD_ZERO(&fds); FD_SET(STDIN_FILENO,&fds);
            struct timeval tv={0,0};
            /* read all pending — movement via repeated char */
            char buf[64]; int nb=(int)read(STDIN_FILENO,buf,sizeof(buf));
            double mv=0.09*sm;
            double ca=cos(ang), sa=sin(ang);
            double fx=ca*mv,fy=sa*mv,sx_=-sa*mv,sy_=ca*mv;
            double ddx=0,ddy=0;
            for(int bi=0;bi<nb;bi++) {
                char k=buf[bi];
                if(k=='w'||k=='W'){ddx+=fx;ddy+=fy;}
                if(k=='s'||k=='S'){ddx-=fx;ddy-=fy;}
                if(k=='a'||k=='A'){ddx-=sx_;ddy-=sy_;}
                if(k=='d'||k=='D'){ddx+=sx_;ddy+=sy_;}
                if(k=='j'||k=='J') ang-=.08;
                if(k=='l'||k=='L') ang+=.08;
                if(k=='e'||k=='E') {
                    /* scatter blast */
                    if (t_now-lsc>SCATTER_COOL && !dead) {
                        lsc=t_now; mu=6;
                        for (int rk=0;rk<SCATTER_RAYS;rk++) {
                            double ra=ang+(rk-(SCATTER_RAYS-1)/2.)*SCATTER_SPREAD;
                            double wd=cast(wseed,px,py,ra);
                            int best=-1; double bd=1e9;
                            for (int i=0;i<ZCOUNT;i++) {
                                if(!Z_ALIVE[i])continue;
                                double rx_=Z[i].x-px,ry_=Z[i].y-py,d2=rx_*rx_+ry_*ry_;
                                if(d2>wd*wd)continue;
                                double d_=sqrt(d2);
                                double a_=atan2(ry_,rx_)-ra;
                                while(a_>M_PI)a_-=P2; while(a_<-M_PI)a_+=P2;
                                if(fabs(a_)<.16+.4/(d_+.5)&&d_<bd){best=i;bd=d_;}
                            }
                            if(best>=0){
                                spl(Z[best].x,Z[best].y);
                                Z[best].hp--;
                                if(Z[best].hp<=0){
                                    Z_ALIVE[best]=0;
                                    kl++;kll++;
                                    cb=(t_now-lkt<2.5)?cb+1:1; lkt=t_now;
                                    sc+=10*cb;
                                    spawn_zombie(best,px,py);
                                }
                            }
                            if(boss_alive){
                                double brx=boss_x-px,bry=boss_y-py,bd2=brx*brx+bry*bry;
                                if(bd2<wd*wd){
                                    double bd_=sqrt(bd2);
                                    double ba=atan2(bry,brx)-ra;
                                    while(ba>M_PI)ba-=P2; while(ba<-M_PI)ba+=P2;
                                    if(fabs(ba)<.22){boss_hp--;spl(boss_x,boss_y);
                                        if(boss_hp<=0){boss_alive=0;sc+=500;kl++;kll=kll>9?kll:9;cb=(t_now-lkt<2.5)?cb+1:1;lkt=t_now;}}
                                }
                            }
                        }
                    }
                }
                if((k==' ')&&!OH&&t_now-ls>CGUN_RATE) {
                    ls=t_now; mu=3;
                    /* knife at ≤0.5u */
                    int knife_hit=0;
                    for(int i=0;i<ZCOUNT;i++){
                        if(!Z_ALIVE[i])continue;
                        double ex=Z[i].x-px,ey=Z[i].y-py;
                        if(ex*ex+ey*ey<=0.25){
                            Z[i].hp-=2; spl(Z[i].x,Z[i].y); knife_hit=1;
                            if(Z[i].hp<=0){Z_ALIVE[i]=0;kl++;kll++;cb=(t_now-lkt<2.5)?cb+1:1;lkt=t_now;sc+=10*cb;spawn_zombie(i,px,py);}
                        }
                    }
                    if(!knife_hit){
                        /* chaingun */
                        heat=heat+HEAT_PER_SHOT; if(heat>HEAT_MAX){heat=HEAT_MAX;OH=1;smk_t=2.;}
                        double wd=cast(wseed,px,py,ang);
                        int best=-1; double bd=1e9;
                        for(int i=0;i<ZCOUNT;i++){
                            if(!Z_ALIVE[i])continue;
                            double rx_=Z[i].x-px,ry_=Z[i].y-py,d2=rx_*rx_+ry_*ry_;
                            if(d2>wd*wd)continue;
                            double d_=sqrt(d2);
                            double a_=atan2(ry_,rx_)-ang;
                            while(a_>M_PI)a_-=P2; while(a_<-M_PI)a_+=P2;
                            if(fabs(a_)<.10+.45/(d_+.5)&&d_<bd){best=i;bd=d_;}
                        }
                        if(best>=0){
                            spl(Z[best].x,Z[best].y);
                            Z[best].hp--;
                            if(Z[best].hp<=0){Z_ALIVE[best]=0;kl++;kll++;cb=(t_now-lkt<2.5)?cb+1:1;lkt=t_now;sc+=10*cb;spawn_zombie(best,px,py);}
                        }
                        if(boss_alive){
                            double brx=boss_x-px,bry=boss_y-py,bd2=brx*brx+bry*bry;
                            if(bd2<wd*wd){
                                double bd_=sqrt(bd2);
                                double ba=atan2(bry,brx)-ang;
                                while(ba>M_PI)ba-=P2; while(ba<-M_PI)ba+=P2;
                                if(fabs(ba)<.15+.30/(bd_+.5)){boss_hp--;spl(boss_x,boss_y);
                                    if(boss_hp<=0){boss_alive=0;sc+=500;kl++;kll=kll>9?kll:9;cb=(t_now-lkt<2.5)?cb+1:1;lkt=t_now;}}
                            }
                        }
                    }
                }
            }
            if(!world_cell(wseed,px+ddx,py))px+=ddx;
            if(!world_cell(wseed,px,py+ddy))py+=ddy;

            /* heat decay */
            if(heat>0){heat-=COOL_RATE*dt;if(heat<0)heat=0;}
            if(OH&&heat<=OH_RESUME){OH=0;}

            /* ── ZOMBIE THINK ────────────────────────────────────── */
            const ZTier *ct=ztier(lv);
            for(int i=0;i<ZCOUNT;i++){
                if(!Z_ALIVE[i])continue;
                double zx=Z[i].x,zy=Z[i].y;
                double dx=px-zx,dy_=py-zy,d2=dx*dx+dy_*dy_;
                if(d2<.0001)continue;
                double d=sqrt(d2);
                double vx,vy;
                if(d>ct->see){
                    if(lv<=4){
                        Z[i].fa+=((double)rand()/RAND_MAX)*.6-.3;
                        vx=cos(Z[i].fa)*ct->spd*.5; vy=sin(Z[i].fa)*ct->spd*.5;
                    } else { vx=dx/d*ct->spd*.4; vy=dy_/d*ct->spd*.4; }
                } else {
                    vx=dx/d*ct->spd; vy=dy_/d*ct->spd;
                    if(ct->strafe){
                        Z[i].ft-=dt;
                        if(Z[i].ft<=0){Z[i].fa=((rand()%2)?-1.:1.)*(.4+((double)rand()/RAND_MAX)*.5);Z[i].ft=.6+((double)rand()/RAND_MAX)*1.2;}
                        double fl=Z[i].fa;
                        vx+=(-dy_/d)*fl*ct->spd*.6; vy+=(dx/d)*fl*ct->spd*.6;
                    }
                }
                double nx=zx+vx,ny=zy+vy;
                if(!world_cell(wseed,nx,zy)) Z[i].x=nx;
                else Z[i].fa=((double)rand()/RAND_MAX)*P2;
                if(!world_cell(wseed,Z[i].x,ny)) Z[i].y=ny;
                else Z[i].fa=((double)rand()/RAND_MAX)*P2;
                if(d2<.49&&t_now-lh>.8){hp-=ct->dmg;lh=t_now;}
            }

            /* ── BOSS THINK ───────────────────────────────────────── */
            if(boss_alive){
                double bdx=px-boss_x,bdy_=py-boss_y,bd=hypot(bdx,bdy_)+.0001;
                double nvx=bdx/bd*BOSS_SPD,nvy=bdy_/bd*BOSS_SPD;
                if(!world_cell(wseed,boss_x+nvx,boss_y))boss_x+=nvx;
                if(!world_cell(wseed,boss_x,boss_y+nvy))boss_y+=nvy;
                double bdist2=(boss_x-px)*(boss_x-px)+(boss_y-py)*(boss_y-py);
                if(bdist2<BOSS_REACH*BOSS_REACH&&t_now-lh>.8){hp-=BOSS_DMG;lh=t_now;}
            }

            if(hp<=0){hp=0;dead=1;cb=0;}

            /* ── power pickups ─────────────────────────────────────── */
            for(int i=PW_N-1;i>=0;i--){
                double ex=PW[i].x-px,ey=PW[i].y-py;
                if(ex*ex+ey*ey<.36){
                    if(PW[i].kind=='H'){hp=100;}
                    else{sm=sm+.3;if(sm>3.5)sm=3.5;}
                    sc+=5;
                    PW[i]=PW[--PW_N];
                }
            }
            if(PW_N==0) ppw(px,py);
            if(hp<100&&t_now-lh>2.&&t_now-lr>.3){hp++;if(hp>100)hp=100;lr=t_now;}
            if(kll>=10) nxt_wave(&px,&py,&ang,&kll,&boss_x,&boss_y,&boss_hp,&boss_alive);
            if(cb>0&&t_now-lkt>2.5)cb=0;
        }

        /* ── BLOOD PARTICLES ──────────────────────────────────────── */
        for(int i=0;i<BL_N;){
            BL[i].x+=BL[i].vx*dt; BL[i].y+=BL[i].vy*dt;
            BL[i].vx*=.9; BL[i].vy*=.9; BL[i].life-=dt;
            if(BL[i].life<=0){BL[i]=BL[--BL_N];}else i++;
        }

        /* ── RENDER ───────────────────────────────────────────────── */
        for(int y=0;y<H;y++){memset(BF[y],' ',W);BF[y][W]=0;memset(SH[y],0,W);}
        for(int x=0;x<W;x++) ZBuf[x]=MAX_D;

        double ca_=cos(ang), sa_=sin(ang);
        for(int x=0;x<W;x++){
            double co=CC[x],so=CS_[x];
            double rca=ca_*co-sa_*so, rsa=sa_*co+ca_*so;
            double ra=atan2(rsa,rca);
            int ew; double raw=cast_face(wseed,px,py,ra,&ew);
            double d=raw*co; ZBuf[x]=d;
            int wh=(int)(H/(d+.1)), top=(H-wh)>>1;
            int si=(int)((1.-d/MAX_D)*RL); if(si<0)si=0;if(si>RL)si=RL;
            char ch=RM[si];
            int fb=(int)(220.*(1.-d/MAX_D)); if(fb<40)fb=40;
            int fade=ew?fb:(int)(fb*.65); if(fade<28)fade=28;
            for(int y=0;y<H;y++){
                if(y>=top&&y<top+wh){BF[y][x]=ch;SH[y][x]=(unsigned char)fade;}
                else if(y>top+wh){char fc=FC[y];if(fc!=' '){BF[y][x]=fc;SH[y][x]=55;}}
            }
        }

        /* minimap */
        draw_minimap(px,py);

        /* ── SPRITES — painter sort ─────────────────────────────── */
        /* collect all sprite entries */
        typedef struct { double x,y,d2; int kind; int idx; } Spr;
        static Spr sprs[ZMAX_POOL+2+PW_MAX];
        int NS=0;
        for(int i=0;i<ZCOUNT;i++){
            if(!Z_ALIVE[i])continue;
            double rx=Z[i].x-px,ry=Z[i].y-py;
            sprs[NS++]=(Spr){Z[i].x,Z[i].y,rx*rx+ry*ry,0,i};
        }
        for(int i=0;i<PW_N;i++){
            double rx=PW[i].x-px,ry=PW[i].y-py;
            sprs[NS++]=(Spr){PW[i].x,PW[i].y,rx*rx+ry*ry,1,i};
        }
        if(boss_alive){
            double rx=boss_x-px,ry=boss_y-py;
            sprs[NS++]=(Spr){boss_x,boss_y,rx*rx+ry*ry,2,0};
        }
        /* insertion sort descending */
        for(int i=1;i<NS;i++){
            Spr k=sprs[i];int j=i-1;
            while(j>=0&&sprs[j].d2<k.d2){sprs[j+1]=sprs[j];j--;}
            sprs[j+1]=k;
        }
        const ZTier *ct=ztier(lv);
        for(int n=0;n<NS;n++){
            Spr *sp=&sprs[n];
            double rx=sp->x-px,ry=sp->y-py,d=sqrt(sp->d2);
            if(d<.2)continue;
            double a=atan2(ry,rx)-ang;
            while(a>M_PI)a-=P2; while(a<-M_PI)a+=P2;
            if(fabs(a)>FH+.15)continue;
            int col=(int)((a/FV+.5)*W);
            int sh,sw;
            if(sp->kind==2){sh=(int)(H/(d+.1)*1.75);sw=(int)(sh*.88);if(sw<1)sw=1;}
            else{sh=(int)(H/(d+.1));sw=(int)(sh*.55);if(sw<1)sw=1;}
            int top=(H-sh)>>1; if(top<0)top=0;
            int lft=col-(sw>>1);
            for(int x=lft<0?0:lft;x<lft+sw&&x<W;x++){
                if(d>=ZBuf[x])continue;
                double rxr=(double)(x-lft)/(sw>0?sw:1);
                for(int y=top;y<top+sh&&y<H;y++){
                    double ryr=(double)(y-top)/(sh>0?sh:1);
                    char g=0;
                    if(sp->kind==0){/* zombie */
                        if(ryr<.18&&rxr>.35&&rxr<.65) g=ct->head;
                        else if(ryr<.72&&rxr>.18&&rxr<.82) g=ct->body;
                        else if(ryr>=.72&&rxr<.4) g='/';
                        else if(ryr>=.72&&rxr>.6) g='\\';
                        else if(ryr>=.72) g='|';
                    } else if(sp->kind==2){/* boss */
                        if(ryr<.12&&rxr>.28&&rxr<.72) g='@';
                        else if(ryr<.20&&rxr>.15&&rxr<.85) g='O';
                        else if(ryr<.62&&rxr>.08&&rxr<.92) g='M';
                        else if(ryr>=.62&&rxr<.28) g='/';
                        else if(ryr>=.62&&rxr>.72) g='\\';
                        else if(ryr>=.62) g='|';
                    } else {/* powerup */
                        g=(rxr>.3&&rxr<.7&&ryr>.3&&ryr<.7)?PW[sp->idx].kind:'*';
                    }
                    if(g){BF[y][x]=g;SH[y][x]=220;}
                }
            }
            ZBuf[col<W?col:W-1]=d;
        }

        /* blood particles */
        for(int i=0;i<BL_N;i++){
            double rx=BL[i].x-px,ry=BL[i].y-py,d=hypot(rx,ry);
            if(d<.15||d>20)continue;
            double a=atan2(ry,rx)-ang;
            while(a>M_PI)a-=P2; while(a<-M_PI)a+=P2;
            if(fabs(a)<FH){
                int col=(int)((a/FV+.5)*W);
                if(col>=0&&col<W&&d<ZBuf[col]){
                    int y=HH+(int)((1.-BL[i].life)*HH*.3);
                    if(y>=0&&y<H){BF[y][col]=BL[i].g;SH[y][col]=220;}
                }
            }
        }

        /* smoke */
        if(smk_t>0&&!dead){
            smk_t-=dt; if(smk_t<0)smk_t=0;
            const char *sg="~',.;:^~',."; int nsg=10;
            int layers=(int)(smk_t*1.8); if(layers<1)layers=1;
            for(int dr=1;dr<=layers+1;dr++){
                int row=HH-dr;
                if(row>=0&&row<H){
                    for(int dc=-2;dc<=2;dc++){
                        if(((double)rand()/RAND_MAX)<(smk_t/2.)*.72){
                            int col=HW+dc+(rand()%3)-1;
                            if(col>=0&&col<W){BF[row][col]=sg[rand()%nsg];SH[row][col]=220;}
                        }
                    }
                }
            }
        }

        /* muzzle flash */
        if(mu>0){
            const char *mf="*#@%"; int nmf=4;
            for(int dy=-2;dy<=0;dy++) for(int dx=-3;dx<=3;dx++){
                int y=H-3+dy,x=HW+dx;
                if(y>=0&&y<H&&x>=0&&x<W&&(dy==0||abs(dx)<2))
                    {BF[y][x]=mf[rand()%nmf];SH[y][x]=220;}
            }
            mu--;
        }

        /* crosshair */
        if(!dead){BF[HH][HW]='+';SH[HH][HW]=220;}

        flush_frame(dead,hp);

        /* ── HUD ──────────────────────────────────────────────────── */
        static const char *tnames[]={"SHAMBLER","WALKER","RUNNER","SPRINTER","FLANKER","HUNTER","BRUTE","BERSERKER","NIGHTMARE"};
        int tidx=(lv-1)/3; if(tidx>=9)tidx=8;
        const char *gun_tag=OH?"[OVERHEAT]":(heat>0?"[HOT]":"[CHAINGUN]");
        double sct_cd=t_now-lsc;
        char sct_buf[32];
        if(sct_cd<SCATTER_COOL) snprintf(sct_buf,sizeof(sct_buf),"SCATTER:%.1fs",SCATTER_COOL-sct_cd);
        else strcpy(sct_buf,"SCATTER:RDY");
        int alive_z=0; for(int i=0;i<ZCOUNT;i++)if(Z_ALIVE[i])alive_z++;
        printf("\x1b[0mHP:%3d SPD:%.1fx K:%d LV:%d[%s]%s Z:%d/%d SC:%d %s %s%s\n",
            hp, sm, kl, lv, tnames[tidx],
            boss_alive?"[BOSS]":"",
            alive_z, ZCOUNT, sc, gun_tag, sct_buf,
            (cb>=2)?"  COMBO":"");
        if(dead) printf("\x1b[31mYOU DIED — R:RESPAWN  N:NEW WORLD\x1b[0m\n");
        fflush(stdout);

        /* 30fps cap */
        double elapsed=now_s()-t_now;
        double slp=0.0333-elapsed;
        if(slp>0){struct timespec ts;ts.tv_sec=0;ts.tv_nsec=(long)(slp*1e9);nanosleep(&ts,NULL);}
    }
    return 0;
}
/* .- ∞ recurse · the maze has no exit */
/* CHAINGUN: 8/shot · 72/s cool · 8×2 resume — eightfold recursive balance */
