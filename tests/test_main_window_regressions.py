from unittest.mock import Mock

from PyQt6.QtWidgets import QFrame

from src.ai.results import AIOutcome, HintCandidate, HintOutcome
from src.core.simulator import AmazonsSimulator, BLACK_AMAZON
from src.gui.ai_info_panel import PANEL_THEMES
from src.gui.amazon_main_window import AmazonsMainWindow


OPENING_TURN = ((6, 0), (5, 0), (6, 0))


def test_committed_turn_is_broadcast_only_after_validation(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.black_ai_agent.sync_committed_turn = Mock()
    window.white_ai_agent.sync_committed_turn = Mock()

    result = window.post_animation_update(*OPENING_TURN)

    assert result == 'HUMAN_TURN'
    assert len(window.simulator.history_do_chess) == 1
    window.black_ai_agent.sync_committed_turn.assert_called_once_with(
        BLACK_AMAZON, *OPENING_TURN)
    window.white_ai_agent.sync_committed_turn.assert_called_once_with(
        BLACK_AMAZON, *OPENING_TURN)
    window.close()


def test_invalid_turn_is_not_sent_to_engines(qapp, monkeypatch):
    monkeypatch.setattr(
        "src.gui.amazon_main_window.QMessageBox.warning", lambda *args, **kwargs: None)
    window = AmazonsMainWindow(AmazonsSimulator())
    window.black_ai_agent.sync_committed_turn = Mock()
    window.white_ai_agent.sync_committed_turn = Mock()

    result = window.post_animation_update((6, 0), (6, 1), (6, 1))

    assert result == 'MOVE_FAILED'
    window.black_ai_agent.sync_committed_turn.assert_not_called()
    window.white_ai_agent.sync_committed_turn.assert_not_called()
    window.close()


def test_stale_hint_result_is_ignored(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.show_hints_action.setChecked(True)
    window._hint_request_id = 5
    window.board_widget.set_hints = Mock()

    window._handle_hint_outcome(HintOutcome(request_id=4, candidates=((60, 50.0),)))

    window.board_widget.set_hints.assert_not_called()
    window.close()


def test_ai_failure_returns_control_to_human(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.black_modes = window.PLAYER_TYPE_AI_MCTS
    window._active_ai_request = (window.game_generation, BLACK_AMAZON, 'mcts')

    window.execute_ai_move(AIOutcome.failure("boom"), BLACK_AMAZON)

    assert window.black_modes == window.PLAYER_TYPE_HUMAN
    assert window.board_widget.isEnabled()
    assert "boom" in window.statusBar().currentMessage()
    window.close()


def test_info_panel_uses_three_cards_and_updates_rates(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())

    assert window.info_panel.width() == 280
    assert window.info_panel.findChild(QFrame, "statusCard")
    assert window.info_panel.findChild(QFrame, "winRateCard")
    assert window.info_panel.findChild(QFrame, "analysisCard")

    window.update_win_rate_display(53.4, BLACK_AMAZON)
    assert window.win_rate_label.text() == "53.4%"
    assert window.info_panel.win_rate_bar.value() == 53
    assert "黑方" in window.info_panel.win_rate_context.text()

    window.update_win_rate_display(None)
    assert window.win_rate_label.text() == "—"
    assert window.info_panel.win_rate_bar.value() == 0
    window.close()


def test_info_panel_theme_changes_are_visible(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    for scheme, colors in PANEL_THEMES.items():
        window.set_color_scheme(scheme)
        assert colors["accent"] in window.info_panel.styleSheet()
    window.close()


def test_top_n_hint_candidates_fill_board_and_info_card(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.show_hints_action.setChecked(True)
    window._hint_request_id = 8
    candidates = (
        HintCandidate(60, 50, 40, (62.0, 58.0, 64.0), (100, 90, 80)),
        HintCandidate(69, 59, 49, (55.0, 54.0, 56.0), (95, 85, 75)),
    )
    window._handle_hint_outcome(HintOutcome(
        request_id=8, candidates=candidates, best_turn=(60, 50, 40),
        stage_win_rates=candidates[0].stage_win_rates))
    assert len(window.board_widget.hint_moves) == 2
    assert "1." in window.info_panel.info_candidates.text()
    assert "2." in window.info_panel.info_candidates.text()
    window.close()
