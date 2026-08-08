from unittest.mock import Mock

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QFrame

from src.ai.results import AIOutcome, BestResult, HintCandidate, HintOutcome
from src.core.game_record import export_record
from src.core.game_session import SessionState
from src.core.simulator import AmazonsSimulator, BLACK_AMAZON
from src.gui.ai_info_panel import PANEL_THEMES
from src.gui.amazon_main_window import AmazonsMainWindow


OPENING_TURN = ((6, 0), (5, 0), (6, 0))


def test_only_one_cpp_mcts_option_is_exposed(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    action_texts = [action.text() for action in window.findChildren(QAction)]

    assert action_texts.count("MCTS★") == 2  # 黑方、白方各一个入口
    window.close()


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


def test_full_turn_win_rate_is_disabled_on_every_start(qapp):
    previous_window = AmazonsMainWindow(AmazonsSimulator())
    previous_window.settings.setValue("hints/enabled", True)
    previous_window.settings.sync()
    previous_window.close()

    window = AmazonsMainWindow(AmazonsSimulator())

    assert not window.show_hints_action.isChecked()
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


def test_out_of_range_ai_move_returns_control_to_human(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.black_modes = window.PLAYER_TYPE_AI_MCTS
    window.board_widget.setEnabled(False)
    window.session.begin_ai()
    window._active_ai_request = (window.game_generation, BLACK_AMAZON, 'mcts')

    window.execute_ai_move(
        AIOutcome.success(BestResult(100, 1, 2)), BLACK_AMAZON)

    assert window.black_modes == window.PLAYER_TYPE_HUMAN
    assert window.board_widget.isEnabled()
    assert window.session.state is SessionState.IDLE
    window.close()


def test_switching_pending_ai_to_human_unlocks_board(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.black_modes = window.PLAYER_TYPE_AI_MCTS
    window._ai_turn_pending = True
    window.session.begin_ai()
    window.board_widget.setEnabled(False)

    window.set_player_mode(BLACK_AMAZON, window.PLAYER_TYPE_HUMAN)

    assert not window._ai_turn_pending
    assert window.board_widget.isEnabled()
    assert window.session.state is SessionState.IDLE
    window.close()


def test_import_resumes_configured_ai_side(qapp, tmp_path, monkeypatch):
    record = tmp_path / "game.amazons.json"
    export_record(str(record), AmazonsSimulator())
    monkeypatch.setattr(
        "src.gui.amazon_main_window.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(record), ""))

    window = AmazonsMainWindow(AmazonsSimulator())
    window.black_modes = window.PLAYER_TYPE_AI_MCTS
    window.update_win_rate_display(81.2, BLACK_AMAZON)
    window.update_ai_info_panel(
        BestResult(60, 50, 40, 81.2, 600, 0.812),
        BLACK_AMAZON,
        "kataAmazon_gpu",
    )
    window.start_ai_turn = Mock()

    window.import_game_record()

    window.start_ai_turn.assert_called_once_with()
    assert window.win_rate_label.text() == "—"
    assert window.info_ai_model.text() == "模型：—"
    window.close()


def test_opening_undo_keeps_active_ai_request_alive(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.black_modes = window.PLAYER_TYPE_AI_KATAAMAZON_GPU
    request = (window.game_generation, BLACK_AMAZON, "kataAmazon_gpu")
    window._active_ai_request = request
    window.session.begin_ai()
    window.board_widget.setEnabled(False)

    window.undo_move()

    assert window._active_ai_request == request
    assert window.session.state is SessionState.AI_THINKING
    assert not window.board_widget.isEnabled()
    window.close()


def test_undo_to_human_unlocks_board_and_clears_old_analysis(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    assert window.simulator.execute_turn(*OPENING_TURN)
    window.white_modes = window.PLAYER_TYPE_AI_MCTS
    window.board_widget.setEnabled(False)
    window.update_win_rate_display(73.5, BLACK_AMAZON)
    window.update_ai_info_panel(
        BestResult(60, 50, 40, 73.5, 600, 0.735),
        BLACK_AMAZON,
        "kataAmazon_gpu",
    )

    window.undo_move()

    assert not window.simulator.history_do_chess
    assert window.board_widget.isEnabled()
    assert window.session.state is SessionState.IDLE
    assert window.win_rate_label.text() == "—"
    assert window.info_ai_model.text() == "模型：—"
    window.close()


def test_busy_worker_uses_completion_signal_instead_of_retry_timer(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.black_modes = window.PLAYER_TYPE_AI_MCTS
    window.black_ai_agent.start_thread_ai_calculation = Mock(return_value=False)
    window.start_ai_turn = Mock()

    window.start_ai_calculation(window.game_generation, BLACK_AMAZON)

    assert window._resume_ai_after_worker
    assert not window.board_widget.isEnabled()
    window.start_ai_turn.assert_not_called()
    window.close()


def test_game_over_status_names_winner(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.simulator.game_over = True
    window.simulator.winner = BLACK_AMAZON

    window.update_status()

    assert window.status_label.text() == "游戏结束：黑方获胜"
    window.close()


def test_zoom_shortcuts_step_between_adjacent_levels(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.set_board_zoom(100)

    window.zoom_in_action.trigger()
    assert window.board_zoom == 120
    window.zoom_in_action.trigger()
    assert window.board_zoom == 140
    window.zoom_out_action.trigger()
    assert window.board_zoom == 120
    assert window.zoom_actions[120].isChecked()
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


def test_hint_progress_is_shown_in_right_panel(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.show_hints_action.setChecked(True)
    window._hint_request_id = 12

    window._handle_hint_progress({
        "request_id": 12,
        "text": "候选 1/3：正在分析移动…",
        "progress": 42,
    })

    assert window.info_panel.task_status_label.isVisibleTo(window.info_panel)
    assert "候选 1/3" in window.info_panel.task_status_label.text()
    assert window.info_panel.task_progress_bar.value() == 42

    window._handle_hint_progress({
        "request_id": 11,
        "text": "过期任务",
        "progress": 99,
    })
    assert "过期任务" not in window.info_panel.task_status_label.text()
    window.close()


def test_top_n_hint_candidates_keep_only_highest_rate_on_board(qapp):
    window = AmazonsMainWindow(AmazonsSimulator())
    window.show_hints_action.setChecked(True)
    window._hint_request_id = 8
    candidates = (
        HintCandidate(60, 50, 40, (62.0, 58.0, 64.0), (100, 90, 80)),
        HintCandidate(69, 59, 49, (71.0, 66.0, 72.0), (95, 85, 75)),
    )
    window._handle_hint_outcome(HintOutcome(
        request_id=8, candidates=candidates, best_turn=(60, 50, 40),
        stage_win_rates=candidates[0].stage_win_rates))
    assert len(window.board_widget.hint_moves) == 1
    assert window.board_widget.hint_moves[0][:2] == (6, 9)
    assert window.board_widget.hint_best_turn == (69, 59, 49)
    assert "1." in window.info_panel.info_candidates.text()
    assert "2." in window.info_panel.info_candidates.text()
    window.close()
