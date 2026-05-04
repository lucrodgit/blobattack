import pygame
import math
import sys
import random

# ── Window ────────────────────────────────────────────
WIDTH, HEIGHT = 1280, 900
FPS = 60

# ── Map ───────────────────────────────────────────────
MAP_W, MAP_H = 3200, 2400
BORDER       = 40
GRID_SIZE    = 60

# ── Colors ────────────────────────────────────────────
BORDER_COL  = (0, 0, 0)
BG          = (15, 15, 25)
GRID_COL    = (28, 28, 45)
PLAYER_COL  = (50, 200, 255)
PLAYER_RIM  = (20, 120, 180)
BARREL_COL  = (80, 220, 255)
BARREL_RIM  = (20, 100, 160)
BULLET_COL  = (255, 230, 60)
BULLET_RIM  = (255, 140, 0)
RED_COL     = (220, 50,  50)
RED_RIM     = (140, 20,  20)
YELLOW_COL  = (255, 220, 30)
YELLOW_RIM  = (180, 140,  0)
TANK_COL    = (160, 40, 220)
TANK_RIM    = (80,   0, 130)
HP_BG       = (60, 10, 10)
HP_FG       = (220, 50, 50)
TANK_HP_FG  = (160, 40, 220)

# ── Player ────────────────────────────────────────────
PLAYER_SPEED  = 5
PLAYER_RADIUS = 16
BARREL_LEN    = 24
BARREL_W      = 6
PLAYER_MAX_HP = 100

# ── Bullet ────────────────────────────────────────────
BULLET_RADIUS = 4
BULLET_SPEED  = 12

# ── Waves ─────────────────────────────────────────────
WAVE_DURATION    = 30 * FPS   # 30 seconds per wave
SPAWN_MARGIN     = 80         # px outside camera to spawn


# ──────────────────────────────────────────────────────
#  WAVE CONFIG  (endless, scales every wave)
#  Each entry: (interval_frames, type, count_per_spawn)
#  interval = how many frames between each spawn event of that type
#  At wave W, interval shrinks and count grows
# ──────────────────────────────────────────────────────
def wave_config(wave):
    """Return spawn parameters scaled to the current wave number."""
    # Base intervals (frames between spawns)
    red_interval    = max(90,  240 - wave * 12)   # starts at 240, floor 90
    yellow_interval = max(120, 300 - wave * 15)   # starts at 300, floor 120
    tank_interval   = max(300, 600 - wave * 25)   # starts at 600, floor 300

    # Enemies per spawn event
    red_count    = 1 + wave // 3          # +1 red every 3 waves
    yellow_count = 5 + wave // 2          # yellow packs grow faster
    tank_count   = 1 + wave // 6          # tanks come in pairs eventually

    return {
        'red':    {'interval': red_interval,    'count': red_count},
        'yellow': {'interval': yellow_interval, 'count': yellow_count},
        'tank':   {'interval': tank_interval,   'count': tank_count},
    }


