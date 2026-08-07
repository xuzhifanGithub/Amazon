from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings

from src.ai.ai_profile import AIProfile, load_profile, save_profile
from src.ai.amazons_engine import BACKENDS, profile_config_for_visits
from src.ai.engine_manager import EngineManager
from src.core.game_record import export_record, load_record
from src.core.simulator import AmazonsSimulator


OPENING_TURN = ((6, 0), (5, 0), (6, 0))


def test_profiles_are_clamped_and_persisted(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    saved = save_profile(settings, "black", AIProfile(99, 1))
    assert saved == AIProfile(10.0, 100)
    assert load_profile(settings, "black") == saved


def test_visits_profile_config_does_not_mutate_bundled_file():
    source = Path(BACKENDS['gpu']['dir']) / BACKENDS['gpu']['cfg']
    before = source.read_text(encoding='utf-8')
    generated = Path(profile_config_for_visits('gpu', 750))
    assert "maxVisits = 750" in generated.read_text(encoding='utf-8')
    assert source.read_text(encoding='utf-8') == before


def test_visits_profile_cache_changes_when_base_config_changes(tmp_path, monkeypatch):
    source = tmp_path / "engine.cfg"
    source.write_text("maxVisits = 600\nfoo = one\n", encoding="utf-8")
    monkeypatch.setitem(BACKENDS, "test", {
        "dir": str(tmp_path),
        "cfg": "engine.cfg",
    })

    first = Path(profile_config_for_visits("test", 750))
    source.write_text("maxVisits = 600\nfoo = two\n", encoding="utf-8")
    second = Path(profile_config_for_visits("test", 750))

    assert first != second
    assert "foo = one" in first.read_text(encoding="utf-8")
    assert "foo = two" in second.read_text(encoding="utf-8")


def test_game_record_round_trip_and_invalid_import_is_atomic(tmp_path):
    original = AmazonsSimulator()
    assert original.execute_turn(*OPENING_TURN)
    record = tmp_path / "game.amazons.json"
    export_record(str(record), original)

    restored = AmazonsSimulator()
    turns = load_record(str(record), restored)
    restored.load_turns(turns)
    assert restored.history_do_chess == original.history_do_chess

    invalid = tmp_path / "bad.amazons.json"
    invalid.write_text('{"format":"amazons","version":1,"board_size":10,"turns":[[]]}', encoding='utf-8')
    before = restored.board.copy()
    with pytest.raises(ValueError):
        load_record(str(invalid), restored)
    assert (restored.board == before).all()


def test_engine_manager_reuses_same_profile_and_closes_all():
    created = []

    class FakeEngine:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False

        def close(self):
            self.closed = True

    def factory(**kwargs):
        engine = FakeEngine(**kwargs)
        created.append(engine)
        return engine

    played = []
    manager = EngineManager(factory)
    first = manager.get_game_engine('gpu', 600, [OPENING_TURN],
                                    lambda engine, player, *turn: played.append((engine, player, turn)))
    assert manager.get_game_engine('gpu', 600, [], lambda *_: None) is first
    second = manager.get_game_engine('gpu', 800, [], lambda *_: None)
    assert first is not second
    assert played[0][1:] == (1, OPENING_TURN)
    manager.close_all()
    assert all(engine.closed for engine in created)
