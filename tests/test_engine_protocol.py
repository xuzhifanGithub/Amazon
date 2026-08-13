import pytest
from types import SimpleNamespace
from pathlib import Path

from src.ai.amazons_engine import BACKENDS, AmazonsKataGoEngine, parse_genmove_analyze
from src.core.simulator import BLACK_AMAZON


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


@pytest.mark.parametrize("move", ["pass", "resign", "A0", "I1", "L1", "AA1"])
def test_engine_rejects_non_amazons_move_tokens(move):
    with pytest.raises(RuntimeError, match="禁止|非落子"):
        AmazonsKataGoEngine._require_playable_move(move, "测试")


def test_engine_accepts_only_10x10_coordinates():
    assert AmazonsKataGoEngine._require_playable_move("j10") == "J10"


@pytest.mark.parametrize("backend", ["gpu", "legacy"])
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
        if command.startswith("genmove"):
            return "B2" if len([c for c in self.commands if c.startswith('genmove')]) == 1 else "C3"
        return ""


def test_best_turn_always_restores_engine_position():
    engine = FakeTurnEngine()
    turn = engine.get_best_turn(BLACK_AMAZON)
    assert turn == ("A1", "B2", "C3")
    assert engine.commands[-3:] == ["undo", "undo", "undo"]
    assert engine.last_winrate == 60.0


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
