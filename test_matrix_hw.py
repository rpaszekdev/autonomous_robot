from robot.hardware.matrix import max7219_matrix
import time
import random
import math

m = max7219_matrix()

# 1. Spiral fill
order = []
top, bottom, left, right = 0, 7, 0, 7
while top <= bottom and left <= right:
    for x in range(left, right + 1): order.append((top, x))
    top += 1
    for y in range(top, bottom + 1): order.append((y, right))
    right -= 1
    for x in range(right, left - 1, -1): order.append((bottom, x))
    bottom -= 1
    for y in range(bottom, top - 1, -1): order.append((y, left))
    left += 1

grid = [[0]*8 for _ in range(8)]
for y, x in order:
    grid[y][x] = 1
    m.draw_grid(grid)
    time.sleep(0.04)
time.sleep(0.5)

# Spiral unfill
for y, x in reversed(order):
    grid[y][x] = 0
    m.draw_grid(grid)
    time.sleep(0.04)
time.sleep(0.5)

# 2. Rain drops
for _ in range(40):
    grid = [[0]*8 for _ in range(8)]
    for col in range(8):
        if random.random() < 0.3:
            row = random.randint(0, 7)
            grid[row][col] = 1
    m.draw_grid(grid)
    time.sleep(0.08)
time.sleep(0.3)

# 3. Expanding diamond
for size in list(range(5)) + list(range(4, -1, -1)):
    grid = [[0]*8 for _ in range(8)]
    cx, cy = 3.5, 3.5
    for y in range(8):
        for x in range(8):
            if abs(x - cx) + abs(y - cy) <= size:
                grid[y][x] = 1
    m.draw_grid(grid)
    time.sleep(0.15)
time.sleep(0.3)

# 4. Sine wave
for frame in range(60):
    grid = [[0]*8 for _ in range(8)]
    for x in range(8):
        y = int(3.5 + 3 * math.sin((x + frame) * 0.8))
        y = max(0, min(7, y))
        grid[y][x] = 1
    m.draw_grid(grid)
    time.sleep(0.06)
time.sleep(0.3)

# 5. Game of Life (random start, 30 generations)
grid = [[random.randint(0, 1) for _ in range(8)] for _ in range(8)]
for _ in range(30):
    m.draw_grid(grid)
    time.sleep(0.15)
    new = [[0]*8 for _ in range(8)]
    for y in range(8):
        for x in range(8):
            n = sum(grid[(y+dy)%8][(x+dx)%8] for dy in [-1,0,1] for dx in [-1,0,1]) - grid[y][x]
            if grid[y][x] and n in (2, 3):
                new[y][x] = 1
            elif not grid[y][x] and n == 3:
                new[y][x] = 1
    grid = new
time.sleep(0.3)

# 6. Smiley face
smiley = [
    [0,0,1,1,1,1,0,0],
    [0,1,0,0,0,0,1,0],
    [1,0,1,0,0,1,0,1],
    [1,0,0,0,0,0,0,1],
    [1,0,1,0,0,1,0,1],
    [1,0,0,1,1,0,0,1],
    [0,1,0,0,0,0,1,0],
    [0,0,1,1,1,1,0,0],
]
m.draw_grid(smiley)
time.sleep(2)

m.clear()
m.close()
