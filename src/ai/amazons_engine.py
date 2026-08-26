# src/ai/amazons_engine.py
# 亚马逊棋 KataGo (Amazons 分支) 引擎桥接。
#
# 说明（重要）：
#   gpu 后端使用项目内置的 amazon10x10_xzf 最新模型
#   （gen223_b featurev1，b20c256legacyv10），配合启用了
#   USE_AMAZON_FEATURES_V1 的 OpenCL 版 amazons.exe。该引擎按模型内部名称中的
#   featurev1 标记启用新版输入；旧 2022 引擎不能正确推理该模型。
#
#   本项目还保留两套参考模型：
#     - amazon_L              最初会返回 pass 的原始模型
#     - amazon_Z              服务器评测使用的 amazon18 强模型
#   两者都由可读取外部权重的 kataAmazonEngineCuda/amazons.exe 推理。
#   默认自动选择：依次尝试 amazon_X、amazon_Z、amazon_L。
#
#   所有路径都相对本文件（__file__）计算，项目整体复制到别处也能正常工作。
#   正常运行始终使用项目内随附的引擎、模型和配置；构造函数的显式参数仅供开发测试。
import logging
import hashlib
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
# 将项目的根目录添加到 sys.path
sys.path.append(project_root)
from src.core.simulator import WHITE_AMAZON, BLACK_AMAZON, OBSTACLE, EMPTY
from src.ai.ai_profile import KataSearchConfig


logger = logging.getLogger(__name__)
_EOF = object()


def parse_genmove_analyze_details(response: str):
    """Return the selected move and all numeric analysis fields by move."""
    played = None
    move_info = {}
    for raw_line in response.splitlines():
        line = raw_line.strip()
        if line.startswith("play "):
            parts = line.split()
            if len(parts) >= 2:
                played = parts[1]
            continue
        if "info move " not in line:
            continue
        for segment in line.split("info move ")[1:]:
            tokens = segment.strip().split()
            if not tokens:
                continue
            move = tokens[0]
            metrics = {
                "move": move,
                "visits": 0,
                "winrate": None,
                "score_mean": None,
                "score_lead": None,
                "score_selfplay": None,
                "score_stdev": None,
                "utility": None,
                "prior": None,
            }
            index = 1
            while index < len(tokens) - 1:
                key, value = tokens[index], tokens[index + 1]
                if key == "visits":
                    try:
                        metrics["visits"] = int(value)
                    except ValueError:
                        metrics["visits"] = 0
                elif key == "winrate":
                    try:
                        metrics["winrate"] = float(value) * 100.0
                    except ValueError:
                        metrics["winrate"] = None
                elif key == "scoreMean":
                    try:
                        metrics["score_mean"] = float(value)
                    except ValueError:
                        pass
                elif key == "scoreLead":
                    try:
                        metrics["score_lead"] = float(value)
                    except ValueError:
                        pass
                elif key == "scoreSelfplay":
                    try:
                        metrics["score_selfplay"] = float(value)
                    except ValueError:
                        pass
                elif key == "scoreStdev":
                    try:
                        metrics["score_stdev"] = float(value)
                    except ValueError:
                        pass
                elif key == "utility":
                    try:
                        metrics["utility"] = float(value)
                    except ValueError:
                        pass
                elif key == "prior":
                    try:
                        metrics["prior"] = float(value)
                    except ValueError:
                        pass
                index += 1
            move_info[move] = metrics

    ranked_details = sorted(
        move_info.values(),
        key=lambda item: item["visits"],
        reverse=True,
    )
    selected = played or (ranked_details[0]["move"] if ranked_details else None)
    return selected, move_info.get(selected), ranked_details


def parse_genmove_analyze(response: str):
    """Parse bounded ``kata-genmove_analyze`` output without engine state.

    Returns ``(played, win_rate_percent, visits, ranked_candidates)`` where
    candidates are ``(move, win_rate_percent, visits)`` sorted by visits.
    The stable four-item interface is retained for callers that do not need
    score-lead metadata.
    """
    selected, selected_details, ranked_details = \
        parse_genmove_analyze_details(response)
    ranked = [
        (details["move"], details["winrate"], details["visits"])
        for details in ranked_details
    ]
    selected_visits = (selected_details["visits"]
                       if selected_details is not None else None)
    selected_winrate = (selected_details["winrate"]
                        if selected_details is not None else None)
    return selected, selected_winrate, selected_visits, ranked

