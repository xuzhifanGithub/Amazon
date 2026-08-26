from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings

from src.ai.ai_profile import (
    AIProfile, KataSearchConfig, SEARCH_CONFIG_CUSTOM,
    SEARCH_CONFIG_STRONGEST, STRONGEST_KATA_SEARCH_CONFIG,
    load_profile, save_profile,
)
from src.ai.amazons_engine import (
    BACKENDS, profile_config_for_visits, resolve_engine_resources,
)
from src.ai.engine_manager import EngineManager
from src.core.game_record import export_record, load_record
from src.core.simulator import AmazonsSimulator
from src.gui.ai_settings_dialog import AISettingsDialog


OPENING_TURN = ((6, 0), (5, 0), (6, 0))


def test_legacy_backend_reads_a_replaceable_external_model():
    spec = BACKENDS["legacy"]
    model = (Path(spec["dir"]) / spec["model"]).resolve()

    assert spec["exe"] == "amazons.exe"
    assert Path(spec["dir"]).name == "kataAmazonEngineCuda"
    assert model.name == "amazons10x10.bin.gz"
    assert model.parent.name == "weights"


def test_profiles_are_clamped_and_persisted(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    saved = save_profile(settings, "black", AIProfile(99, 1, False))
    assert saved == AIProfile(10.0, 100, False)
    assert load_profile(settings, "black") == saved

    strongest = save_profile(
        settings,
        "white",
        AIProfile(8, 1800, True, SEARCH_CONFIG_STRONGEST),
    )
    assert strongest == AIProfile(
        1.0,
        600,
        False,
        SEARCH_CONFIG_STRONGEST,
        0.0,
        0.0,
        1.0,
        1.0,
        0.45,
        500,
        False,
        False,
        0.0,
        1,
        False,
    )
    assert load_profile(settings, "white") == strongest


def test_score_utility_defaults_off_and_dialog_edits_each_side(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "defaults.ini"), QSettings.Format.IniFormat)
    assert load_profile(settings, "black").score_utility_enabled is False

    dialog = AISettingsDialog(
        AIProfile(score_utility_enabled=False),
        AIProfile(score_utility_enabled=True),
    )
    assert not dialog.black_controls["score_utility"].isChecked()
    assert dialog.white_controls["score_utility"].isChecked()
    assert dialog.profiles()[0].score_utility_enabled is False

    dialog.restore_defaults()
    assert dialog.profiles()[0].score_utility_enabled is False
    assert dialog.profiles()[1].score_utility_enabled is False
    dialog.close()


def test_ai_settings_strength_presets_apply_complete_profiles(qapp):
    dialog = AISettingsDialog(AIProfile(), AIProfile())
    strongest = dialog.black_controls["mode"]
    strongest.setCurrentIndex(
        strongest.findData(AISettingsDialog.PRESET_STRONGEST))

    black = dialog.profiles()[0]
    assert black.mcts_seconds == 1.0
    assert black.kata_visits == 600
    assert black.score_utility_enabled is False
    assert black.search_config_mode == SEARCH_CONFIG_STRONGEST
    assert black.kata_search_config() == STRONGEST_KATA_SEARCH_CONFIG
    assert black.nn_randomize is False

    # Editing a preset value makes the profile explicitly custom instead of
    # continuing to claim that a reduced search budget is the strongest one.
    dialog.black_controls["visits"].setValue(1500)
    assert strongest.currentData() == AISettingsDialog.PRESET_CUSTOM

    dialog.black_controls["move_temperature"].setValue(0.35)
    custom = dialog.profiles()[0]
    assert custom.search_config_mode == SEARCH_CONFIG_CUSTOM
    assert custom.move_temperature == 0.35
    assert custom.nn_randomize is False

    dialog.restore_defaults()
    assert dialog.profiles()[0] == AIProfile(1.0, 600, False)
    assert dialog.profiles()[1] == AIProfile(1.0, 600, False)
    dialog.close()


def test_ai_settings_explains_advanced_parameters_and_reference_values(qapp):
    dialog = AISettingsDialog(AIProfile(), AIProfile())
    help_text = dialog.parameter_help.toPlainText()

    for phrase in (
        "前期 / 后期落子温度",
        "网络策略温度",
        "网络方向随机化",
        "cpuct 探索系数",
        "搜索线程数",
        "根节点噪声",
        "0.8–1.2",
        "比赛 0–0.01",
    ):
        assert phrase in help_text
    assert "参考 0.8–1.2" in dialog.black_controls[
        "cpuct_exploration"].toolTip()
    assert "正式评测" in dialog.black_controls["use_graph_search"].toolTip()
    assert "随机旋转或镜像" in dialog.black_controls["nn_randomize"].toolTip()
    dialog.close()


def test_visits_profile_config_does_not_mutate_bundled_file():
    source = Path(BACKENDS['gpu']['dir']) / BACKENDS['gpu']['cfg']
    before = source.read_text(encoding='utf-8')
    generated = Path(profile_config_for_visits('gpu', 750))
    assert "maxVisits = 750" in generated.read_text(encoding='utf-8')
    assert source.read_text(encoding='utf-8') == before


def test_score_utility_switch_generates_distinct_configs_without_mutating_source():
    source = Path(BACKENDS['gpu']['dir']) / BACKENDS['gpu']['cfg']
    before = source.read_text(encoding='utf-8')

    enabled = Path(profile_config_for_visits('gpu', 600, True))
    disabled = Path(profile_config_for_visits('gpu', 600, False))

    assert enabled != disabled
    assert "dynamicScoreUtilityFactor = 0.02" in enabled.read_text(encoding='utf-8')
    assert "dynamicScoreUtilityFactor = 0.0" in disabled.read_text(encoding='utf-8')
    assert source.read_text(encoding='utf-8') == before


