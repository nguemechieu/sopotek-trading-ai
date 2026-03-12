import asyncio
import json
import os
from datetime import datetime
import re
import uuid

import aiohttp


class TelegramService:
    def __init__(self, controller, logger, bot_token, chat_id=None, enabled=False):
        self.controller = controller
        self.logger = logger
        self.bot_token = str(bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.enabled = bool(enabled and self.bot_token)
        self._offset = 0
        self._poll_task = None
        self._session = None
        self._running = False
        self._chat_histories = {}
        self._pending_trade_actions = {}

    @property
    def base_url(self):
        return f"https://api.telegram.org/bot{self.bot_token}"

    def is_configured(self):
        return bool(self.bot_token)

    def can_send(self):
        return bool(self.bot_token and self.chat_id)

    async def start(self):
        if not self.enabled or not self.bot_token:
            return
        if self._poll_task and not self._poll_task.done():
            return
        self._running = True
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))
        self._poll_task = asyncio.create_task(self._poll_loop(), name="telegram_poll")
        if self.can_send():
            await self.send_message("Sopotek Pilot is connected on Telegram. Use /help for commands.", include_keyboard=True)

    async def stop(self):
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def notify_trade(self, trade):
        if not self.can_send() or not isinstance(trade, dict):
            return

        symbol = str(trade.get("symbol") or "-")
        side = str(trade.get("side") or "-").upper()
        status = str(trade.get("status") or "-").upper()
        price = trade.get("price", "-")
        size = trade.get("size", trade.get("amount", "-"))
        pnl = trade.get("pnl", "-")
        order_id = trade.get("order_id", trade.get("id", "-"))
        timestamp = trade.get("timestamp") or datetime.utcnow().isoformat()
        message = (
            "<b>Trading Activity</b>\n"
            f"Symbol: <code>{symbol}</code>\n"
            f"Side: <b>{side}</b>\n"
            f"Status: <b>{status}</b>\n"
            f"Price: <code>{price}</code>\n"
            f"Size: <code>{size}</code>\n"
            f"PnL: <code>{pnl}</code>\n"
            f"Order ID: <code>{order_id}</code>\n"
            f"Time: <code>{timestamp}</code>"
        )
        await self.send_message(message)

    async def send_message(self, text, include_keyboard=False, reply_markup=None):
        if not self.can_send():
            return False
        try:
            await self._ensure_session()
            chunks = self._split_message_chunks(str(text or ""))
            sent_any = False
            for index, chunk in enumerate(chunks):
                payload = {
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true",
                }
                markup_payload = None
                if index == len(chunks) - 1:
                    if reply_markup is not None:
                        markup_payload = reply_markup
                    elif include_keyboard:
                        markup_payload = self._command_keyboard_markup()
                if markup_payload is not None:
                    payload["reply_markup"] = json.dumps(markup_payload)
                async with self._session.post(
                    f"{self.base_url}/sendMessage",
                    data=payload,
                ) as response:
                    result = await response.json(content_type=None)
                    if not result.get("ok"):
                        return False
                    sent_any = True
            return sent_any
        except Exception as exc:
            self.logger.debug("Telegram send_message failed: %s", exc)
            return False

    async def send_photo(self, file_path, caption=None):
        if not self.can_send() or not file_path or not os.path.exists(file_path):
            return False
        try:
            await self._ensure_session()
            data = aiohttp.FormData()
            data.add_field("chat_id", self.chat_id)
            if caption:
                data.add_field("caption", str(caption))
            with open(file_path, "rb") as handle:
                data.add_field(
                    "photo",
                    handle,
                    filename=os.path.basename(file_path),
                    content_type="image/png",
                )
                async with self._session.post(f"{self.base_url}/sendPhoto", data=data) as response:
                    payload = await response.json(content_type=None)
                    return bool(payload.get("ok"))
        except Exception as exc:
            self.logger.debug("Telegram send_photo failed: %s", exc)
            return False

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))

    async def _poll_loop(self):
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.logger.debug("Telegram polling error: %s", exc)
                await asyncio.sleep(3)

    async def _get_updates(self):
        await self._ensure_session()
        params = {"timeout": 30, "offset": self._offset + 1}
        async with self._session.get(f"{self.base_url}/getUpdates", params=params) as response:
            payload = await response.json(content_type=None)
        if not payload.get("ok"):
            return []
        return payload.get("result", []) or []

    async def _handle_update(self, update):
        update_id = int(update.get("update_id", self._offset) or self._offset)
        self._offset = max(self._offset, update_id)
        callback_query = update.get("callback_query") or {}
        callback_data = str(callback_query.get("data") or "").strip()
        callback_chat = callback_query.get("message", {}).get("chat", {}) or {}
        callback_chat_id = str(callback_chat.get("id") or "").strip()
        callback_id = str(callback_query.get("id") or "").strip()
        if callback_data and callback_chat_id:
            if self.chat_id and callback_chat_id != self.chat_id:
                return
            await self._handle_callback_query(callback_data, callback_chat_id, callback_id)
            return

        message = update.get("message") or update.get("edited_message") or {}
        text = str(message.get("text") or "").strip()
        chat = message.get("chat") or {}
        incoming_chat_id = str(chat.get("id") or "").strip()
        if not text or not incoming_chat_id:
            return
        if self.chat_id and incoming_chat_id != self.chat_id:
            return

        command_text = text.split(None, 1)
        command_token = str(command_text[0] or "").strip().lower()
        command = command_token.split("@", 1)[0]
        args_text = command_text[1].strip() if len(command_text) > 1 else ""
        lowered = text.lower()

        if command in {"/start", "/help", "/commands"}:
            await self.send_message(self._help_text(), include_keyboard=True)
            return
        if command == "/status":
            await self.send_message(await self.controller.telegram_status_text())
            return
        if command == "/balances":
            await self.send_message(await self.controller.telegram_balances_text())
            return
        if command == "/positions":
            await self.send_message(await self.controller.telegram_positions_text())
            return
        if command in {"/orders", "/openorders"}:
            await self.send_message(await self.controller.telegram_open_orders_text())
            return
        if command == "/recommendations":
            await self.send_message(await self.controller.telegram_recommendations_text())
            return
        if command == "/performance":
            await self.send_message(await self.controller.telegram_performance_text())
            return
        if command in {"/analysis", "/positionanalysis"}:
            await self.send_message(await self.controller.telegram_position_analysis_text(open_window=True))
            return
        if command == "/screenshot":
            screenshot_path = await self.controller.capture_telegram_screenshot()
            if screenshot_path:
                sent = await self.send_photo(screenshot_path, caption="Sopotek terminal screenshot")
                if not sent:
                    await self.send_message(f"Screenshot captured but could not be uploaded: <code>{screenshot_path}</code>")
            else:
                await self.send_message("Unable to capture a screenshot right now.")
            return
        if command == "/chart":
            parsed = self._parse_chart_args(args_text)
            if not parsed.get("symbol"):
                await self.send_message("Usage: /chart SYMBOL [TIMEFRAME]. Example: <code>/chart EUR/USD 1h</code>")
                return
            result = await self.controller.telegram_open_chart(parsed["symbol"], parsed.get("timeframe"))
            await self.send_message(result.get("message") or "Chart request processed.")
            return
        if command in {"/chartshot", "/chartphoto", "/sendchart"}:
            parsed = self._parse_chart_args(args_text)
            if not parsed.get("symbol"):
                await self.send_message("Usage: /chartshot SYMBOL [TIMEFRAME]. Example: <code>/chartshot BTC/USDT 15m</code>")
                return
            screenshot_path = await self.controller.capture_chart_screenshot(
                parsed["symbol"],
                parsed.get("timeframe"),
                prefix="telegram_chart",
            )
            if screenshot_path:
                caption = f"Sopotek chart {parsed['symbol']} ({parsed.get('timeframe') or getattr(self.controller, 'time_frame', '1h')})"
                sent = await self.send_photo(screenshot_path, caption=caption)
                if not sent:
                    await self.send_message(f"Chart captured but could not be uploaded: <code>{screenshot_path}</code>")
            else:
                await self.send_message("Unable to open or capture that chart right now.")
            return
        if command in {"/ask", "/chat"}:
            question = args_text
            if not question:
                await self.send_message("Send a question after /ask or /chat.")
                return
            answer = await self._ask_controller(question, incoming_chat_id)
            await self.send_message(answer)
            return
        if command in {"/trade", "/buy", "/sell"}:
            action_text = self._build_trade_action_text(command, args_text)
            if not action_text:
                await self.send_message(
                    "Usage: <code>/trade buy EUR/USD amount 1000 confirm</code> or "
                    "<code>/buy EUR/USD amount 0.01 type market confirm</code>"
                )
                return
            if "confirm" in action_text.lower():
                answer = await self._handle_direct_action(action_text, incoming_chat_id)
                await self.send_message(answer)
                return
            preview = await self._handle_direct_action(action_text, incoming_chat_id)
            token = self._register_pending_trade_action(incoming_chat_id, action_text)
            await self.send_message(
                preview,
                reply_markup=self._trade_confirmation_markup(token),
            )
            return

        if command.startswith("/"):
            await self.send_message(self._help_text(), include_keyboard=True)
            return

        answer = await self._ask_controller(text, incoming_chat_id)
        await self.send_message(answer)

    def _help_text(self):
        return (
            "<b>Sopotek Telegram Commands</b>\n"
            "/commands - show keyboard and command list\n"
            "/status - trading status and AI scope\n"
            "/balances - account balances\n"
            "/positions - open positions\n"
            "/orders - open exchange orders\n"
            "/recommendations - top trade recommendations\n"
            "/performance - performance snapshot\n"
            "/analysis - broker position analysis summary\n"
            "/screenshot - terminal screenshot\n"
            "/chart SYMBOL [TIMEFRAME] - open/focus a chart in the app\n"
            "/chartshot SYMBOL [TIMEFRAME] - capture that chart and send it here\n"
            "/trade ... - preview or place a trade with CONFIRM\n"
            "/ask &lt;question&gt; - ask Sopotek Pilot about the app or current market context\n"
            "/help - show this message"
        )

    def _command_keyboard_markup(self):
        return {
            "keyboard": [
                [{"text": "/status"}, {"text": "/balances"}, {"text": "/positions"}],
                [{"text": "/orders"}, {"text": "/recommendations"}, {"text": "/performance"}],
                [{"text": "/analysis"}, {"text": "/screenshot"}, {"text": "/commands"}],
                [{"text": "/chart EUR/USD 1h"}, {"text": "/chartshot EUR/USD 1h"}],
                [{"text": "/trade buy EUR/USD amount 1000"}, {"text": "/trade buy EUR/USD amount 1000 confirm"}],
                [{"text": "/ask Give me a short market and account summary"}],
            ],
            "resize_keyboard": True,
            "is_persistent": True,
            "one_time_keyboard": False,
            "input_field_placeholder": "Choose a command or type /ask ...",
        }

    def _trade_confirmation_markup(self, token):
        return {
            "inline_keyboard": [
                [
                    {"text": "Confirm Trade", "callback_data": f"trade_confirm:{token}"},
                    {"text": "Cancel Trade", "callback_data": f"trade_cancel:{token}"},
                ]
            ]
        }

    def _parse_chart_args(self, text):
        raw = str(text or "").strip()
        if not raw:
            return {"symbol": "", "timeframe": ""}
        parts = [part for part in re.split(r"\s+", raw) if part]
        if not parts:
            return {"symbol": "", "timeframe": ""}
        symbol = parts[0].upper()
        timeframe = parts[1] if len(parts) > 1 else ""
        return {"symbol": symbol, "timeframe": timeframe}

    def _build_trade_action_text(self, command, args_text):
        raw_args = str(args_text or "").strip()
        normalized_command = str(command or "").strip().lower()
        if normalized_command == "/trade":
            if not raw_args:
                return ""
            return raw_args if raw_args.lower().startswith("trade ") else f"trade {raw_args}"
        if not raw_args:
            return ""
        side = "buy" if normalized_command == "/buy" else "sell"
        return f"trade {side} {raw_args}"

    def _register_pending_trade_action(self, chat_id, action_text):
        token = uuid.uuid4().hex[:12]
        self._pending_trade_actions[token] = {
            "chat_id": str(chat_id or "").strip(),
            "action_text": str(action_text or "").strip(),
        }
        return token

    async def _handle_callback_query(self, data, chat_id, callback_id=""):
        payload = str(data or "").strip()
        if ":" not in payload:
            await self._answer_callback_query(callback_id, "Unknown action.")
            return
        action, token = payload.split(":", 1)
        pending = self._pending_trade_actions.get(token)
        if not pending or pending.get("chat_id") != str(chat_id or "").strip():
            await self._answer_callback_query(callback_id, "This trade request is no longer available.")
            return

        if action == "trade_cancel":
            self._pending_trade_actions.pop(token, None)
            await self._answer_callback_query(callback_id, "Trade request canceled.")
            await self.send_message("Trade request canceled.")
            return

        if action == "trade_confirm":
            self._pending_trade_actions.pop(token, None)
            action_text = str(pending.get("action_text") or "").strip()
            if "confirm" not in action_text.lower():
                action_text = f"{action_text} confirm"
            result = await self._handle_direct_action(action_text, chat_id)
            await self._answer_callback_query(callback_id, "Trade submitted.")
            await self.send_message(result)
            return

        await self._answer_callback_query(callback_id, "Unknown trade action.")

    async def _answer_callback_query(self, callback_id, text=""):
        if not callback_id:
            return False
        try:
            await self._ensure_session()
            async with self._session.post(
                f"{self.base_url}/answerCallbackQuery",
                data={"callback_query_id": callback_id, "text": str(text or "")[:200]},
            ) as response:
                payload = await response.json(content_type=None)
                return bool(payload.get("ok"))
        except Exception as exc:
            self.logger.debug("Telegram answerCallbackQuery failed: %s", exc)
            return False

    async def _handle_direct_action(self, action_text, chat_id):
        handler = getattr(self.controller, "handle_market_chat_action", None)
        if callable(handler):
            try:
                result = await handler(action_text)
            except TypeError:
                result = None
            if result:
                return str(result)
        return await self._ask_controller(action_text, chat_id)

    async def _ask_controller(self, question, chat_id):
        history = list(self._chat_histories.get(chat_id, []) or [])
        try:
            answer = await self.controller.ask_openai_about_app(question, conversation=history)
        except TypeError:
            answer = await self.controller.ask_openai_about_app(question)
        answer_text = str(answer or "").strip() or "No response returned."
        updated_history = history + [
            {"role": "user", "content": str(question or "").strip()},
            {"role": "assistant", "content": answer_text},
        ]
        self._chat_histories[chat_id] = updated_history[-12:]
        return answer_text

    def _split_message_chunks(self, text, max_length=3500):
        raw = str(text or "")
        if not raw:
            return [""]
        if len(raw) <= max_length:
            return [raw]

        chunks = []
        remaining = raw
        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, max_length)
            if split_at < max_length // 3:
                split_at = remaining.rfind(" ", 0, max_length)
            if split_at < max_length // 3:
                split_at = max_length
            chunk = remaining[:split_at].rstrip()
            chunks.append(chunk)
            remaining = remaining[split_at:].lstrip()
        return chunks
