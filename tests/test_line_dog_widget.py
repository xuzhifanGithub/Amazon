from PyQt6.QtCore import QSettings

from src.gui.line_dog_widget import (
    LineDogWidget,
    PET_ACTION_KEYS,
    PET_ASSETS,
    PET_THEMES,
)


def test_pet_and_play_switch_real_gif_actions(qapp, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat)
    dogs = LineDogWidget(settings)
    monkeypatch.setattr(
        "src.gui.line_dog_widget.random.choice",
        lambda choices: "pet" if "pet" in choices else "chase",
    )

    assert dogs.canvas.movie_is_valid
    assert dogs.canvas._pose == "idle"
    assert dogs.canvas._movie.scaledSize().isEmpty()
    dogs.pet_button.click()
    assert dogs.affection == 1
    assert dogs.canvas._pose == "pet"
    assert dogs.canvas.movie_is_valid

    dogs.play_dogs()
    assert dogs.affection == 3
    assert dogs.canvas._pose == "chase"
    assert dogs.canvas.movie_is_valid

    dogs.show_sleeping()
    assert dogs.canvas._pose == "sleep"

    restored = LineDogWidget(QSettings(
        str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat))
    assert restored.affection == 3


def test_random_action_never_immediately_repeats(qapp, tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat)
    dogs = LineDogWidget(settings)
    selected = []
    monkeypatch.setattr(dogs, "_show_reaction", selected.append)
    monkeypatch.setattr("src.gui.line_dog_widget.random.choice", lambda choices: choices[0])

    dogs._show_random_action()
    first = selected[-1]
    dogs._show_random_action()
    second = selected[-1]

    assert first in PET_ACTION_KEYS
    assert second in PET_ACTION_KEYS
    assert first != second


def test_every_semantically_named_pet_gif_loads(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat)
    dogs = LineDogWidget(settings)

    for pose, filename in PET_ASSETS.items():
        dogs.canvas.set_pose(pose)
        assert dogs.canvas.movie_is_valid, filename


def test_all_themes_recolor_the_dog_scene(qapp, tmp_path):
    settings = QSettings(str(tmp_path / "dogs.ini"), QSettings.Format.IniFormat)
    dogs = LineDogWidget(settings)

    for scheme, theme in PET_THEMES.items():
        dogs.set_theme(scheme)
        assert dogs.canvas._theme == theme
