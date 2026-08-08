from datetime import date

from PyQt6.QtCore import QSettings

from src.gui.line_dog_widget import LineDogWidget, PET_THEMES


def test_pet_and_feed_are_independent_local_interactions(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat)
    dogs = LineDogWidget(settings)

    assert not dogs.canvas._artwork.isNull()
    dogs.pet_button.click()
    assert dogs.affection == 1
    assert dogs.canvas._pose == "pet"

    dogs.feed_button.click()
    assert dogs.affection == 3
    assert dogs.snacks == 2
    assert "2" in dogs.feed_button.text()

    restored = LineDogWidget(QSettings(
        str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat))
    assert restored.affection == 3
    assert restored.snacks == 2


def test_snacks_reset_on_a_new_day(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat)
    settings.setValue("pets/snack_date", "2000-01-01")
    settings.setValue("pets/snacks", 0)

    dogs = LineDogWidget(settings)

    assert dogs.snack_date == date.today().isoformat()
    assert dogs.snacks == 3
    assert dogs.feed_button.isEnabled()


def test_all_themes_recolor_the_dog_scene(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat)
    dogs = LineDogWidget(settings)

    for scheme, theme in PET_THEMES.items():
        dogs.set_theme(scheme)
        assert dogs.canvas._theme == theme
