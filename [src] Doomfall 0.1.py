#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOOMFALL PI v0.1 — ASCII TERMINAL ENGINE
Pure Python · Raycast + ASCII renderer + SFX + Procedural vibe
"""

import sys, subprocess, math, time, random

# --- AUTO INSTALL ---
def install(pkg):
    try:
        __import__(pkg)
        return
    except:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "--user"])

for p in ["pygame", "numpy"]:
    install(p)

import pygame
import numpy as np

# --- CONFIG ---
W, H = 120, 40   # ASCII resolution
SCREEN_SCALE = 8
FOV = math.pi / 3

ASCII = " .:-=+*#%@"

# --- MAP ---
MAP = [
"##########",
"#........#",
"#........#",
"#....#...#",
"#........#",
"#........#",
"##########",
]

MW, MH = len(MAP[0]), len(MAP)

def is_wall(x,y):
    if x<0 or y<0 or x>=MW or y>=MH:
        return True
    return MAP[int(y)][int(x)] == '#'

# --- RAYCAST ---
def cast(px, py, angle):
    dx, dy = math.cos(angle), math.sin(angle)
    dist = 0
    while dist < 20:
        x = px + dx * dist
        y = py + dy * dist
        if is_wall(x,y):
            return dist
        dist += 0.02
    return 20

# --- AUDIO (simple synth) ---
def beep(freq=440, dur=0.1):
    sample_rate = 22050
    t = np.linspace(0, dur, int(sample_rate*dur))
    wave = (np.sin(2*np.pi*freq*t)*32767).astype(np.int16)
    sound = pygame.sndarray.make_sound(wave)
    sound.play()

# --- INIT ---
pygame.init()
screen = pygame.display.set_mode((W*SCREEN_SCALE, H*SCREEN_SCALE))
font = pygame.font.SysFont("Courier", SCREEN_SCALE)
clock = pygame.time.Clock()

px, py = 3.5, 3.5
angle = 0

# --- MAIN LOOP ---
running = True
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                running = False
            if e.key == pygame.K_e:
                beep(880,0.05)

    keys = pygame.key.get_pressed()

    if keys[pygame.K_a]: angle -= 0.05
    if keys[pygame.K_d]: angle += 0.05

    dx, dy = math.cos(angle)*0.1, math.sin(angle)*0.1
    if keys[pygame.K_w]:
        if not is_wall(px+dx, py+dy):
            px += dx; py += dy
    if keys[pygame.K_s]:
        if not is_wall(px-dx, py-dy):
            px -= dx; py -= dy

    # --- RENDER ASCII BUFFER ---
    screen.fill((0,0,0))

    for x in range(W):
        ray_angle = angle - FOV/2 + (x/W)*FOV
        dist = cast(px, py, ray_angle)

        wall_height = int(H / (dist+0.1))

        for y in range(H):
            if H//2 - wall_height//2 < y < H//2 + wall_height//2:
                shade = int((1 - dist/20)* (len(ASCII)-1))
                char = ASCII[max(0,shade)]
            else:
                char = ' '

            text = font.render(char, True, (200,200,200))
            screen.blit(text, (x*SCREEN_SCALE, y*SCREEN_SCALE))

    # --- HUD ---
    hud = font.render(f"X:{px:.2f} Y:{py:.2f}", True, (100,255,100))
    screen.blit(hud, (10,10))

    pygame.display.flip()
    clock.tick(30)

pygame.quit()
sys.exit()


