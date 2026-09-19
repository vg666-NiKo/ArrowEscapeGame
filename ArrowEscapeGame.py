import os
import json
import math
import random
from pathlib import Path

import pygame


# ============================================================
# 基本配置
# ============================================================

WIDTH, HEIGHT = 960, 760
FPS = 60
MAX_LIVES = 3

DIRECTIONS = {
    "U": (-1, 0),
    "D": (1, 0),
    "L": (0, -1),
    "R": (0, 1),
}

LEVELS = [
    (4, 11),
    (5, 29),
    (6, 47),
    (7, 83),
    (8, 131),
]

BG = (237, 244, 249)
WHITE = (255, 255, 255)
TEXT = (42, 62, 81)
MUTED = (106, 124, 140)
BLUE = (66, 145, 228)
BLUE_HOVER = (49, 126, 208)
CELL = (226, 236, 248)
CELL_HOVER = (207, 225, 246)
EMPTY_CELL = (240, 245, 250)
GREEN = (44, 166, 117)
RED = (222, 81, 91)
GOLD = (238, 174, 45)

ARROW_COLORS = {
    "U": (62, 136, 201),
    "D": (71, 153, 147),
    "L": (126, 114, 191),
    "R": (62, 136, 201),
}


# ============================================================
# 棋盘逻辑：与图形界面分离，方便解释和测试
# ============================================================

def copy_board(board):
    return [row[:] for row in board]


def remaining_count(board):
    return sum(
        value is not None
        for row in board
        for value in row
    )


def path_is_clear(board, row, col, direction):
    """从相邻格开始，检查箭头前方直到棋盘边界。"""
    dr, dc = DIRECTIONS[direction]
    row += dr
    col += dc
    n = len(board)

    while 0 <= row < n and 0 <= col < n:
        if board[row][col] is not None:
            return False
        row += dr
        col += dc

    return True


def available_moves(board):
    """返回当前可以直接离开的箭头坐标。"""
    n = len(board)
    return [
        (r, c)
        for r in range(n)
        for c in range(n)
        if board[r][c] is not None
        and path_is_clear(board, r, c, board[r][c])
    ]


def solve_board(board):
    """规则求解器，不调用联网AI或大模型。"""
    work = copy_board(board)
    solution = []

    while remaining_count(work):
        moves = available_moves(work)
        if not moves:
            return None

        for r, c in moves:
            work[r][c] = None
            solution.append((r, c))

    return solution


def generate_board(n, seed):
    """
    逆向构造：
    每次只放置一个能够越过已有箭头离开的新箭头。
    因此逆序移除这些箭头，一定可以清空棋盘。
    """
    rng = random.Random(seed)
    board = [[None for _ in range(n)] for _ in range(n)]

    positions = [
        (r, c)
        for r in range(n)
        for c in range(n)
    ]
    rng.shuffle(positions)

    for r, c in positions:
        choices = [
            direction
            for direction in DIRECTIONS
            if path_is_clear(board, r, c, direction)
        ]

        if choices:
            board[r][c] = rng.choice(choices)

    return board


def valid_board(board):
    if not isinstance(board, list) or not 4 <= len(board) <= 8:
        return False

    n = len(board)

    return all(
        isinstance(row, list)
        and len(row) == n
        and all(
            value is None
            or (
                isinstance(value, str)
                and value in DIRECTIONS
            )
            for value in row
        )
        for row in board
    )


# ============================================================
# 窗口、字体和存档位置
# ============================================================

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Arrow Escape")
clock = pygame.time.Clock()

# 直接按文件路径读取字体，避免此前SysFont的异常。
FONT_PATH = None
font_candidates = [
    Path(os.environ.get("WINDIR", "C:/Windows"))
    / "Fonts" / "msyh.ttc",
    Path(os.environ.get("WINDIR", "C:/Windows"))
    / "Fonts" / "simhei.ttf",
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
]

for candidate in font_candidates:
    if candidate.is_file():
        try:
            pygame.font.Font(str(candidate), 20)
            FONT_PATH = str(candidate)
            break
        except (OSError, pygame.error):
            pass

USE_CHINESE = FONT_PATH is not None
FONT_CACHE = {}


def tr(chinese, english):
    return chinese if USE_CHINESE else english


def get_font(size):
    if size not in FONT_CACHE:
        FONT_CACHE[size] = pygame.font.Font(FONT_PATH, size)
    return FONT_CACHE[size]


