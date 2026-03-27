from PySide6.QtWidgets import QMessageBox

from frontend.ui.services.trade_safety import compose_live_trade_review_message


def _maybe_confirm_live_trade_submission(
    terminal,
    *,
    symbol,
    side,
    order_type,
    requested_amount,
    display_mode,
    preflight,
):
    controller = getattr(terminal, "controller", None)
    if controller is None or not bool(getattr(controller, "is_live_mode", lambda: False)()):
        return True

    broker = getattr(controller, "broker", None)
    exchange_name = str(getattr(broker, "exchange_name", "") or "").strip()
    account_label = str(getattr(controller, "current_account_label", lambda: "Not set")() or "Not set").strip()
    message = compose_live_trade_review_message(
        symbol=symbol,
        side=side,
        order_type=order_type,
        requested_amount=requested_amount,
        display_mode=display_mode,
        exchange_name=exchange_name,
        account_label=account_label,
        preflight=preflight,
    )
    reply = QMessageBox.question(
        terminal,
        "Live Pre-Trade Review",
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    confirmed = reply == QMessageBox.StandardButton.Yes
    if not confirmed and hasattr(terminal, "_push_notification"):
        terminal._push_notification(
            "Live order canceled",
            f"Operator canceled the live {str(order_type or 'market').upper()} order for {symbol}.",
            level="WARN",
            source="trade",
            dedupe_seconds=2.0,
        )
    return confirmed


async def submit_manual_trade(
    terminal,
    *,
    symbol,
    side,
    amount,
    requested_amount=None,
    quantity_mode="units",
    order_type="market",
    price=None,
    stop_price=None,
    stop_loss=None,
    take_profit=None,
):
    controller = getattr(terminal, "controller", None)
    if controller is None:
        raise RuntimeError("Manual trading is unavailable because the controller is missing.")

    requested_display_amount = requested_amount if requested_amount is not None else amount
    display_mode = terminal._normalize_manual_trade_quantity_mode(quantity_mode)
    try:
        preflight = await controller.preview_trade_submission(
            symbol=symbol,
            side=side,
            amount=requested_display_amount,
            quantity_mode=quantity_mode,
            order_type=order_type,
            price=price,
            stop_price=stop_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source="manual",
            timeframe=str(getattr(terminal, "current_timeframe", "") or ""),
        )
        if not _maybe_confirm_live_trade_submission(
            terminal,
            symbol=str(preflight.get("symbol") or symbol).strip().upper(),
            side=side,
            order_type=order_type,
            requested_amount=requested_display_amount,
            display_mode=display_mode,
            preflight=preflight,
        ):
            if hasattr(controller, "queue_trade_audit"):
                controller.queue_trade_audit(
                    "submit_canceled",
                    status="canceled",
                    symbol=str(preflight.get("symbol") or symbol).strip().upper(),
                    requested_symbol=str(symbol or "").strip().upper(),
                    side=side,
                    order_type=order_type,
                    source="manual",
                    requested_amount=requested_display_amount,
                    payload={"preflight": dict(preflight)},
                    message="Operator canceled the live pre-trade review dialog.",
                )
            terminal.system_console.log(
                f"Manual live order canceled before submission: {side.upper()} {requested_display_amount} {display_mode} {symbol}",
                "WARN",
            )
            return None

        order = await controller.submit_trade_with_preflight(
            symbol=symbol,
            side=side,
            amount=requested_display_amount,
            quantity_mode=quantity_mode,
            order_type=order_type,
            price=price,
            stop_price=stop_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source="manual",
            strategy_name="Manual",
            reason="Manual order",
            preflight=preflight,
            timeframe=str(getattr(terminal, "current_timeframe", "") or ""),
        )
        status_text = str(order.get("status") or "submitted").replace("_", " ").upper()
        display_amount = order.get(
            "applied_requested_mode_amount",
            requested_display_amount,
        )
        requested_display_amount = order.get(
            "requested_amount",
            requested_display_amount,
        )
        sizing_summary = str(order.get("sizing_summary") or "").strip()
        ai_sizing_reason = str(order.get("ai_sizing_reason") or "").strip()
        requested_suffix = (
            f" | requested {requested_display_amount} {display_mode}"
            if bool(order.get("size_adjusted"))
            else ""
        )
        sizing_suffix = f" | {sizing_summary}" if sizing_summary else ""
        ai_suffix = f" | ChatGPT size note: {ai_sizing_reason}" if ai_sizing_reason else ""
        terminal.system_console.log(
            (
                f"Manual order {status_text}: {side.upper()} {display_amount} {display_mode} "
                f"{symbol} ({order_type}){requested_suffix}{sizing_suffix}{ai_suffix}"
            ),
            "INFO",
        )
        message = f"{status_text.title()} {side.upper()} {display_amount} {display_mode} {symbol}."
        if bool(order.get("size_adjusted")):
            message += f"\nRequested: {requested_display_amount} {display_mode}"
        if sizing_summary:
            message += f"\nSizing: {sizing_summary}"
        if ai_sizing_reason:
            message += f"\nChatGPT size note: {ai_sizing_reason}"
        terminal._show_async_message(
            "Manual Order",
            message,
            QMessageBox.Icon.Information,
        )
        return order
    except Exception:
        raise
