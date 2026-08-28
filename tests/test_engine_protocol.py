import pytest
from types import SimpleNamespace
from pathlib import Path

from src.ai.amazons_engine import (BACKENDS, AmazonsKataGoEngine,
                                   parse_genmove_analyze,
                                   parse_genmove_analyze_details)
from src.core.simulator import (
    BLACK_AMAZON, WHITE_AMAZON, OBSTACLE,
)


class _RaisingInput:
    def write(self, _value):
        raise OSError(22, "Invalid argument")

    def flush(self):
        raise AssertionError("flush should not run after write fails")


class _Signal:
    def emit(self, _value):
        pass


def test_send_command_normalizes_process_closing_race():
    engine = SimpleNamespace(
        process=SimpleNamespace(
            poll=lambda: None,
            returncode=None,
            stdin=_RaisingInput(),
        ),
        command_sent=_Signal(),
    )

    with pytest.raises(RuntimeError, match="输入已关闭"):
        AmazonsKataGoEngine._send_command(engine, "undo")


def test_parse_analyze_prefers_actual_play_over_highest_visits():
    response = """info move A1 visits 200 winrate 0.61 info move B2 visits 120 winrate 0.57
play B2"""
    move, winrate, visits, ranked = parse_genmove_analyze(response)
    assert move == "B2"
    assert winrate == pytest.approx(57.0)
    assert visits == 120
    assert ranked[0] == ("A1", 61.0, 200)


def test_parse_analyze_falls_back_to_most_visited_move():
    response = "info move C3 visits 4 winrate bad info move D4 visits 9 winrate 0.501"
    move, winrate, visits, ranked = parse_genmove_analyze(response)
    assert move == "D4"
    assert winrate == 50.1
    assert visits == 9
    assert ranked[-1] == ("C3", None, 4)


def test_parse_analyze_exposes_score_and_policy_metadata():
    response = (
        "info move A1 visits 200 utility 0.42 winrate 0.61 "
        "scoreMean 0.01 scoreStdev 1.25 scoreLead -3.5 "
        "scoreSelfplay 3.0 prior 0.18 pv A1 "
        "info move B2 visits 120 utility -0.1 winrate 0.57 "
        "scoreMean 0.02 scoreLead -2.25 scoreSelfplay 1.75 "
        "scoreStdev 2.5 prior 0.08 pv B2\n"
        "play B2"
    )

    move, selected, ranked = parse_genmove_analyze_details(response)

    assert move == "B2"
    assert selected["score_lead"] == pytest.approx(-2.25)
    assert selected["score_mean"] == pytest.approx(0.02)
    assert selected["score_selfplay"] == pytest.approx(1.75)
    assert selected["score_stdev"] == pytest.approx(2.5)
    assert selected["utility"] == pytest.approx(-0.1)
    assert selected["prior"] == pytest.approx(0.08)
    assert ranked[0]["move"] == "A1"
    # The original compatibility interface remains unchanged.
    legacy = parse_genmove_analyze(response)
    assert legacy[0] == "B2"
    assert legacy[1] == pytest.approx(57.0)
    assert legacy[2] == 120


@pytest.mark.parametrize("move", ["pass", "resign", "A0", "I1", "L1", "AA1"])
def test_engine_rejects_non_amazons_move_tokens(move):
    with pytest.raises(RuntimeError, match="禁止|非落子"):
        AmazonsKataGoEngine._require_playable_move(move, "测试")


def test_engine_accepts_only_10x10_coordinates():
    assert AmazonsKataGoEngine._require_playable_move("j10") == "J10"


def test_complete_amazons_position_command_contains_queens_obstacle_and_side():
    board = [[0 for _ in range(10)] for _ in range(10)]
    for point in ((0, 0), (0, 3), (3, 0), (3, 3)):
        board[point[0]][point[1]] = BLACK_AMAZON
    for point in ((6, 6), (6, 9), (9, 6), (9, 9)):
        board[point[0]][point[1]] = WHITE_AMAZON
    board[4][4] = OBSTACLE
    commands = []
    engine = SimpleNamespace(
        _convert_to_gtp_coord=lambda row, col: (
            AmazonsKataGoEngine._convert_to_gtp_coord(
                SimpleNamespace(), row, col)),
        _execute_sync_command=lambda command: commands.append(command),
        last_winrate=42.0,
        last_visits=10,
        last_score_lead=1.0,
        last_score_selfplay=2.0,
        last_score_stdev=3.0,
        last_utility=0.4,
        last_policy_prior=0.5,
    )

    AmazonsKataGoEngine.set_amazons_position(
        engine, board, WHITE_AMAZON)

    command = commands[0]
    assert command.startswith("set_amazons_position w ")
    assert "b A1" in command
    assert "b D4" in command
    assert "w G7" in command
    assert "w K10" in command
    assert "x E5" in command
    assert engine.last_winrate is None
    assert engine.last_policy_prior is None


@pytest.mark.parametrize("backend", ["gpu", "z", "legacy"])
def test_bundled_engine_configs_disable_resignation(backend):
    spec = BACKENDS[backend]
    for config_name in (spec["cfg"], spec["hint_cfg"]):
        path = Path(spec["dir"]) / config_name
        text = path.read_text(encoding="utf-8")
        assert "allowResignation = false" in text