@pytest.mark.parametrize("backend", ["gpu", "legacy"])
def test_strongest_profile_generates_competitive_config_at_normal_budget(backend):
    strongest = Path(profile_config_for_visits(
        backend, 600, False, STRONGEST_KATA_SEARCH_CONFIG))
    config = strongest.read_text(encoding="utf-8")

    assert "maxVisits = 600" in config
    assert "chosenMoveTemperatureEarly = 0.0" in config
    assert "chosenMoveTemperature = 0.0" in config
    assert "rootNoiseEnabled = false" in config
    assert "nnPolicyTemperature = 1.0" in config
    assert "cpuctExploration = 1.0" in config
    assert "cpuctExplorationLog = 0.45" in config
    assert "useGraphSearch = false" in config
    assert "subtreeValueBiasFactor = 0.0" in config
    assert "dynamicScoreUtilityFactor = 0.0" in config
    assert "numSearchThreads = 1" in config
    assert "nnRandomize = false" in config


def test_custom_search_parameters_are_written_to_generated_config():
    custom = KataSearchConfig(
        move_temperature_early=0.7,
        move_temperature=0.25,
        policy_temperature=1.2,
        cpuct_exploration=1.15,
        cpuct_exploration_log=0.3,
        cpuct_exploration_base=750,
        use_graph_search=True,
        root_noise_enabled=True,
        subtree_value_bias_factor=0.2,
        num_search_threads=6,
        nn_randomize=True,
    )
    config = Path(profile_config_for_visits(
        "gpu", 850, False, custom)).read_text(encoding="utf-8")

    assert "maxVisits = 850" in config
    assert "chosenMoveTemperatureEarly = 0.7" in config
    assert "chosenMoveTemperature = 0.25" in config
    assert "nnPolicyTemperature = 1.2" in config
    assert "cpuctExploration = 1.15" in config
    assert "cpuctExplorationLog = 0.3" in config
    assert "cpuctExplorationBase = 750" in config
    assert "useGraphSearch = true" in config
    assert "rootNoiseEnabled = true" in config
    assert "subtreeValueBiasFactor = 0.2" in config
    assert "numSearchThreads = 6" in config
    assert "nnRandomize = true" in config


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


def test_runtime_engine_resources_ignore_machine_environment(monkeypatch):
    monkeypatch.setenv("KATA_AMAZON_DIR", "Z:/external-engine")
    monkeypatch.setenv("KATA_AMAZON_EXE", "external.exe")
    monkeypatch.setenv("KATA_AMAZON_MODEL", "external.bin.gz")
    monkeypatch.setenv("KATA_AMAZON_CFG", "external.cfg")

    directory, executable, model, config = resolve_engine_resources("gpu")

    assert Path(directory) == Path(BACKENDS["gpu"]["dir"]).resolve()
    assert executable == BACKENDS["gpu"]["exe"]
    assert model == BACKENDS["gpu"]["model"]
    assert config == BACKENDS["gpu"]["cfg"]


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
    assert not manager.has_game_engine('gpu', 600)
    first = manager.get_game_engine('gpu', 600, [OPENING_TURN],
                                    lambda engine, player, *turn: played.append((engine, player, turn)))
    assert manager.has_game_engine('gpu', 600)
    assert not manager.has_game_engine('gpu', 800)
    assert manager.get_game_engine('gpu', 600, [], lambda *_: None) is first
    second = manager.get_game_engine('gpu', 800, [], lambda *_: None)
    assert first is not second
    assert played[0][1:] == (1, OPENING_TURN)
    manager.close_all()
    assert not manager.has_game_engine('gpu', 600)
    assert all(engine.closed for engine in created)


def test_engine_manager_isolates_score_utility_profiles():
    created = []

    class FakeEngine:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def close(self):
            pass

    def factory(**kwargs):
        engine = FakeEngine(**kwargs)
        created.append(engine)
        return engine

    manager = EngineManager(factory)
    enabled = manager.get_game_engine(
        'gpu', 600, (), lambda *_: None, score_utility_enabled=True)
    disabled = manager.get_game_engine(
        'gpu', 600, (), lambda *_: None, score_utility_enabled=False)

    assert enabled is not disabled
    assert enabled.kwargs['score_utility_enabled'] is True
    assert disabled.kwargs['score_utility_enabled'] is False
    assert manager.has_game_engine(
        'gpu', 600, score_utility_enabled=True)
    assert manager.has_game_engine(
        'gpu', 600, score_utility_enabled=False)
    manager.close_all()


def test_engine_manager_isolates_strongest_search_configuration():
    class FakeEngine:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def close(self):
            pass

    manager = EngineManager(FakeEngine)
    normal = manager.get_game_engine('gpu', 600, (), lambda *_: None)
    strongest = manager.get_game_engine(
        'gpu', 600, (), lambda *_: None,
        search_config=STRONGEST_KATA_SEARCH_CONFIG)

    assert strongest is not normal
    assert strongest.kwargs['search_config'] == STRONGEST_KATA_SEARCH_CONFIG
    assert manager.has_game_engine(
        'gpu', 600, search_config=STRONGEST_KATA_SEARCH_CONFIG)
    manager.close_all()