# --- 引擎后端表（相对本文件，保证可移植）----------------------------------------
# 本项目提供三个 KataGo 模型选项，每个是一套 (目录, 可执行文件, 模型, 配置)：
#   'gpu'    -> kataAmazonEngineCuda ：XZF 最新模型 + OpenCL 版 amazons.exe。
#               需要支持 OpenCL 的显卡及正确安装的驱动。
#   'legacy' -> kataAmazonEngineCuda ：兼容引擎 + kataAmazonEngine 下的原始 L 权重及配置。
#               使用外部权重而不是旧程序内嵌权重，因而替换兼容模型会真实生效。
#               原始模型曾会返回 pass，桥接层会改选访问量最高的合法坐标。
#   'z'      -> kataAmazonEngineCuda ：同一兼容引擎 + 服务器评测使用的
#               amazon18-s2161408-d449231 权重，沿用稳定的 L 搜索配置。

BACKENDS = {
    'gpu': {
        'dir': os.path.normpath(os.path.join(current_dir, 'kataAmazonEngineCuda')),
        'exe': 'amazons.exe',
        'model': 'amazon10x10_xzf.bin.gz',
        'cfg': 'engine.cfg',
        'hint_cfg': 'hint.cfg',
        'runtime_files': ('libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll'),
        'label': 'XZF gen223_b featurev1（OpenCL/GPU）',
    },
    'legacy': {
        'dir': os.path.normpath(os.path.join(current_dir, 'kataAmazonEngineCuda')),
        'exe': 'amazons.exe',
        'model': os.path.join('..', 'kataAmazonEngine', 'weights', 'amazons10x10.bin.gz'),
        'cfg': os.path.join('..', 'kataAmazonEngine', 'engine.cfg'),
        'hint_cfg': os.path.join('..', 'kataAmazonEngine', 'hint.cfg'),
        'runtime_files': ('libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll'),
        'label': 'amazon_L（OpenCL/GPU）',
    },
    'z': {
        'dir': os.path.normpath(os.path.join(current_dir, 'kataAmazonEngineCuda')),
        'exe': 'amazons.exe',
        'model': os.path.join(
            '..', 'kataAmazonEngine', 'weights',
            'amazon18-s2161408-d449231.bin.gz'),
        'cfg': os.path.join('..', 'kataAmazonEngine', 'engine.cfg'),
        'hint_cfg': os.path.join('..', 'kataAmazonEngine', 'hint.cfg'),
        'runtime_files': (
            'libgcc_s_seh-1.dll', 'libstdc++-6.dll', 'libwinpthread-1.dll'),
        'label': 'amazon_Z（OpenCL/GPU）',
    },
}

def _backend_files_available(spec: dict) -> bool:
    required = (
        spec['exe'], spec['model'], spec['cfg'], spec.get('hint_cfg', spec['cfg']),
        *spec.get('runtime_files', ()),
    )
    return all(os.path.isfile(
        item if os.path.isabs(item) else os.path.join(spec['dir'], item)
    ) for item in required)


# 默认后端：依次选择文件完整的 amazon_X、amazon_Z、amazon_L。
_DEFAULT_BACKEND = next(
    (key for key in ('gpu', 'z', 'legacy')
     if _backend_files_available(BACKENDS[key])),
    'legacy',
)

# 兼容旧引用
_CUDA_ENGINE_DIR = BACKENDS['gpu']['dir']
CUDA_ENGINE_DIR = _CUDA_ENGINE_DIR

_DEFAULT_ENGINE_DIR = BACKENDS[_DEFAULT_BACKEND]['dir']
_DEFAULT_ENGINE_EXE = BACKENDS[_DEFAULT_BACKEND]['exe']
_DEFAULT_MODEL = BACKENDS[_DEFAULT_BACKEND]['model']
_DEFAULT_CFG = BACKENDS[_DEFAULT_BACKEND]['cfg']


def engine_spec_for_backend(backend: str) -> dict:
    """按后端名返回其 (dir/exe/model/cfg/label) 规格。未知后端回退到默认后端。"""
    return BACKENDS.get(backend, BACKENDS[_DEFAULT_BACKEND])


def engine_dir_for_backend(backend: str) -> str:
    """按后端名返回引擎目录（兼容旧调用）。"""
    return engine_spec_for_backend(backend)['dir']


