/* MAZFALL_ZOMBIE_ALPHA_v0.5  —  pure C · ANSI terminal · POSIX
 * Doomfall-0.1 ASCII ramp × Mazfall-α0.02 infinite chunked LCG world
 * WASD move · JL turn · SPACE fire · N new seed · R respawn · Q quit
 * build:  cc -O2 -lm Mazfall_Zombie_Alpha_v0.5.c -o mz05
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <sys/select.h>
#include <sys/ioctl.h>

#define W 100
#define H 34
#define CZ 21
#define CM 10
#define MD 40.0
#define CACHE 256
#define ZMAX 256
#define P2 6.28318530717958647692
#define FV 1.0471975511965976
#define FH 0.5235987755982988
static const char RM[] = " .:-=+*#%@";
#define RL 9

/* ── LCG — doom P_Random soul ─────────────────────────────────── */
typedef struct { unsigned int v; } lcg_t;
static unsigned int cseed(unsigned int w, int cx, int cy) {
    unsigned int v = w ^ ((unsigned)cx*1664525u+1013904223u) ^ ((unsigned)cy*22695477u+1u);
    return v * 2654435761u;
}
static unsigned int lrn(lcg_t *l) { l->v = l->v*1664525u + 1013904223u; return l->v; }

/* ── chunk gen — recursive backtracker maze ───────────────────── */
typedef unsigned char cell_t;
typedef struct { int cx, cy; cell_t m[CZ][CZ]; int hit; } chunk_t;
static chunk_t CH[CACHE];
static int CH_n = 0;
static int CH_tick = 0;

static void gen_chunk(unsigned int ws, int cx, int cy, chunk_t *dst) {
    lcg_t l; l.v = cseed(ws, cx, cy);
    dst->cx = cx; dst->cy = cy;
    for (int y = 0; y < CZ; y++) for (int x = 0; x < CZ; x++) dst->m[y][x] = 1;
    dst->m[0][CM] = dst->m[CZ-1][CM] = dst->m[CM][0] = dst->m[CM][CZ-1] = 0;
    /* iterative DFS carver — preserve doom carve_iter soul */
    int stack_x[CZ*CZ], stack_y[CZ*CZ], sp = 0;
    dst->m[1][1] = 0; stack_x[sp]=1; stack_y[sp]=1; sp++;
    int dd[4][2] = {{0,-2},{0,2},{-2,0},{2,0}};
    while (sp > 0) {
        int x = stack_x[sp-1], y = stack_y[sp-1];
        int order[4] = {0,1,2,3};
        for (int i = 3; i > 0; i--) { int j = lrn(&l) % (i+1); int t=order[i]; order[i]=order[j]; order[j]=t; }
        int moved = 0;
        for (int k = 0; k < 4; k++) {
            int dx = dd[order[k]][0], dy = dd[order[k]][1];
            int nx = x+dx, ny = y+dy;
            if (nx>=1 && nx<CZ-1 && ny>=1 && ny<CZ-1 && dst->m[ny][nx]) {
                dst->m[y+dy/2][x+dx/2] = 0; dst->m[ny][nx] = 0;
                stack_x[sp]=nx; stack_y[sp]=ny; sp++; moved = 1; break;
            }
        }
        if (!moved) sp--;
    }
}

static chunk_t *get_chunk(unsigned int ws, int cx, int cy) {
    for (int i = 0; i < CH_n; i++) if (CH[i].cx == cx && CH[i].cy == cy) { CH[i].hit = ++CH_tick; return &CH[i]; }
    int slot;
    if (CH_n < CACHE) slot = CH_n++;
    else { int lo = CH[0].hit, li = 0; for (int i=1;i<CH_n;i++) if (CH[i].hit<lo){lo=CH[i].hit;li=i;} slot = li; }
    gen_chunk(ws, cx, cy, &CH[slot]);
    CH[slot].hit = ++CH_tick;
    return &CH[slot];
}

static inline int imod(int a, int n) { int r = a % n; return r < 0 ? r + n : r; }
static inline int idiv(int a, int n) { int r = a / n; if ((a % n) < 0) r--; return r; }

static int cell(unsigned int ws, double wx, double wy) {
    int ix = (int)floor(wx), iy = (int)floor(wy);
    int cx = idiv(ix, CZ), cy = idiv(iy, CZ);
    int lx = imod(ix, CZ), ly = imod(iy, CZ);
    return get_chunk(ws, cx, cy)->m[ly][lx];
}

