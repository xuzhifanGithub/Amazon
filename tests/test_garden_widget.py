from PyQt6.QtCore import QSettings

from src.gui.garden_widget import GardenState, GardenWidget, STAGE_NAMES


def test_garden_state_rewards_and_grows_through_four_stages():
    state = GardenState()

    assert state.stage == 0
    for expected_stage in (1, 1, 2, 2, 2, 3):
        state.reward_game()
        assert state.water()
        assert state.stage == expected_stage

    assert state.fully_grown
    assert not state.water()
    assert state.completed_games == 6


def test_garden_widget_persists_water_and_growth(qapp, tmp_path):
    path = tmp_path / "garden.ini"
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    garden = GardenWidget(settings)

    garden.reward_completed_game()
    assert garden.state.water_drops == 1
    assert garden.water_button.isEnabled()
    garden.water_button.click()
    assert garden.state.stage == 1
    assert garden.stage_label.text() == STAGE_NAMES[1]

    restored = GardenWidget(QSettings(str(path), QSettings.Format.IniFormat))
    assert restored.state.growth == 1
    assert restored.state.completed_games == 1
    assert restored.state.water_drops == 0


def test_garden_ai_activity_animates_and_reports_progress(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "garden.ini"), QSettings.Format.IniFormat)
    garden = GardenWidget(settings)

    garden.set_ai_activity(True, "胜率分析中", 42)
    assert garden.canvas._timer.isActive()
    assert "42%" in garden.activity_label.text()

    garden.set_ai_activity(False, "胜率分析完成")
    assert not garden.canvas._timer.isActive()
    assert garden.activity_label.text() == "胜率分析完成"