def draw_text(text, x, y, size=22, color=TEXT, center=False):
    image = get_font(size).render(str(text), True, color)
    rect = image.get_rect()

    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)

    screen.blit(image, rect)


def format_time(seconds):
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# 不向项目源码目录写入个人进度，方便上传GitHub。
SAVE_DIR = (
    Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    / "ArrowEscapeGame"
)
SAVE_PATH = SAVE_DIR / "progress.json"


# ============================================================
# 游戏
# ============================================================

class Game:
    def __init__(self):
        self.running = True
        self.state = "menu"
        self.buttons = []

        self.initial = []
        self.board = []
        self.level_index = 0
        self.random_mode = False

        self.lives = MAX_LIVES
        self.score = 0
        self.elapsed = 0.0
        self.assisted = False

        self.history = []
        self.flight = None
        self.bump = None
        self.hint_cell = None
        self.hint_time = 0.0
        self.auto = False
        self.auto_wait = 0.0

        self.status = ""
        self.status_time = 0.0
        self.save_error = ""
        self.save_timer = 0.0

        self.saved_session = None
        self.records = {}
        self.load_save()

    # -------------------- 存档 --------------------

    def load_save(self):
        if not SAVE_PATH.exists():
            return

        try:
            with SAVE_PATH.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("Unsupported save")

            records = data.get("records", {})
            if isinstance(records, dict):
                self.records = {
                    str(key): value
                    for key, value in records.items()
                    if type(value) is int and 1 <= value <= 3
                }

            session = data.get("session")
            if session is None:
                return

            if not isinstance(session, dict):
                raise ValueError("Invalid session")

            initial = session.get("initial")
            board = session.get("board")

            if not valid_board(initial) or not valid_board(board):
                raise ValueError("Invalid board")

            if len(initial) != len(board):
                raise ValueError("Board size mismatch")

            n = len(board)
            for r in range(n):
                for c in range(n):
                    if board[r][c] is not None:
                        if board[r][c] != initial[r][c]:
                            raise ValueError("Changed direction")

            index = session.get("level_index")
            lives = session.get("lives")
            score = session.get("score")
            elapsed = session.get("elapsed")

            if type(index) is not int or not 0 <= index < len(LEVELS):
                raise ValueError("Invalid level")

            if type(lives) is not int or not 1 <= lives <= MAX_LIVES:
                raise ValueError("Invalid lives")

            if type(score) is not int or not 0 <= score <= 100000:
                raise ValueError("Invalid score")

            if type(elapsed) not in (int, float):
                raise ValueError("Invalid time")

            if not math.isfinite(elapsed) or not 0 <= elapsed <= 10000000:
                raise ValueError("Invalid time")

            if type(session.get("random_mode")) is not bool:
                raise ValueError("Invalid mode")

            if type(session.get("assisted")) is not bool:
                raise ValueError("Invalid assist flag")

            if remaining_count(board) == 0:
                return

            if solve_board(initial) is None or solve_board(board) is None:
                raise ValueError("Unsolvable board")

            self.saved_session = session

        except (OSError, ValueError, TypeError, KeyError):
            self.saved_session = None
            self.save_error = tr(
                "旧存档无法读取，可以正常开始新游戏。",
                "Old save unavailable. You can start a new game."
            )

    def save_progress(self):
        session = self.saved_session

        if self.state == "playing":
            if self.lives > 0 and remaining_count(self.board) > 0:
                session = {
                    "initial": copy_board(self.initial),
                    "board": copy_board(self.board),
                    "level_index": self.level_index,
                    "random_mode": self.random_mode,
                    "lives": self.lives,
                    "score": self.score,
                    "elapsed": self.elapsed,
                    "assisted": self.assisted,
                }
            else:
                session = None

        elif self.state in ("won", "lost"):
            session = None

        self.saved_session = session

        try:
            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            temporary = SAVE_PATH.with_suffix(".tmp")

            with temporary.open("w", encoding="utf-8") as file:
                json.dump(
                    {
                        "version": 1,
                        "session": session,
                        "records": self.records,
                    },
                    file,
                    ensure_ascii=False,
                    indent=2
                )

            os.replace(temporary, SAVE_PATH)
            self.save_error = ""

        except OSError:
            self.save_error = tr(
                "存档写入失败，本次游戏仍可继续。",
                "Cannot save progress; the game can still continue."
            )

    # -------------------- 开始、恢复、重开 --------------------

    def notify(self, message):
        self.status = message
        self.status_time = 2.5

    def clear_transient(self):
        self.history = []
        self.flight = None
        self.bump = None
        self.hint_cell = None
        self.hint_time = 0.0
        self.auto = False
        self.auto_wait = 0.0
        self.status = ""
        self.status_time = 0.0
        self.save_timer = 0.0

    def start_level(self, index=0, random_mode=False):
        self.level_index = index
        self.random_mode = random_mode

        if random_mode:
            n = 6
            # 确保随机棋盘包含四种方向。
            while True:
                seed = random.randrange(1, 1000000000)
                board = generate_board(n, seed)
                kinds = {
                    value
                    for row in board
                    for value in row
                    if value is not None
                }
                if len(kinds) == 4:
                    break
        else:
            n, seed = LEVELS[index]
            board = generate_board(n, seed)

        self.initial = copy_board(board)
        self.restart()

    def restart(self):
        self.board = copy_board(self.initial)
        self.lives = MAX_LIVES
        self.score = 0
        self.elapsed = 0.0
        self.assisted = False
        self.clear_transient()
        self.state = "playing"
        self.save_progress()

    def resume(self):
        if self.saved_session is None:
            return

        session = self.saved_session
        self.initial = copy_board(session["initial"])
        self.board = copy_board(session["board"])
        self.level_index = session["level_index"]
        self.random_mode = session["random_mode"]
        self.lives = session["lives"]
        self.score = session["score"]
        self.elapsed = float(session["elapsed"])
        self.assisted = session["assisted"]

        self.clear_transient()
        self.state = "playing"
        self.notify(tr(
            "已恢复进度；撤销历史不跨程序保存。",
            "Progress restored; undo history starts here."
        ))

    def back_to_menu(self):
        self.save_progress()
        self.auto = False
        self.state = "menu"

    # -------------------- 操作和动画 --------------------

    def layout(self):
        n = len(self.board)
        step = min(72, 480 // n)
        side = step * n
        left = (WIDTH - side) // 2
        top = 165 + (480 - side) // 2
        return left, top, step, side

    def cell_center(self, row, col):
        left, top, step, _ = self.layout()
        return (
            left + (col + 0.5) * step,
            top + (row + 0.5) * step
        )

    def busy(self):
        return self.flight is not None or self.bump is not None

    def remember(self):
        self.history.append((
            copy_board(self.board),
            self.lives,
            self.score
        ))

    def click_arrow(self, row, col):
        if self.state != "playing" or self.busy():
            return

        direction = self.board[row][col]
        if direction is None:
            return

        self.remember()
        self.hint_cell = None

        if path_is_clear(self.board, row, col, direction):
            x, y = self.cell_center(row, col)

            self.flight = {
                "x": x,
                "y": y,
                "direction": direction,
            }

            # 动画期间锁住棋盘点击，因此可以先释放逻辑格子。
            self.board[row][col] = None
            self.score += 100
            self.notify(tr("道路畅通！", "Clear path!"))

        else:
            self.lives -= 1
            self.score = max(0, self.score - 30)
            self.bump = {"row": row, "col": col, "time": 0.0}
            self.notify(tr(
                "前方有箭头阻挡，剩余失误次数减1。",
                "Blocked! One chance lost."
            ))

        self.save_progress()

    def undo(self):
        if self.state != "playing" or self.busy() or self.auto:
            return

        if not self.history:
            self.notify(tr("目前没有可撤销的操作。", "Nothing to undo."))
            return

        board, lives, score = self.history.pop()
        self.board = copy_board(board)
        self.lives = lives
        self.score = score
        self.hint_cell = None

        # 计时不回退；辅助标记也不通过撤销清除。
        self.assisted = True
        self.notify(tr("已撤销上一步。", "Last move undone."))
        self.save_progress()

    def hint(self):
        if self.state != "playing" or self.busy() or self.auto:
            return

        moves = available_moves(self.board)

        if moves:
            self.hint_cell = moves[0]
            self.hint_time = 2.5
            self.assisted = True
            self.notify(tr(
                "金色边框中的箭头可以离开。",
                "The gold-highlighted arrow can leave."
            ))
            self.save_progress()

    def toggle_auto(self):
        if self.state != "playing":
            return

        self.auto = not self.auto
        if self.auto:
            self.assisted = True
            self.auto_wait = 0.25

        self.notify(
            tr("自动求解已开启。", "Auto solve enabled.")
            if self.auto
            else tr("自动求解已停止。", "Auto solve stopped.")
        )
        self.save_progress()

    def star_count(self):
        stars = max(1, self.lives)
        if self.assisted:
            stars = min(stars, 2)
        return stars

    def finish(self, won):
        self.auto = False
        self.state = "won" if won else "lost"

        if won and not self.random_mode:
            key = str(self.level_index)
            self.records[key] = max(
                self.records.get(key, 0),
                self.star_count()
            )

        self.save_progress()

    def update(self, dt):
        self.status_time = max(0.0, self.status_time - dt)
        self.hint_time = max(0.0, self.hint_time - dt)

        if self.hint_time == 0:
            self.hint_cell = None

        if self.state != "playing":
            return

        self.elapsed += dt

        if self.flight is not None:
            dr, dc = DIRECTIONS[self.flight["direction"]]
            self.flight["x"] += dc * 850 * dt
            self.flight["y"] += dr * 850 * dt

            left, top, _, side = self.layout()
            x = self.flight["x"]
            y = self.flight["y"]

            # 留出箭头图形半径，确保整支箭头都已离开。
            if (
                x < left - 45 or x > left + side + 45
                or y < top - 45 or y > top + side + 45
            ):
                self.flight = None

        if self.bump is not None:
            self.bump["time"] += dt
            if self.bump["time"] >= 0.4:
                self.bump = None

        if not self.busy():
            if self.lives <= 0:
                self.finish(False)
                return

            if remaining_count(self.board) == 0:
                self.finish(True)
                return

            if self.auto:
                self.auto_wait -= dt
                if self.auto_wait <= 0:
                    moves = available_moves(self.board)
                    if moves:
                        self.click_arrow(*moves[0])
                        self.auto_wait = 0.25
                    else:
                        self.auto = False
                        self.notify(tr(
                            "没有可用操作，请重新开始。",
                            "No available move. Please restart."
                        ))

        self.save_timer += dt
        if self.save_timer >= 2.0:
            self.save_timer = 0.0
            self.save_progress()

    # -------------------- 界面绘制 --------------------

    def button(self, rect, label, action, enabled=True):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(pygame.mouse.get_pos())

        color = (
            BLUE_HOVER if hover else BLUE
        ) if enabled else (185, 198, 211)

        pygame.draw.rect(screen, color, rect, border_radius=10)
        draw_text(label, *rect.center, size=20, color=WHITE, center=True)
        self.buttons.append((rect, action, enabled))

    def draw_arrow(self, x, y, direction, size, color):
        dr, dc = DIRECTIONS[direction]
        forward = pygame.Vector2(dc, dr)
        sideways = pygame.Vector2(-dr, dc)
        center = pygame.Vector2(x, y)

        # 基础箭头：纵坐标沿箭头前进方向，横坐标沿垂直方向。
        shape = [
            (-0.38, -0.10),
            (0.06, -0.10),
            (0.06, -0.27),
            (0.42, 0.00),
            (0.06, 0.27),
            (0.06, 0.10),
            (-0.38, 0.10),
        ]

        points = []
        for along, across in shape:
            point = center + forward * along * size + sideways * across * size
            points.append((point.x, point.y))

        pygame.draw.polygon(screen, color, points)

    def draw_menu(self):
        draw_text(
            tr("一箭又一箭", "ARROW ESCAPE"),
            WIDTH // 2, 135, 46, center=True
        )
        draw_text(
            tr("点击箭头，让它沿朝向飞出棋盘", "Click arrows to send them off the board"),
            WIDTH // 2, 200, 23, MUTED, True
        )
        draw_text(
            tr("前方有阻挡会损失一次机会，全部清空即可通关",
               "Blocked arrows cost a chance. Clear the board to win."),
            WIDTH // 2, 240, 20, MUTED, True
        )

        self.button(
            (330, 305, 300, 50),
            tr("开始游戏", "Start game"), "start"
        )
        self.button(
            (330, 375, 300, 50),
            tr("继续上次游戏", "Continue"), "resume",
            self.saved_session is not None
        )
        self.button(
            (330, 445, 300, 50),
            tr("选择关卡", "Select level"), "select"
        )
        self.button(
            (330, 515, 300, 50),
            tr("随机可解关卡", "Random puzzle"), "random"
        )
        self.button(
            (330, 585, 300, 50),
            tr("退出", "Quit"), "quit"
        )

    def draw_select(self):
        draw_text(
            tr("选择关卡", "SELECT LEVEL"),
            WIDTH // 2, 105, 36, center=True
        )

        for i, (size, _) in enumerate(LEVELS):
            y = 170 + i * 85
            stars = self.records.get(str(i), 0)
            label = tr(
                f"第 {i + 1} 关   {size} × {size}   最佳：{stars} 星",
                f"Level {i + 1}   {size} x {size}   Best: {stars}/3"
            )
            self.button((260, y, 440, 60), label, f"level:{i}")

        self.button(
            (350, 635, 260, 48),
            tr("返回首页", "Back"), "menu"
        )

    def draw_playing(self):
        name = (
            tr("随机关卡", "Random puzzle")
            if self.random_mode
            else tr(
                f"第 {self.level_index + 1} / {len(LEVELS)} 关",
                f"Level {self.level_index + 1} / {len(LEVELS)}"
            )
        )

        draw_text(name, 40, 24, 27)

        pending = 1 if self.flight else 0
        stats = [
            (
                tr("剩余箭头", "Remaining"),
                remaining_count(self.board) + pending
            ),
            (tr("剩余失误次数", "Chances"), self.lives),
            (tr("得分", "Score"), self.score),
            (tr("用时", "Time"), format_time(self.elapsed)),
        ]

        for i, (label, value) in enumerate(stats):
            rect = pygame.Rect(40 + i * 225, 72, 205, 75)
            pygame.draw.rect(screen, WHITE, rect, border_radius=12)
            draw_text(label, rect.x + 15, rect.y + 9, 17, MUTED)
            draw_text(value, rect.x + 15, rect.y + 33, 27)

        left, top, step, side = self.layout()
        panel = pygame.Rect(left - 9, top - 9, side + 18, side + 18)
        pygame.draw.rect(screen, WHITE, panel, border_radius=14)

        mouse = pygame.mouse.get_pos()
        for r, row in enumerate(self.board):
            for c, direction in enumerate(row):
                rect = pygame.Rect(
                    left + c * step + 3,
                    top + r * step + 3,
                    step - 6,
                    step - 6
                )

                color = CELL if direction else EMPTY_CELL
                if (
                    direction and rect.collidepoint(mouse)
                    and not self.busy() and not self.auto
                ):
                    color = CELL_HOVER

                bumped = (
                    self.bump is not None
                    and (r, c) == (self.bump["row"], self.bump["col"])
                )
                if bumped:
                    color = (255, 217, 220)

                pygame.draw.rect(screen, color, rect, border_radius=8)

                if self.hint_cell == (r, c):
                    pygame.draw.rect(screen, GOLD, rect, 3, border_radius=8)

                if direction:
                    x, y = self.cell_center(r, c)
                    if bumped:
                        offset = math.sin(self.bump["time"] * 65) * 5
                        dr, dc = DIRECTIONS[direction]
                        x += dc * offset
                        y += dr * offset

                    self.draw_arrow(
                        x, y, direction, step * 0.72,
                        RED if bumped else ARROW_COLORS[direction]
                    )

        if self.flight is not None:
            # 飞出动画限制在棋盘区域内，不覆盖按钮或信息栏。
            old_clip = screen.get_clip()
            screen.set_clip(panel)
            self.draw_arrow(
                self.flight["x"],
                self.flight["y"],
                self.flight["direction"],
                step * 0.72,
                ARROW_COLORS[self.flight["direction"]]
            )
            screen.set_clip(old_clip)

        message = self.status if self.status_time > 0 else tr(
            "点击箭头消除；空格可暂停自动求解",
            "Click an arrow; SPACE toggles auto solve"
        )
        draw_text(message, WIDTH // 2, 665, 18, MUTED, True)

        can_operate = not self.busy() and not self.auto
        labels = [
            (tr("重开 R", "Restart R"), "restart", True),
            (tr("提示 H", "Hint H"), "hint", can_operate),
            (
                tr("撤销 U", "Undo U"), "undo",
                can_operate and bool(self.history)
            ),
            (
                tr("停止求解", "Stop auto") if self.auto
                else tr("自动求解", "Auto solve"),
                "auto", True
            ),
            (tr("保存并返回", "Save & menu"), "menu", True),
        ]

        for i, (label, action, enabled) in enumerate(labels):
            self.button(
                (40 + i * 180, 690, 160, 44),
                label, action, enabled
            )

    def draw_result(self):
        won = self.state == "won"
        title = (
            tr("本关通关！", "LEVEL COMPLETE!")
            if won else tr("挑战失败", "GAME OVER")
        )

        draw_text(
            title, WIDTH // 2, 160, 43,
            GREEN if won else RED, True
        )

        if won:
            draw_text(
                tr(
                    f"星级评价：{self.star_count()} / 3",
                    f"Rating: {self.star_count()} / 3"
                ),
                WIDTH // 2, 235, 30, GOLD, True
            )

        draw_text(
            tr(
                f"得分：{self.score}    用时：{format_time(self.elapsed)}",
                f"Score: {self.score}    Time: {format_time(self.elapsed)}"
            ),
            WIDTH // 2, 300, 27, TEXT, True
        )

        draw_text(
            tr(
                "使用提示、撤销或自动求解时，最高评为2星。",
                "Hints, undo or auto solve limit the rating to 2 stars."
            ),
            WIDTH // 2, 350, 18, MUTED, True
        )

        if won:
            if self.random_mode:
                label = tr("再来一个随机棋盘", "New random puzzle")
                action = "random"
            elif self.level_index < len(LEVELS) - 1:
                label = tr("进入下一关", "Next level")
                action = "next"
            else:
                label = tr("全部关卡完成 · 选择关卡", "All clear - select level")
                action = "select"

            self.button((310, 415, 340, 50), label, action)

        self.button(
            (310, 485, 340, 50),
            tr("重新挑战本关", "Retry this level"), "restart"
        )
        self.button(
            (310, 555, 340, 50),
            tr("返回首页", "Main menu"), "menu"
        )

    def draw(self):
        screen.fill(BG)
        self.buttons = []

        if self.state == "menu":
            self.draw_menu()
        elif self.state == "select":
            self.draw_select()
        elif self.state == "playing":
            self.draw_playing()
        else:
            self.draw_result()

        if self.save_error:
            draw_text(
                self.save_error,
                WIDTH // 2, 748, 14, RED, True
            )

    # -------------------- 事件处理 --------------------

    def action(self, action):
        if action == "start":
            self.start_level(0)
        elif action == "resume":
            self.resume()
        elif action == "select":
            self.state = "select"
        elif action.startswith("level:"):
            self.start_level(int(action.split(":")[1]))
        elif action == "random":
            self.start_level(0, True)
        elif action == "restart":
            self.restart()
        elif action == "next":
            self.start_level(self.level_index + 1)
        elif action == "hint":
            self.hint()
        elif action == "undo":
            self.undo()
        elif action == "auto":
            self.toggle_auto()
        elif action == "menu":
            self.back_to_menu()
        elif action == "quit":
            self.save_progress()
            self.running = False

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.save_progress()
            self.running = False
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.back_to_menu()
                return

            if self.state in ("playing", "won", "lost"):
                if event.key == pygame.K_r:
                    self.restart()
                elif self.state == "playing":
                    if event.key == pygame.K_h:
                        self.hint()
                    elif event.key == pygame.K_u:
                        self.undo()
                    elif event.key == pygame.K_SPACE:
                        self.toggle_auto()
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        for rect, action, enabled in self.buttons:
            if rect.collidepoint(event.pos):
                if enabled:
                    self.action(action)
                return

        if self.state != "playing" or self.busy() or self.auto:
            return

        left, top, step, side = self.layout()
        board_rect = pygame.Rect(left, top, side, side)

        if board_rect.collidepoint(event.pos):
            col = int((event.pos[0] - left) // step)
            row = int((event.pos[1] - top) // step)

            # 点击格子之间的留白不触发操作。
            cell_rect = pygame.Rect(
                left + col * step + 3,
                top + row * step + 3,
                step - 6,
                step - 6
            )

            if cell_rect.collidepoint(event.pos):
                self.click_arrow(row, col)

    def run(self):
        while self.running:
            dt = min(clock.tick(FPS) / 1000.0, 0.05)

            # 先建立当前页面的按钮区域，再处理事件。
            self.draw()

            for event in pygame.event.get():
                self.handle_event(event)
                if not self.running:
                    break

                # 页面切换后立即更新按钮，避免使用上一页的区域。
                self.draw()

            if not self.running:
                break

            self.update(dt)
            self.draw()
            pygame.display.flip()


if __name__ == "__main__":
    try:
        Game().run()
    finally:
        pygame.quit()