/* ── DDA raycast ──────────────────────────────────────────────── */
static double cast(unsigned int ws, double px, double py, double a) {
    double dx = cos(a), dy = sin(a), t = 0.04;
    while (t < MD) { if (cell(ws, px+dx*t, py+dy*t)) return t; t += 0.04; }
    return MD;
}

/* ── terminal I/O — raw mode ─────────────────────────────────── */
static struct termios orig_tio;
static void tio_restore(void) {
    tcsetattr(STDIN_FILENO, TCSANOW, &orig_tio);
    printf("\x1b[?25h\x1b[0m\x1b[2J\x1b[H"); fflush(stdout);
}
static void tio_raw(void) {
    tcgetattr(STDIN_FILENO, &orig_tio);
    struct termios t = orig_tio;
    t.c_lflag &= ~(ICANON | ECHO);
    t.c_cc[VMIN] = 0; t.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSANOW, &t);
    printf("\x1b[?25l\x1b[2J"); fflush(stdout);
    atexit(tio_restore);
}
static int kbhit_read(char *c) { return read(STDIN_FILENO, c, 1) == 1; }

/* ── zombie pool ──────────────────────────────────────────────── */
typedef struct { double x, y; int hp, alive; } zomb_t;
static zomb_t Z[ZMAX];
static int ZN = 0;

static void far_floor(unsigned int ws, double px, double py, double *ox, double *oy) {
    for (int r = 4; r < 30; r += 3) for (int k = 0; k < 24; k++) {
        double a = (rand()/(double)RAND_MAX)*P2;
        double d = r + (rand()/(double)RAND_MAX)*3.0;
        double wx = px + cos(a)*d, wy = py + sin(a)*d;
        if (!cell(ws, wx, wy)) { *ox = wx; *oy = wy; return; }
    }
    *ox = px+5; *oy = py+5;
}

static void spawn_zomb(unsigned int ws, double px, double py, int lv) {
    if (ZN >= ZMAX) return;
    far_floor(ws, px, py, &Z[ZN].x, &Z[ZN].y);
    Z[ZN].hp = 1 + lv/3; Z[ZN].alive = 1; ZN++;
}

/* ── render buffer ────────────────────────────────────────────── */
static char BUF[H][W+1];
static unsigned char SHD[H][W];
static double ZB[W];
static double CC_[W], CS_[W];

/* ── nano-sleep for ~20fps cap ───────────────────────────────── */
static double now_s(void) { struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts); return ts.tv_sec+ts.tv_nsec*1e-9; }