class FakeTurnEngine:
    get_best_turn = AmazonsKataGoEngine.get_best_turn
    analyze_turn_stages = AmazonsKataGoEngine.analyze_turn_stages

    def __init__(self):
        self.generated = iter([
            ("A1", 60.0, 10),
            ("B2", 30.0, 20),
            ("C3", 65.0, 30),
        ])
        self.commands = []
        self.last_winrate = None
        self.last_visits = None

    def _genmove_analyze(self, _player):
        return next(self.generated)

    def _execute_sync_command(self, command):
        self.commands.append(command)
        return ""


def test_best_turn_always_restores_engine_position():
    engine = FakeTurnEngine()
    turn = engine.get_best_turn(BLACK_AMAZON)
    assert turn == ("A1", "B2", "C3")
    assert engine.commands[-3:] == ["undo", "undo", "undo"]
    assert engine.last_winrate == 60.0
    assert engine.last_score_lead is None
    assert engine.last_score_selfplay is None


def test_analyze_replaces_pass_with_most_visited_coordinate():
    commands = []
    response = (
        "info move pass visits 22 winrate 0 order 0 pv pass "
        "info move J4 visits 29 winrate 0.00667659 order 1 pv J4 pass\n"
        "play pass"
    )

    def execute(command):
        commands.append(command)
        return response if command.startswith("kata-genmove_analyze") else ""

    engine = SimpleNamespace(_execute_sync_command=execute)
    move, rate, visits = AmazonsKataGoEngine._genmove_analyze(engine, "w")

    assert move == "J4"
    assert rate == pytest.approx(0.667659)
    assert visits == 29
    assert commands == ["kata-genmove_analyze w", "undo", "play w J4"]


def test_three_stage_analysis_normalizes_move_to_original_player():
    engine = FakeTurnEngine()
    turn, rates, visits = engine.analyze_turn_stages(BLACK_AMAZON)
    assert turn == ("A1", "B2", "C3")
    assert rates == (60.0, 70.0, 65.0)
    assert visits == (10, 20, 30)
    assert engine.commands == ["undo", "undo", "undo"]


class FakeCandidateEngine:
    analyze_turn_for_start = AmazonsKataGoEngine.analyze_turn_for_start

    def __init__(self):
        self.generated = iter([("B2", 30.0, 20), ("C3", 65.0, 30)])
        self.commands = []

    def _genmove_analyze(self, _player):
        return next(self.generated)

    def _execute_sync_command(self, command):
        self.commands.append(command)
        return ""


def test_candidate_turn_restores_board_and_keeps_original_player_view():
    engine = FakeCandidateEngine()
    turn, rates, visits = engine.analyze_turn_for_start(BLACK_AMAZON, "A1", 60.0, 10)
    assert turn == ("A1", "B2", "C3")
    assert rates == (60.0, 70.0, 65.0)
    assert visits == (10, 20, 30)
    assert engine.commands == ["play b A1", "undo", "undo", "undo"]


def test_candidate_turn_reports_all_three_progress_stages():
    engine = FakeCandidateEngine()
    stages = []

    engine.analyze_turn_for_start(
        BLACK_AMAZON, "A1", 60.0, 10,
        progress_callback=lambda stage, rate, visits: stages.append(
            (stage, rate, visits)),
    )

    assert stages == [
        ("piece", 60.0, 10),
        ("move", 70.0, 20),
        ("arrow", 65.0, 30),
    ]


@pytest.mark.parametrize(
    ("gtp", "gui"),
    [("D10", "D1"), ("K7", "J4"), ("A1", "A10")],
)
def test_gtp_coordinate_is_converted_to_gui_labels(gtp, gui):
    engine = SimpleNamespace()
    engine._convert_coord = lambda coord: AmazonsKataGoEngine._convert_coord(
        engine, coord)
    assert AmazonsKataGoEngine.gtp_coord_to_gui(engine, gtp) == gui


def test_ranked_candidates_filter_pass_before_top_n_limit():
    commands = []
    response = (
        "info move pass visits 100 winrate 0 order 0 pv pass "
        "info move A1 visits 90 winrate 0.6 order 1 pv A1 "
        "info move B2 visits 80 winrate 0.5 order 2 pv B2 "
        "info move C3 visits 70 winrate 0.4 order 3 pv C3\n"
        "play pass"
    )
    engine = SimpleNamespace(
        _execute_sync_command=lambda command: (
            commands.append(command) or response),
    )

    candidates = AmazonsKataGoEngine.ranked_start_candidates(
        engine, BLACK_AMAZON, top_n=3)

    assert [move for move, _rate, _visits in candidates] == ["A1", "B2", "C3"]
    assert commands == ["kata-genmove_analyze b", "undo"]


def test_restore_skips_undo_after_engine_input_is_closed():
    commands = []
    engine = SimpleNamespace(
        process=SimpleNamespace(
            poll=lambda: None,
            stdin=SimpleNamespace(closed=True),
        ),
        _execute_sync_command=lambda command: commands.append(command),
    )

    AmazonsKataGoEngine._restore_temporary_moves(engine, 3)

    assert commands == []