# ──────────────────────────────────────────────────────
#  CAMERA
# ──────────────────────────────────────────────────────
class Camera:
    def __init__(self):
        self.x = self.y = 0

    def update(self, tx, ty):
        self.x = max(0, min(tx - WIDTH  // 2, MAP_W - WIDTH))
        self.y = max(0, min(ty - HEIGHT // 2, MAP_H - HEIGHT))

    def to_screen(self, wx, wy):
        return wx - self.x, wy - self.y

    def to_world(self, sx, sy):
        return sx + self.x, sy + self.y


# ──────────────────────────────────────────────────────
#  BULLET
# ──────────────────────────────────────────────────────
class Bullet:
    def __init__(self, wx, wy, angle):
        self.x  = wx
        self.y  = wy
        self.vx = math.cos(angle) * BULLET_SPEED
        self.vy = math.sin(angle) * BULLET_SPEED
        self.active = True

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if not (BORDER < self.x < MAP_W - BORDER and BORDER < self.y < MAP_H - BORDER):
            self.active = False

    def draw(self, screen, cam):
        sx, sy = cam.to_screen(self.x, self.y)
        pygame.draw.circle(screen, BULLET_RIM, (int(sx), int(sy)), BULLET_RADIUS + 3)
        pygame.draw.circle(screen, BULLET_COL, (int(sx), int(sy)), BULLET_RADIUS)


# ──────────────────────────────────────────────────────
#  ENEMY BASE
# ──────────────────────────────────────────────────────
class Enemy:
    def __init__(self, x, y, radius, hp, speed, damage, color, rim):
        self.x      = x
        self.y      = y
        self.radius = radius
        self.hp     = hp
        self.max_hp = hp
        self.speed  = speed
        self.damage = damage
        self.color  = color
        self.rim    = rim
        self.dead   = False
        self.flash  = 0

    def move_toward(self, tx, ty, enemies):
        dx = tx - self.x
        dy = ty - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            nx = (dx / dist) * self.speed
            ny = (dy / dist) * self.speed
        else:
            nx = ny = 0

        self.x += nx
        self.y += ny

        # ── Solid circle collision vs other enemies ──
        for other in enemies:
            if other is self:
                continue
            gap = math.hypot(self.x - other.x, self.y - other.y)
            min_dist = self.radius + other.radius
            if gap < min_dist and gap > 0:
                # Push self away from other
                push = (min_dist - gap) / gap
                self.x += (self.x - other.x) * push * 0.5
                self.y += (self.y - other.y) * push * 0.5

        r = self.radius
        self.x = max(BORDER + r, min(MAP_W - BORDER - r, self.x))
        self.y = max(BORDER + r, min(MAP_H - BORDER - r, self.y))

    def hit(self, damage=1):
        self.hp -= damage
        self.flash = 6
        if self.hp <= 0:
            self.dead = True

    def collides_with_player(self, px, py, pr):
        return math.hypot(self.x - px, self.y - py) < self.radius + pr

    def push_from_player(self, px, py, pr):
        """Solid collision: push enemy out of player circle."""
        dist = math.hypot(self.x - px, self.y - py)
        min_d = self.radius + pr
        if 0 < dist < min_d:
            push = (min_d - dist) / dist
            self.x += (self.x - px) * push
            self.y += (self.y - py) * push

    def draw(self, screen, cam):
        sx, sy = cam.to_screen(self.x, self.y)
        if not (-self.radius < sx < WIDTH + self.radius and
                -self.radius < sy < HEIGHT + self.radius):
            return
        col = (255, 255, 255) if self.flash > 0 else self.color
        self.flash = max(0, self.flash - 1)
        pygame.draw.circle(screen, self.rim, (int(sx), int(sy)), self.radius + 2)
        pygame.draw.circle(screen, col,      (int(sx), int(sy)), self.radius)
        self._draw_hp_bar(screen, sx, sy)

    def _draw_hp_bar(self, screen, sx, sy):
        if self.hp == self.max_hp:
            return
        bar_w = self.radius * 2
        bar_h = 5
        bx    = sx - self.radius
        by    = sy - self.radius - 10
        ratio = max(0, self.hp / self.max_hp)
        pygame.draw.rect(screen, HP_BG,           (int(bx), int(by), bar_w, bar_h))
        pygame.draw.rect(screen, self._hp_col(),  (int(bx), int(by), int(bar_w * ratio), bar_h))

    def _hp_col(self):
        return HP_FG


class RedEnemy(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y, radius=14, hp=3,  speed=1.8, damage=10,
                         color=RED_COL, rim=RED_RIM)

class YellowEnemy(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y, radius=8,  hp=1,  speed=3.2, damage=3,
                         color=YELLOW_COL, rim=YELLOW_RIM)

class TankEnemy(Enemy):
    def __init__(self, x, y):
        super().__init__(x, y, radius=28, hp=50, speed=0.9, damage=25,
                         color=TANK_COL, rim=TANK_RIM)
    def _hp_col(self):
        return TANK_HP_FG


# ──────────────────────────────────────────────────────
#  PLAYER
# ──────────────────────────────────────────────────────
class Player:
    def __init__(self):
        self.x   = MAP_W // 2
        self.y   = MAP_H // 2
        self.hp  = PLAYER_MAX_HP
        self.inv = 0

    def handle_input(self, keys):
        dx = dy = 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:    dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx += 1
        if dx and dy:
            dx *= 0.7071; dy *= 0.7071
        self.x += dx * PLAYER_SPEED
        self.y += dy * PLAYER_SPEED
        r = PLAYER_RADIUS
        self.x = max(BORDER + r, min(MAP_W - BORDER - r, self.x))
        self.y = max(BORDER + r, min(MAP_H - BORDER - r, self.y))

    def take_damage(self, amount):
        if self.inv > 0:
            return
        self.hp -= amount
        self.inv = 40

    def update(self):
        self.inv = max(0, self.inv - 1)

    def angle_to_mouse(self, cam):
        mx, my = pygame.mouse.get_pos()
        wx, wy = cam.to_world(mx, my)
        return math.atan2(wy - self.y, wx - self.x)

    def shoot(self, cam):
        angle = self.angle_to_mouse(cam)
        tip_x = self.x + math.cos(angle) * (PLAYER_RADIUS + BARREL_LEN)
        tip_y = self.y + math.sin(angle) * (PLAYER_RADIUS + BARREL_LEN)
        return Bullet(tip_x, tip_y, angle)

    def draw(self, screen, cam):
        if self.inv > 0 and (self.inv // 5) % 2 == 1:
            return
        sx, sy = cam.to_screen(self.x, self.y)
        angle  = self.angle_to_mouse(cam)

        barrel_surf = pygame.Surface((BARREL_LEN, BARREL_W * 2), pygame.SRCALPHA)
        pygame.draw.rect(barrel_surf, BARREL_RIM, (0, 0, BARREL_LEN, BARREL_W * 2), border_radius=3)
        pygame.draw.rect(barrel_surf, BARREL_COL, (2, 2, BARREL_LEN - 2, BARREL_W * 2 - 4), border_radius=3)
        rotated  = pygame.transform.rotate(barrel_surf, -math.degrees(angle))
        offset_x = math.cos(angle) * BARREL_LEN / 2
        offset_y = math.sin(angle) * BARREL_LEN / 2
        screen.blit(rotated, (sx + offset_x - rotated.get_width()  / 2,
                               sy + offset_y - rotated.get_height() / 2))

        pygame.draw.circle(screen, PLAYER_RIM, (int(sx), int(sy)), PLAYER_RADIUS + 3)
        pygame.draw.circle(screen, PLAYER_COL, (int(sx), int(sy)), PLAYER_RADIUS)
        pygame.draw.circle(screen, PLAYER_RIM, (int(sx), int(sy)), 5)

    def draw_hud(self, screen, wave, wave_timer):
        font_sm = pygame.font.SysFont("consolas", 13, bold=True)
        font_lg = pygame.font.SysFont("consolas", 20, bold=True)

        # HP bar
        bar_w, bar_h = 200, 16
        bx, by = 16, 16
        ratio  = max(0, self.hp / PLAYER_MAX_HP)
        color  = ((50,220,80) if ratio > 0.6 else (220,180,30) if ratio > 0.3 else (220,50,50))
        pygame.draw.rect(screen, (40,40,40),     (bx, by, bar_w, bar_h), border_radius=4)
        pygame.draw.rect(screen, color,          (bx, by, int(bar_w * ratio), bar_h), border_radius=4)
        pygame.draw.rect(screen, (180,180,180),  (bx, by, bar_w, bar_h), 2, border_radius=4)
        screen.blit(font_sm.render(f"HP  {max(0,self.hp)} / {PLAYER_MAX_HP}", True, (220,220,220)), (bx+4, by+1))

        # Wave info top-center
        secs_left = max(0, wave_timer // FPS)
        wave_txt  = font_lg.render(f"WAVE  {wave}", True, (255, 200, 50))
        timer_txt = font_sm.render(f"next wave in  {secs_left}s", True, (160, 160, 160))
        screen.blit(wave_txt,  (WIDTH // 2 - wave_txt.get_width()  // 2, 12))
        screen.blit(timer_txt, (WIDTH // 2 - timer_txt.get_width() // 2, 38))


# ──────────────────────────────────────────────────────
#  SPAWN HELPERS
# ──────────────────────────────────────────────────────
def edge_pos(cam):
    side = random.choice(('top', 'bottom', 'left', 'right'))
    m = SPAWN_MARGIN
    if side == 'top':
        x, y = random.uniform(cam.x, cam.x + WIDTH), cam.y - m
    elif side == 'bottom':
        x, y = random.uniform(cam.x, cam.x + WIDTH), cam.y + HEIGHT + m
    elif side == 'left':
        x, y = cam.x - m, random.uniform(cam.y, cam.y + HEIGHT)
    else:
        x, y = cam.x + WIDTH + m, random.uniform(cam.y, cam.y + HEIGHT)
    x = max(BORDER + 30, min(MAP_W - BORDER - 30, x))
    y = max(BORDER + 30, min(MAP_H - BORDER - 30, y))
    return x, y


def spawn_group(kind, count, cam):
    x, y = edge_pos(cam)
    group = []
    for i in range(count):
        ox = x + random.uniform(-50, 50)
        oy = y + random.uniform(-50, 50)
        if kind == 'red':
            group.append(RedEnemy(ox, oy))
        elif kind == 'yellow':
            group.append(YellowEnemy(ox, oy))
        elif kind == 'tank':
            group.append(TankEnemy(ox, oy))
    return group


# ──────────────────────────────────────────────────────
#  WORLD DRAW
# ──────────────────────────────────────────────────────
def draw_world(screen, cam):
    screen.fill(BG)
    wx0, wy0 = cam.x, cam.y
    wx1, wy1 = cam.x + WIDTH, cam.y + HEIGHT

    gx = (int(wx0) // GRID_SIZE) * GRID_SIZE
    while gx <= wx1:
        sx, _ = cam.to_screen(gx, 0)
        pygame.draw.line(screen, GRID_COL, (int(sx), 0), (int(sx), HEIGHT))
        gx += GRID_SIZE
    gy = (int(wy0) // GRID_SIZE) * GRID_SIZE
    while gy <= wy1:
        _, sy = cam.to_screen(0, gy)
        pygame.draw.line(screen, GRID_COL, (0, int(sy)), (WIDTH, int(sy)))
        gy += GRID_SIZE

    bx0, by0 = cam.to_screen(0, 0)
    bx1, by1 = cam.to_screen(MAP_W, MAP_H)
    for rect in [
        pygame.Rect(bx0, by0, BORDER, by1 - by0),
        pygame.Rect(bx1 - BORDER, by0, BORDER, by1 - by0),
        pygame.Rect(bx0, by0, bx1 - bx0, BORDER),
        pygame.Rect(bx0, by1 - BORDER, bx1 - bx0, BORDER),
    ]:
        pygame.draw.rect(screen, BORDER_COL, rect)

    hi = (40, 40, 70)
    pygame.draw.line(screen, hi, cam.to_screen(BORDER, BORDER),         cam.to_screen(MAP_W-BORDER, BORDER))
    pygame.draw.line(screen, hi, cam.to_screen(BORDER, MAP_H-BORDER),   cam.to_screen(MAP_W-BORDER, MAP_H-BORDER))
    pygame.draw.line(screen, hi, cam.to_screen(BORDER, BORDER),         cam.to_screen(BORDER, MAP_H-BORDER))
    pygame.draw.line(screen, hi, cam.to_screen(MAP_W-BORDER, BORDER),   cam.to_screen(MAP_W-BORDER, MAP_H-BORDER))


# ──────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Circle Shooter")
    clock  = pygame.time.Clock()

    player  = Player()
    camera  = Camera()
    bullets = []
    enemies = []

    # Wave state
    wave       = 1
    wave_timer = WAVE_DURATION          # counts down each frame
    cfg        = wave_config(wave)

    # Per-type spawn timers (independent countdowns)
    spawn_timers = {
        'red':    cfg['red']['interval'] // 2,   # first spawns come quickly
        'yellow': cfg['yellow']['interval'] // 2,
        'tank':   cfg['tank']['interval'],
    }

    game_over = False
    font_big  = pygame.font.SysFont("consolas", 64, bold=True)
    font_med  = pygame.font.SysFont("consolas", 28, bold=True)

    while True:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_r and game_over:
                    main(); return   # restart
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not game_over:
                bullets.append(player.shoot(camera))

        if not game_over:
            # ── Player ────────────────────────────
            keys = pygame.key.get_pressed()
            player.handle_input(keys)
            player.update()
            camera.update(player.x, player.y)

            # ── Wave timer ────────────────────────
            wave_timer -= 1
            if wave_timer <= 0:
                wave      += 1
                wave_timer = WAVE_DURATION
                cfg        = wave_config(wave)
                # Reset spawn timers for new wave (don't rush them)
                spawn_timers = {
                    'red':    cfg['red']['interval'],
                    'yellow': cfg['yellow']['interval'],
                    'tank':   cfg['tank']['interval'],
                }

            # ── Spawn per type ────────────────────
            for kind in ('red', 'yellow', 'tank'):
                spawn_timers[kind] -= 1
                if spawn_timers[kind] <= 0:
                    enemies.extend(spawn_group(kind, cfg[kind]['count'], camera))
                    spawn_timers[kind] = cfg[kind]['interval']

            # ── Bullets ───────────────────────────
            for b in bullets:
                b.update()
            bullets = [b for b in bullets if b.active]

            # ── Enemies ───────────────────────────
            for e in enemies:
                e.move_toward(player.x, player.y, enemies)

                # Bullet collision
                for b in bullets:
                    if b.active and math.hypot(b.x - e.x, b.y - e.y) < BULLET_RADIUS + e.radius:
                        e.hit(1)
                        b.active = False

                # Player solid collision — push enemy out, then deal damage
                e.push_from_player(player.x, player.y, PLAYER_RADIUS)
                if e.collides_with_player(player.x, player.y, PLAYER_RADIUS):
                    player.take_damage(e.damage)

            enemies = [e for e in enemies if not e.dead]

            if player.hp <= 0:
                game_over = True

        # ── Draw ──────────────────────────────────
        draw_world(screen, camera)
        for e in enemies:
            e.draw(screen, camera)
        for b in bullets:
            b.draw(screen, camera)
        player.draw(screen, camera)
        player.draw_hud(screen, wave, wave_timer)

        if game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            screen.blit(overlay, (0, 0))
            t1 = font_big.render("GAME OVER", True, (220, 50, 50))
            t2 = font_med.render(f"Survived to Wave {wave}   |   Press R to restart", True, (200, 200, 200))
            screen.blit(t1, (WIDTH//2 - t1.get_width()//2, HEIGHT//2 - 60))
            screen.blit(t2, (WIDTH//2 - t2.get_width()//2, HEIGHT//2 + 20))

        pygame.display.flip()


if __name__ == "__main__":
    main()