int main(void) {
    srand((unsigned)time(NULL));
    unsigned int ws = (unsigned int)(((unsigned long)rand()<<16) ^ rand() ^ time(NULL));
    double px = 1.5, py = 1.5, ang = 0.0;
    int hp = 100, sc = 0, kl = 0, lv = 1;
    double heat = 0.0; int OH = 0;
    const double MAXH=100, HPS=8, COOL=72, RES=16, RATE=0.035;
    const double MV=0.22, TR=0.11;
    double ls = 0, lh = 0;
    for (int x = 0; x < W; x++) { CC_[x]=cos(-FH+(double)x/W*FV); CS_[x]=sin(-FH+(double)x/W*FV); }
    for (int i = 0; i < 40; i++) spawn_zomb(ws, px, py, lv);
    tio_raw();
    double last = now_s();
    int run = 1;
    while (run) {
        double t = now_s(); double dt = t - last; last = t;
        /* input — drain kbd buffer */
        char c;
        while (kbhit_read(&c)) {
            if (c == 27 || c == 'q' || c == 'Q') run = 0;
            else if (c == 'w' || c == 'W') {
                double nx = px + cos(ang)*MV, ny = py + sin(ang)*MV;
                if (!cell(ws,nx,py)) px = nx;
                if (!cell(ws,px,ny)) py = ny;
            } else if (c == 's' || c == 'S') {
                double nx = px - cos(ang)*MV, ny = py - sin(ang)*MV;
                if (!cell(ws,nx,py)) px = nx;
                if (!cell(ws,px,ny)) py = ny;
            } else if (c == 'a' || c == 'A') {
                double nx = px - (-sin(ang))*MV, ny = py - cos(ang)*MV;
                if (!cell(ws,nx,py)) px = nx;
                if (!cell(ws,px,ny)) py = ny;
            } else if (c == 'd' || c == 'D') {
                double nx = px + (-sin(ang))*MV, ny = py + cos(ang)*MV;
                if (!cell(ws,nx,py)) px = nx;
                if (!cell(ws,px,ny)) py = ny;
            } else if (c == 'j' || c == 'J') ang -= TR;
            else if (c == 'l' || c == 'L') ang += TR;
            else if (c == ' ') {
                if (!OH && hp > 0 && t - ls > RATE) {
                    ls = t;
                    heat += HPS; if (heat >= MAXH) { heat = MAXH; OH = 1; }
                    /* find closest target in cone */
                    double wd = cast(ws, px, py, ang);
                    int best = -1; double bd = 1e9;
                    for (int i = 0; i < ZN; i++) {
                        if (!Z[i].alive) continue;
                        double ex = Z[i].x-px, ey = Z[i].y-py, d2 = ex*ex+ey*ey;
                        if (d2 > wd*wd) continue;
                        double d = sqrt(d2);
                        double a = atan2(ey,ex) - ang; while(a>M_PI)a-=P2; while(a<-M_PI)a+=P2;
                        if (fabs(a) < 0.10 + 0.40/(d+0.5) && d < bd) { best = i; bd = d; }
                    }
                    if (best >= 0) {
                        Z[best].hp--;
                        if (Z[best].hp <= 0) {
                            Z[best].alive = 0; sc += 10; kl++;
                            /* compact array */
                            for (int i = best; i < ZN-1; i++) Z[i] = Z[i+1];
                            ZN--;
                            spawn_zomb(ws, px, py, lv); spawn_zomb(ws, px, py, lv); /* ∞ 2-for-1 */
                        }
                    }
                }
            } else if (c == 'n' || c == 'N') {
                ws = (unsigned int)((rand()<<16) ^ rand() ^ time(NULL));
                CH_n = 0; px = 1.5; py = 1.5; ZN = 0;
                for (int i = 0; i < 40+lv*4; i++) spawn_zomb(ws, px, py, lv);
            } else if ((c == 'r' || c == 'R') && hp <= 0) {
                hp = 100; ZN = 0;
                for (int i = 0; i < 40+lv*4; i++) spawn_zomb(ws, px, py, lv);
            }
        }
        /* heat decay */
        if (heat > 0) { heat -= COOL*dt; if (heat < 0) heat = 0; }
        if (OH && heat < RES) OH = 0;
        /* zombie AI */
        double zsp = 0.035 + lv*0.006;
        if (hp > 0) {
            for (int i = 0; i < ZN; i++) {
                double ex = px-Z[i].x, ey = py-Z[i].y, d2 = ex*ex+ey*ey;
                if (d2 < 1e-4) continue;
                double d = sqrt(d2), vx = ex/d*zsp, vy = ey/d*zsp;
                if (!cell(ws, Z[i].x+vx, Z[i].y)) Z[i].x += vx;
                if (!cell(ws, Z[i].x, Z[i].y+vy)) Z[i].y += vy;
                if (d2 < 0.49 && t - lh > 0.8) { hp -= 2 + lv/2; lh = t; }
            }
            if (kl >= lv*20) { lv++; for (int k = 0; k < 3; k++) spawn_zomb(ws, px, py, lv); }
        }
        /* ── render ─────────────────────────────────────────── */
        for (int y = 0; y < H; y++) { for (int x = 0; x < W; x++) { BUF[y][x] = ' '; SHD[y][x] = 0; } BUF[y][W] = 0; }
        double ca = cos(ang), sa = sin(ang);
        for (int x = 0; x < W; x++) {
            double co = CC_[x], so = CS_[x];
            double ra = atan2(sa*co+ca*so, ca*co-sa*so);
            double d = cast(ws, px, py, ra) * co;
            ZB[x] = d;
            int wh = (int)(H/(d+0.1)), top = (H-wh)>>1;
            int si = (int)((1.0 - d/MD) * RL); if (si<0)si=0; if (si>RL)si=RL;
            char ch = RM[si];
            int v = (int)(220*(1.0 - d/MD)); if (v<60) v=60;
            for (int y = 0; y < H; y++) {
                if (y >= top && y < top+wh) { BUF[y][x] = ch; SHD[y][x] = (unsigned char)v; }
                else if (y > top+wh) {
                    double fr = ((double)y-H/2.0)/(H/2.0);
                    char fc = fr<0.1?' ':fr<0.45?'.':':';
                    if (fc != ' ') { BUF[y][x] = fc; SHD[y][x] = 95; }
                }
            }
        }
        /* sprites — painter sort by insertion */
        int idx[ZMAX]; double dsq[ZMAX]; int N = 0;
        for (int i = 0; i < ZN; i++) {
            double rx = Z[i].x-px, ry = Z[i].y-py;
            dsq[N] = rx*rx+ry*ry; idx[N] = i; N++;
        }
        /* insertion sort descending by distance */
        for (int i = 1; i < N; i++) {
            double k = dsq[i]; int ki = idx[i]; int j = i-1;
            while (j >= 0 && dsq[j] < k) { dsq[j+1]=dsq[j]; idx[j+1]=idx[j]; j--; }
            dsq[j+1] = k; idx[j+1] = ki;
        }
        for (int n = 0; n < N; n++) {
            int i = idx[n];
            double rx = Z[i].x-px, ry = Z[i].y-py, d = sqrt(rx*rx+ry*ry);
            if (d < 0.2) continue;
            double a = atan2(ry,rx) - ang; while(a>M_PI)a-=P2; while(a<-M_PI)a+=P2;
            if (fabs(a) > FH+0.15) continue;
            int col = (int)((a/FV+0.5)*W);
            int sh = (int)(H/(d+0.1)); int sw = (int)(sh*0.55); if (sw<1)sw=1;
            int top = (H-sh)>>1; if (top<0) top=0;
            int lft = col - (sw>>1);
            for (int xx = lft>0?lft:0; xx < lft+sw && xx < W; xx++) {
                if (d >= ZB[xx]) continue;
                double rxr = (double)(xx-lft)/(sw>0?sw:1);
                for (int yy = top; yy < top+sh && yy < H; yy++) {
                    double ryr = (double)(yy-top)/(sh>0?sh:1);
                    char g = 0;
                    if (ryr<0.2 && rxr>0.35 && rxr<0.65) g='o';
                    else if (ryr<0.72 && rxr>0.18 && rxr<0.82) g='z';
                    else if (ryr>=0.72 && rxr<0.4) g='/';
                    else if (ryr>=0.72 && rxr>0.6) g='\\';
                    else if (ryr>=0.72) g='|';
                    if (g) { BUF[yy][xx] = g; SHD[yy][xx] = 220; }
                }
            }
        }
        /* crosshair */
        if (hp > 0) { BUF[H/2][W/2] = '+'; SHD[H/2][W/2] = 220; }
        /* flush — ANSI 256 gray ramp, home cursor */
        printf("\x1b[H");
        for (int y = 0; y < H; y++) {
            int last_v = -1;
            for (int x = 0; x < W; x++) {
                int v = SHD[y][x];
                if (v != last_v) {
                    if (v == 0) printf("\x1b[0m");
                    else { int g = 232 + (v*23)/255; if (g<232)g=232; if(g>255)g=255; printf("\x1b[38;5;%dm", g); }
                    last_v = v;
                }
                putchar(BUF[y][x] ? BUF[y][x] : ' ');
            }
            printf("\x1b[0m\n"); last_v = 0;
        }
        /* HUD */
        int bw = 22; int hf = (int)(bw*heat/MAXH);
        printf("\x1b[0mHP:%3d  SC:%d  K:%d  LV:%d  Z:%d  [", hp, sc, kl, lv, ZN);
        for (int i = 0; i < bw; i++) putchar(i<hf?'#':'.');
        printf("] %s  heat=%02d%%%s\n",
            OH ? "OVERHEAT" : "CHAINGUN",
            (int)heat,
            hp<=0 ? "   *** ELIMINATED — R:respawn  N:new seed  Q:quit ***" : "");
        fflush(stdout);
        /* ~20fps */
        double sleep = 0.05 - (now_s() - t);
        if (sleep > 0) { struct timespec ts; ts.tv_sec=0; ts.tv_nsec=(long)(sleep*1e9); nanosleep(&ts, NULL); }
    }
    return 0;
}
/* .- ∞ recurse · the maze has no exit */
