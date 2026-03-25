import os
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QMainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.terminal import Terminal


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FakeTerminal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = SimpleNamespace(language_code="en", set_language=lambda _code: None)
        self.show_bid_ask_lines = True
        self.current_connection_status = "connecting"
        self.language_actions = {}
        self.timeframe_buttons = {}
        self.autotrading_enabled = False
        self.connection_indicator = None
        self.symbol_label = None
        self.open_symbol_button = None
        self.screenshot_button = None
        self.system_status_button = None
        self.kill_switch_button = None
        self.session_mode_badge = None
        self.license_badge = None
        self.trading_activity_label = None

    def _tr(self, key, **kwargs):
        return key

    def apply_language(self):
        return Terminal.apply_language(self)

    def _update_autotrade_button(self):
        return None

    def _set_active_timeframe_button(self, _timeframe):
        return None

    def __getattr__(self, name):
        if name.startswith("_"):
            return lambda *args, **kwargs: None
        raise AttributeError(name)


def test_create_menu_bar_groups_actions_into_single_clear_menus():
    _app()
    terminal = _FakeTerminal()

    Terminal._create_menu_bar(terminal)

    file_actions = terminal.file_menu.actions()
    strategy_actions = terminal.strategy_menu.actions()
    backtest_actions = terminal.backtest_menu.actions()
    risk_actions = terminal.risk_menu.actions()
    review_actions = terminal.review_menu.actions()
    research_actions = terminal.research_menu.actions()
    tools_actions = terminal.tools_menu.actions()
    settings_actions = terminal.settings_menu.actions()

    assert terminal.settings_menu.menuAction() in file_actions
    assert terminal.action_exit in file_actions
    assert terminal.action_generate_report not in file_actions
    assert terminal.action_export_trades not in file_actions

    assert terminal.action_app_settings in settings_actions
    assert terminal.language_menu.menuAction() in settings_actions

    assert terminal.backtest_menu.menuAction() in strategy_actions
    assert terminal.action_strategy_assigner in strategy_actions
    assert terminal.action_strategy_scorecard in strategy_actions
    assert terminal.action_strategy_debug in strategy_actions
    assert terminal.action_run_backtest in backtest_actions
    assert terminal.action_strategy_optimization in backtest_actions

    assert terminal.action_risk_settings in risk_actions
    assert terminal.action_portfolio_view in risk_actions
    assert terminal.action_position_analysis in risk_actions
    assert terminal.action_trade_checklist in risk_actions
    assert terminal.action_system_health in risk_actions
    assert terminal.action_kill_switch not in risk_actions

    assert terminal.action_performance in review_actions
    assert terminal.action_recommendations in review_actions
    assert terminal.action_closed_journal in review_actions
    assert terminal.action_journal_review in review_actions
    assert terminal.action_generate_report in review_actions
    assert terminal.action_export_trades in review_actions

    assert terminal.action_market_chat in research_actions
    assert terminal.action_quant_pm in research_actions
    assert terminal.action_ml_monitor in research_actions
    assert terminal.action_ml_research in research_actions
    assert terminal.action_stellar_asset_explorer in research_actions
    assert terminal.action_recommendations not in research_actions
    assert terminal.action_strategy_optimization not in research_actions
    assert terminal.action_strategy_assigner not in research_actions
    assert terminal.action_run_backtest not in research_actions

    assert terminal.action_logs in tools_actions
    assert terminal.action_system_console in tools_actions
    assert terminal.action_system_status in tools_actions
    assert terminal.action_market_chat not in tools_actions
    assert terminal.action_performance not in tools_actions