def backend_available(backend: str) -> bool:
    """Return whether the executable, model and configs are all present."""
    spec = engine_spec_for_backend(backend)
    return _backend_files_available(spec)


def resolve_engine_resources(backend: str, engine_dir: str | None = None,
                             engine_exe: str | None = None,
                             model_file: str | None = None,
                             config_file: str | None = None):
    """Resolve normal runtime resources from the bundled backend directory."""
    spec = engine_spec_for_backend(backend)
    return (
        os.path.abspath(engine_dir or spec['dir']),
        engine_exe or spec['exe'],
        model_file or spec['model'],
        config_file or spec['cfg'],
    )


def _set_config_value(source: str, key: str, value: str) -> str:
    """Replace or append one exact KataGo configuration value."""
    replacement = f"{key} = {value}"
    pattern = rf"(?m)^\s*{re.escape(key)}\s*=.*$"
    if re.search(pattern, source):
        return re.sub(pattern, replacement, source)
    return source.rstrip() + "\n" + replacement + "\n"


def profile_config_for_visits(
        backend: str, visits: int,
        score_utility_enabled: bool | None = None,
        search_config: KataSearchConfig | None = None) -> str:
    """Return a generated config with per-search profile overrides.

    The shipped engine configuration is deliberately never edited.  A stable
    file in the platform temp directory also lets multiple turns reuse the
    same engine profile without recreating it.
    """
    spec = engine_spec_for_backend(backend)
    visits = max(1, int(visits))
    source = os.path.join(spec['dir'], spec['cfg'])
    with open(source, 'r', encoding='utf-8') as handle:
        source_text = handle.read()
    rendered = _set_config_value(source_text, "maxVisits", str(visits))

    if score_utility_enabled is not None:
        factor = "0.02" if score_utility_enabled else "0.0"
        rendered = _set_config_value(
            rendered, "dynamicScoreUtilityFactor", factor)

    if search_config is not None:
        search_config = search_config.normalized()
        search_overrides = {
            "chosenMoveTemperatureEarly": str(
                search_config.move_temperature_early),
            "chosenMoveTemperature": str(search_config.move_temperature),
            "rootNoiseEnabled": str(
                search_config.root_noise_enabled).lower(),
            "nnPolicyTemperature": str(search_config.policy_temperature),
            "cpuctExploration": str(search_config.cpuct_exploration),
            "cpuctExplorationLog": str(search_config.cpuct_exploration_log),
            "cpuctExplorationBase": str(search_config.cpuct_exploration_base),
            "useGraphSearch": str(search_config.use_graph_search).lower(),
            "subtreeValueBiasFactor": str(
                search_config.subtree_value_bias_factor),
            "numSearchThreads": str(search_config.num_search_threads),
            "nnRandomize": str(search_config.nn_randomize).lower(),
        }
        for key, value in search_overrides.items():
            rendered = _set_config_value(rendered, key, value)

    directory = os.path.join(tempfile.gettempdir(), "amazons-katago-profiles", backend)
    os.makedirs(directory, exist_ok=True)
    content_hash = hashlib.sha256(rendered.encode('utf-8')).hexdigest()[:12]
    destination = os.path.join(
        directory, f"engine-visits-{visits}-{content_hash}.cfg")
    try:
        # Exclusive creation is safe when several app instances request the
        # same profile concurrently.  The content hash makes bundled config
        # changes select a fresh file after an application update.
        with open(destination, 'x', encoding='utf-8', newline='\n') as handle:
            handle.write(rendered)
    except FileExistsError:
        pass
    return destination


class AmazonsKataGoEngine(QObject):
    """
    管理亚马逊棋 AI 引擎（基于GTP协议）的类。
    负责启动、关闭引擎，以及发送和接收GTP命令。
    使用 kata-genmove_analyze 生成着法，可同时返回胜率与搜索次数。
    """
    # 定义两个信号，用于广播通信内容
    # command_sent: 当一个命令发送给引擎时发射
    # response_received: 当从引擎接收到任何一行输出时发射
    command_sent = pyqtSignal(str)
    response_received = pyqtSignal(str)

    _GTP_COLUMNS_10X10 = "ABCDEFGHJK"

    @classmethod
    def _require_playable_move(cls, move, context: str = "") -> str:
        """Accept only a concrete 10x10 coordinate from a play command.

        KataGo's GTP protocol can legally return ``pass`` or ``resign`` for
        Go.  Neither is a move in Amazons, so accepting either token would
        make the GUI end a game without a board move.  Keep this check at the
        engine boundary so gameplay and hint callers share the same rule.
        """
        value = str(move).strip().upper()
        if value in ("PASS", "RESIGN"):
            raise RuntimeError(
                f"AI 引擎返回了禁止的{value.lower()}结果"
                + (f"（阶段：{context}）" if context else ""))
        if len(value) < 2 or value[0] not in cls._GTP_COLUMNS_10X10:
            raise RuntimeError(f"AI 引擎返回了非落子坐标：{move}")
        try:
            row = int(value[1:])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"AI 引擎返回了非落子坐标：{move}") from exc
        if not 1 <= row <= 10:
            raise RuntimeError(f"AI 引擎返回了非落子坐标：{move}")
        return value

    def __init__(self,
                 backend: str = None,
                 engine_dir: str = None,
                 engine_exe: str = None,
                 model_file: str = None,
                 config_file: str = None,
                 max_visits: int | None = None,
                 score_utility_enabled: bool | None = None,
                 search_config: KataSearchConfig | None = None):

        super().__init__()

        self.startup_timeout = float(os.environ.get('KATA_AMAZON_STARTUP_TIMEOUT', '180'))
        self.command_timeout = float(os.environ.get('KATA_AMAZON_COMMAND_TIMEOUT', '120'))
        self._command_lock = threading.RLock()
        self._output_queue = queue.Queue()
        self._reader_thread = None

        # 若指定了后端（X/Z/L），用其整套规格作为默认；否则用全局默认后端。
        spec = engine_spec_for_backend(backend) if backend else BACKENDS[_DEFAULT_BACKEND]
        self.backend = backend or _DEFAULT_BACKEND

        # Bundled resources are authoritative.  Ambient machine-level
        # KATA_AMAZON_* variables must not redirect a portable build to files
        # outside the application directory.  Explicit constructor arguments
        # remain available for tests and engine development.
        engine_dir, engine_exe, model_file, config_file = resolve_engine_resources(
            self.backend, engine_dir, engine_exe, model_file, config_file)
        if max_visits is not None:
            config_file = profile_config_for_visits(
                self.backend,
                max_visits,
                score_utility_enabled,
                search_config,
            )
        self.max_visits = max_visits
        self.score_utility_enabled = score_utility_enabled
        self.search_config = search_config

        # 允许相对路径：以引擎目录为基准解析（引擎子进程也以此为工作目录）
        engine_path = os.path.join(engine_dir, engine_exe)

        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"引擎文件未找到: {engine_path}")

        model_abs = model_file if os.path.isabs(model_file) else os.path.join(engine_dir, model_file)
        if not os.path.exists(model_abs):
            raise FileNotFoundError(f"模型文件未找到: {model_abs}")

        # 使用相对引擎目录的模型路径，保证可移植（cwd=engine_dir）
        model_arg = model_file
        command = [engine_path, "gtp", "-config", config_file, "-model", model_arg]

        startupinfo = None
        creationflags = 0
        if os.name == 'nt':
            # 隐藏引擎控制台黑窗口
            creationflags = 0x08000000  # CREATE_NO_WINDOW

        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding='utf-8',
                text=True,
                bufsize=1,
                startupinfo=startupinfo,
                creationflags=creationflags,
                cwd=engine_dir
            )
        except Exception:
            logger.exception("启动 AI 引擎失败")
            raise

        self._reader_thread = threading.Thread(
            target=self._pump_engine_output,
            name=f"kata-amazon-output-{self.process.pid}",
            daemon=True,
        )
        self._reader_thread.start()

        # 最近一次生成着法的胜率(%)与搜索次数，由 genmove_analyze 更新
        self.last_winrate = None      # 0..100，当前行动方视角
        self.last_visits = None
        self.last_score_lead = None   # 当前行动方视角的预计领先分
        self.last_score_selfplay = None  # 当前策略下的预计终局领地差
        self.last_score_stdev = None  # 分差预测的标准差
        self.last_utility = None
        self.last_policy_prior = None
        self._last_genmove_metrics = {}

        try:
            self._wait_for_engine_ready()
            self._initialize_engine()
        except Exception:
            self.abort()
            raise
        _label = spec.get('label', self.backend)
        logger.info("亚马逊棋 AI 引擎[%s]初始化完成，准备就绪。", _label)

    def _pump_engine_output(self):
        """Continuously drain stdout so GTP reads can use bounded queue waits."""
        try:
            if self.process.stdout:
                for raw_line in self.process.stdout:
                    self._output_queue.put(raw_line.rstrip('\r\n'))
        finally:
            self._output_queue.put(_EOF)

    def _readline_with_timeout(self, deadline: float, context: str) -> str:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            self._abort_timed_out_process(context)
        try:
            line = self._output_queue.get(timeout=max(remaining, 0.001))
        except queue.Empty:
            self._abort_timed_out_process(context)

        if line is _EOF:
            code = self.process.poll()
            raise RuntimeError(f"AI 引擎输出已关闭（退出码：{code}，阶段：{context}）。")
        return line

    def _abort_timed_out_process(self, context: str):
        if self.process.poll() is None:
            self.process.kill()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        raise TimeoutError(f"AI 引擎在 {context} 阶段等待超时。")

    def _wait_for_engine_ready(self):
        deadline = time.monotonic() + self.startup_timeout
        while True:
            line = self._readline_with_timeout(deadline, "启动")
            logger.debug("FROM ENGINE (startup): %s", line)
            self.response_received.emit(line)
            if "GTP ready, beginning main protocol loop" in line:
                break

    def _send_command(self, command: str):
        if self.process.poll() is not None:
            raise RuntimeError(f"AI 引擎已经退出（退出码：{self.process.returncode}）。")
        if (not self.process.stdin
                or getattr(self.process.stdin, 'closed', False)):
            raise RuntimeError("AI 引擎标准输入不可用。")
        logger.debug("TO ENGINE: %s", command)
        self.command_sent.emit(command)
        try:
            self.process.stdin.write(command + '\n')
            self.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            # A hint cancellation may terminate the subprocess between poll()
            # and write().  Convert that race into the same engine-level error
            # used everywhere else instead of leaking an OSError from cleanup.
            raise RuntimeError(
                f"AI 引擎输入已关闭（退出码：{self.process.poll()}）。") from exc

    def _read_response(self, timeout: float | None = None) -> str:
        """
        读取一个完整的GTP响应块。
        GTP响应块总是以一个空行结束。
        """
        response_lines = []
        deadline = time.monotonic() + (self.command_timeout if timeout is None else timeout)
        while True:
            line = self._readline_with_timeout(deadline, "执行命令")
            self.response_received.emit(line)
            if line == "":
                break
            response_lines.append(line)
        # 将所有行合并成一个字符串返回
        return "\n".join(response_lines)

    def _execute_sync_command(self, command: str) -> str:
        """
        发送命令并处理可能的多行响应。
        """
        with self._command_lock:
            self._send_command(command)
            full_response = self._read_response()

        if full_response.startswith('?'):
            raise RuntimeError(f"引擎命令失败: {command}\n响应: {full_response}")

        # GTP的成功响应以 '=' 开头
        if full_response.startswith('='):
            # 移除第一行的 '='，并返回之后的所有内容
            # 这对于 showboard (返回多行) 和普通命令 (只返回=) 都有效
            return full_response.lstrip('=').strip()

        # 理论上不应发生，但作为保障
        return full_response

    def _initialize_engine(self):
        self._execute_sync_command("boardsize 10")
        self._execute_sync_command("clear_board")

    # ---------- 带胜率的生成着法 ----------------------------------------------
    def _genmove_analyze(self, player_char: str) -> tuple[str, float | None, int | None]:
        """
        用 kata-genmove_analyze 生成一步着法，返回 (坐标, 胜率百分比, 搜索次数)。

        胜率为「当前行动方」(player_char) 视角，0..100。
        引擎输出形如（可能所有 info 在同一行，也可能分行）：
            info move K7 visits 165 winrate 0.6458 ... order 0 pv ...
            info move A7 visits 122 winrate 0.62 ...
            play K7
        取被选中的 play 着法对应的 info 行胜率；找不到则用访问量最大的 info 行。
        """
        response = self._execute_sync_command(f"kata-genmove_analyze {player_char}")

        played, selected_metrics, ranked_details = \
            parse_genmove_analyze_details(response)
        self._last_genmove_metrics = dict(selected_metrics or {})
        win_pct = (selected_metrics["winrate"]
                   if selected_metrics is not None else None)
        visits = (selected_metrics["visits"]
                  if selected_metrics is not None else None)
        if played is None:
            # 兜底：走普通 genmove（无胜率信息）
            played = self._execute_sync_command(f"genmove {player_char}").strip()
            self._last_genmove_metrics = {}
            return AmazonsKataGoEngine._require_playable_move(
                played, "搜索"), None, None

        normalized = str(played).strip().lower()
        if normalized in ("pass", "resign"):
            # Amazons has neither pass nor resignation moves. Legacy KataGo
            # can still choose pass while reporting real coordinates in the
            # same analysis. Replace it with the most-visited coordinate and
            # repair the engine board before the next stage starts.
            fallback = next(
                (details for details in ranked_details
                 if str(details["move"]).strip().lower()
                 not in ("pass", "resign")),
                None,
            )
            if fallback is None:
                return AmazonsKataGoEngine._require_playable_move(
                    played, "搜索"), win_pct, visits
            fallback_move = fallback["move"]
            fallback_rate = fallback["winrate"]
            fallback_visits = fallback["visits"]
            self._last_genmove_metrics = dict(fallback)
            fallback_move = AmazonsKataGoEngine._require_playable_move(
                fallback_move, "搜索候选")
            if normalized == "pass":
                self._execute_sync_command("undo")
            self._execute_sync_command(f"play {player_char} {fallback_move}")
            logger.warning(
                "AI 引擎返回 %s，已改走最高访问量候选 %s（%s visits）",
                normalized, fallback_move, fallback_visits)
            return fallback_move, fallback_rate, fallback_visits

        return AmazonsKataGoEngine._require_playable_move(
            played, "搜索"), win_pct, visits

    def _restore_temporary_moves(self, count: int):
        """Undo temporary analysis moves only while the subprocess is writable.

        Hint cancellation intentionally kills a blocking engine.  Attempting an
        ``undo`` after that point only masks the original cancellation with a
        secondary broken-pipe error.
        """
        process = getattr(self, "process", None)
        if process is not None:
            stdin = getattr(process, "stdin", None)
            if (process.poll() is not None or stdin is None
                    or getattr(stdin, 'closed', False)):
                return
        for _ in range(max(0, count)):
            try:
                self._execute_sync_command("undo")
            except (RuntimeError, TimeoutError, OSError, ValueError):
                break

    def get_best_turn(self, player: int) -> tuple[str, str, str]:
        """分析完整回合，但不永久推进引擎棋盘。

        只有 GUI 模拟器确认回合合法后，才通过 ``play_turn`` 提交到所有引擎。
        """
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        opponent_char = 'w' if player_char == 'b' else 'b'
        played_count = 0
        try:
            self._last_genmove_metrics = {}
            start_pos_str, winrate, visits = self._genmove_analyze(player_char)
            start_metrics = dict(
                getattr(self, '_last_genmove_metrics', {}) or {})
            played_count += 1
            move_pos_str, _move_rate, _move_visits = self._genmove_analyze(opponent_char)
            played_count += 1
            arrow_pos_str, _arrow_rate, _arrow_visits = self._genmove_analyze(player_char)
            played_count += 1

            self.last_winrate = winrate
            self.last_visits = visits
            self.last_score_lead = start_metrics.get("score_lead")
            self.last_score_selfplay = start_metrics.get("score_selfplay")
            self.last_score_stdev = start_metrics.get("score_stdev")
            self.last_utility = start_metrics.get("utility")
            self.last_policy_prior = start_metrics.get("prior")
            return (start_pos_str, move_pos_str, arrow_pos_str)
        finally:
            AmazonsKataGoEngine._restore_temporary_moves(self, played_count)

    def get_move_arrow_for_start(self, player: int, start_coord: str) -> tuple[str, str]:
        """给定已落下的起点坐标，查询引擎后续的移动目标和射箭目标。

        用于 AI 提示：拿到最佳「选子」后，进一步获取该候选的完整一回合。
        返回 (move_coord, arrow_coord)，均为 GTP 坐标字符串。
        注意：调用前 start_coord 必须已经 play 到引擎棋盘上；
              调用后需由上层 undo 3 次恢复局面。
        """
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        opponent_char = 'w' if player_char == 'b' else 'b'
        move_pos_str, _move_rate, _move_visits = self._genmove_analyze(opponent_char)
        arrow_pos_str, _arrow_rate, _arrow_visits = self._genmove_analyze(player_char)
        return move_pos_str, arrow_pos_str

    def analyze_turn_stages(self, player: int):
        """分析最佳完整回合，并返回三个阶段各自的胜率。

        返回 ``(turn, win_rates, visits)``：
          - turn: (选子坐标, 移动坐标, 射箭坐标)
          - win_rates: 三个阶段统一换算为原行动方视角的百分比
          - visits: 三个阶段各自的搜索访问次数

        引擎用交替颜色编码一个亚马逊棋回合：当前方选子、另一颜色移动、
        当前方射箭。配置中的胜率按阶段的 side-to-move 报告，因此移动阶段
        必须用 ``100 - winrate`` 换回本回合原行动方视角。
        """
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        opponent_char = 'w' if player_char == 'b' else 'b'
        played_count = 0
        try:
            start, start_win, start_visits = self._genmove_analyze(player_char)
            start = AmazonsKataGoEngine._require_playable_move(start, "提示选子")
            played_count += 1

            move, move_opponent_win, move_visits = self._genmove_analyze(opponent_char)
            move = AmazonsKataGoEngine._require_playable_move(move, "提示移动")
            played_count += 1

            arrow, arrow_win, arrow_visits = self._genmove_analyze(player_char)
            arrow = AmazonsKataGoEngine._require_playable_move(arrow, "提示射箭")
            played_count += 1

            move_win = (None if move_opponent_win is None
                        else 100.0 - move_opponent_win)
            return (
                (start, move, arrow),
                (start_win, move_win, arrow_win),
                (start_visits, move_visits, arrow_visits),
            )
        finally:
            # kata-genmove_analyze 会实际落下一手；分析完成后必须完整恢复局面。
            AmazonsKataGoEngine._restore_temporary_moves(self, played_count)

    def analyze_candidates(self, player: int, top_n: int = 3) -> list[tuple[str, float]]:
        """
        返回当前局面下「起点(选子)」候选着法及胜率：[(坐标, 胜率百分比), ...]。
        按引擎访问次数（visits）降序排列——MCTS 中访问量最大的着法才是引擎真正信任的最佳着法，
        胜率在访问量极少时不可靠（如 1 次访问 100% 胜率无意义）。
        用于棋盘上的 AI 提示（只提示第一段落点，即将要移动的皇后）。

        实现说明：不使用 `kata-analyze`（它会持续输出、不发送 GTP 结束空行，会导致
        读取阻塞），改用有界的 `kata-genmove_analyze` 拿到候选着法及胜率，随后 `undo`
        撤销它实际落下的那一手，保持局面不变。
        """
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        response = self._execute_sync_command(f"kata-genmove_analyze {player_char}")

        played, _winrate, _visits, ranked = parse_genmove_analyze(response)

        # 撤销 kata-genmove_analyze 实际落下的一手，保持局面不变
        if played is not None and str(played).strip().lower() != "resign":
            # kata-genmove_analyze actually applied either the selected
            # coordinate or pass. Undo both before returning filtered hints.
            AmazonsKataGoEngine._restore_temporary_moves(self, 1)

        playable = [
            (move, winrate)
            for move, winrate, _ in ranked
            if (winrate is not None
                and str(move).strip().lower() not in ("pass", "resign"))
        ]
        return playable[:top_n]

    def ranked_start_candidates(self, player: int, top_n: int = 3) -> list[tuple[str, float | None, int | None]]:
        """Return ranked starting queens while restoring the engine board."""
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        response = self._execute_sync_command(f"kata-genmove_analyze {player_char}")
        played, _winrate, _visits, ranked = parse_genmove_analyze(response)
        if played is not None and str(played).strip().lower() != "resign":
            AmazonsKataGoEngine._restore_temporary_moves(self, 1)
        playable = [
            (move, rate, visits)
            for move, rate, visits in ranked
            if str(move).strip().lower() not in ('pass', 'resign')
        ]
        return playable[:top_n]

    def analyze_turn_for_start(self, player: int, start: str,
                               start_win: float | None = None,
                               start_visits: int | None = None,
                               progress_callback=None):
        """Analyse move and arrow after a chosen first-stage move.

        GTP encodes an Amazons turn as player / opponent / player.  The
        temporary three commands are always undone, including failures.
        """
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        opponent_char = 'w' if player_char == 'b' else 'b'
        played_count = 0
        try:
            self._execute_sync_command(f"play {player_char} {start}")
            played_count += 1
            if progress_callback is not None:
                progress_callback("piece", start_win, start_visits)
            move, opponent_rate, move_visits = self._genmove_analyze(opponent_char)
            played_count += 1
            if str(move).strip().lower() in ('pass', 'resign'):
                return None, None, None
            move_rate = None if opponent_rate is None else 100.0 - opponent_rate
            if progress_callback is not None:
                progress_callback("move", move_rate, move_visits)
            arrow, arrow_rate, arrow_visits = self._genmove_analyze(player_char)
            played_count += 1
            if str(arrow).strip().lower() in ('pass', 'resign'):
                return None, None, None
            if progress_callback is not None:
                progress_callback("arrow", arrow_rate, arrow_visits)
            return ((start, move, arrow),
                    (start_win, move_rate, arrow_rate),
                    (start_visits, move_visits, arrow_visits))
        finally:
            AmazonsKataGoEngine._restore_temporary_moves(self, played_count)

    def clear_board(self):
        """向引擎发送 clear_board 命令。"""
        self._execute_sync_command("clear_board")
        self.last_winrate = None
        self.last_visits = None

    def play_turn(self, player: int, start_str: str, move_str: str, arrow_str: str):
        player_char = 'b' if player == BLACK_AMAZON else 'w'
        opponent_char = 'w' if player_char == 'b' else 'b'

        self._execute_sync_command(f"play {player_char} {start_str}")
        self._execute_sync_command(f"play {opponent_char} {move_str}")
        self._execute_sync_command(f"play {player_char} {arrow_str}")

    def undo(self):
        self._execute_sync_command("undo")
        self._execute_sync_command("undo")
        self._execute_sync_command("undo")

    def set_time_controls(self, main_time: int, byo_yomi_time: int, byo_yomi_stones: int):
        """
        设置引擎的时间控制。
        :param main_time: 主要思考时间 (秒)
        :param byo_yomi_time: 读秒时间 (秒)
        :param byo_yomi_stones: 读秒期间的棋子数
        """
        byo_yomi_time = int(byo_yomi_time)
        command = f"time_settings {main_time} {byo_yomi_time} {byo_yomi_stones}"
        self._execute_sync_command(command)
        logger.info("已向引擎设置时间: %s", command)

    def close(self):
        if not hasattr(self, 'process'):
            return
        with self._command_lock:
            if self.process.poll() is None:
                logger.info("正在关闭亚马逊棋 AI 引擎")
                try:
                    self._send_command("quit")
                    self.process.wait(timeout=5)
                except (BrokenPipeError, OSError, RuntimeError, subprocess.TimeoutExpired):
                    if self.process.poll() is None:
                        self.process.kill()
                        try:
                            self.process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            pass
            for stream in (self.process.stdin, self.process.stdout):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    pass

    def abort(self):
        """Immediately stop the subprocess; used only during app shutdown."""
        if hasattr(self, 'process') and self.process.poll() is None:
            self.process.kill()
            try:
                # kill() is already the hard-stop path.  Do not make window
                # shutdown wait several seconds for a child that is gone.
                self.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass

    def _convert_coord(self, coord_str: str) -> tuple[int, int]:
        """将 'A1' 或 'J10' 这样的棋谱坐标转换为内部数组坐标 (9, 0) 或 (0, 8)"""
        # --- 支持大写和无'I'的列 ---
        GTP_COLS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

        col_char = coord_str[0].upper()
        row_str = coord_str[1:]

        if col_char not in GTP_COLS:
            raise ValueError(f"无法解析的列坐标: {col_char}")

        col_idx = GTP_COLS.index(col_char)
        #row_idx = 10 - int(row_str)
        row_idx = int(row_str)-1

        return (row_idx, col_idx)

    def _convert_to_gtp_coord(self, row_idx: int, col_idx: int) -> str:
        """将内部数组坐标 (9, 0) 或 (0, 8) 转换为 'A1' 或 'J10' 这样的棋谱坐标"""
        # --- 支持大写和无'I'的列 ---
        GTP_COLS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

        if col_idx < 0 or col_idx >= len(GTP_COLS):
            raise ValueError(f"列索引超出范围: {col_idx}")

        if row_idx < 0 or row_idx >= 10:  # 假设10x10棋盘
            raise ValueError(f"行索引超出范围: {row_idx}")

        col_char = GTP_COLS[col_idx]
        #row_number = 10 - row_idx  # 反转换：内部行索引0对应棋谱行10
        row_number = row_idx+1
        return f"{col_char}{row_number}"
