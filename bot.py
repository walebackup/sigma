"""Sigma Telegram bot with reliable inline-button routing."""
import logging
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

HOME_TEXT = (
    "Sigma 8.8\n\n"
    "Your favourite trading bot\n\n"
    "Paste a contract address, $cashtag, or choose an option below."
)

# Kept in memory for compatibility with the existing bot. Use a database in production.
user_wallets: dict[int, str] = {}


def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search", callback_data="positions"),
         InlineKeyboardButton("💰 Buy or Snipe", callback_data="lp_sniper")],
        [InlineKeyboardButton("📊 Positions", callback_data="positions"),
         InlineKeyboardButton("🕵️ Copy Trading", callback_data="copy_trade")],
        [InlineKeyboardButton("🕑 Pending Orders", callback_data="limit_orders"),
         InlineKeyboardButton("💳 Wallets", callback_data="wallets")],
        [InlineKeyboardButton("🏆 Rewards", callback_data="referral"),
         InlineKeyboardButton("⛓️ Chains", callback_data="chains")],
        [InlineKeyboardButton("🛟 Support", callback_data="support"),
         InlineKeyboardButton("🌉 Bridge", callback_data="bridge")],
        [InlineKeyboardButton("🖥 Terminal", callback_data="refresh")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
         InlineKeyboardButton("❌ Close", callback_data="close")],
    ])


def wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Import Wallet", callback_data="wallets_import"),
         InlineKeyboardButton("❌ Delete Wallet", callback_data="wallets_delete")],
        [InlineKeyboardButton("◀️ Back", callback_data="back_to_menu"),
         InlineKeyboardButton("🗑️ Close", callback_data="close")],
    ])


def screen_keyboard(name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"{name}_refresh"),
         InlineKeyboardButton("◀️ Back", callback_data="back_to_menu")],
        [InlineKeyboardButton("🗑️ Close", callback_data="close")],
    ])


def chains_keyboard() -> InlineKeyboardMarkup:
    chains = ("SOL", "ETH", "BNB", "BASE", "HYPE", "TRON", "SUI", "POL")
    rows = [
        [InlineKeyboardButton(chain, callback_data=f"chain_{chain.lower()}")]
        for chain in chains
    ]
    rows.append([InlineKeyboardButton("◀️ Back", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)


def import_keyboard(origin: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Import Wallet", callback_data=f"do_import__{origin}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")],
    ])


def screen_text(name: str) -> str:
    texts = {
        "positions": "📊 Positions\n\nNo open positions yet.",
        "lp_sniper": "🎯 Buy or Snipe\n\nNo active sniper tasks.",
        "copy_trade": "🕵️ Copy Trading\n\nNo copy-trading tasks configured.",
        "limit_orders": "🕑 Pending Orders\n\nNo pending orders.",
        "referral": "🏆 Rewards\n\nNo rewards available yet.",
        "bridge": "🌉 Bridge\n\nBridge setup is ready.",
        "settings": "⚙️ Settings\n\nChoose an option or return to the main menu.",
        "support": "🛟 Support\n\nChoose Import Wallet to continue, or go back.",
    }
    return texts.get(name, HOME_TEXT)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HOME_TEXT, reply_markup=menu_keyboard())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    user_id = query.from_user.id
    logger.info("Button pressed: user_id=%s callback=%s", user_id, data)

    # Always acknowledge the Telegram callback immediately. Without this,
    # Telegram shows a spinner and the user often experiences the button as dead.
    try:
        await query.answer()
    except Exception:
        logger.exception("Could not acknowledge callback %s", data)
        return

    try:
        if data == "close":
            await query.message.delete()
            return

        if data in {"back_to_menu", "refresh"}:
            await query.edit_message_text(HOME_TEXT, reply_markup=menu_keyboard())
            return

        if data == "wallets":
            await query.edit_message_text(
                "💳 Wallets\n\nManage your connected wallet.",
                reply_markup=wallet_keyboard(),
            )
            return

        if data == "wallets_import" or data.startswith("do_import__"):
            origin = data.split("__", 1)[1] if "__" in data else "wallets"
            context.user_data["awaiting_wallet"] = True
            await query.edit_message_text(
                "🔑 Send your wallet private key or recovery phrase in your next message.",
                reply_markup=import_keyboard(origin),
            )
            return

        if data == "wallets_delete":
            user_wallets.pop(user_id, None)
            await query.edit_message_text(
                "✅ Wallet deleted.", reply_markup=wallet_keyboard()
            )
            return

        if data == "chains":
            await query.edit_message_text(
                "⛓️ Select a network:", reply_markup=chains_keyboard()
            )
            return

        if data.startswith("chain_"):
            chain = data.removeprefix("chain_").upper()
            if chain in {"SOL", "ETH", "BNB", "BASE", "HYPE", "TRON", "SUI", "POL"}:
                await query.edit_message_text(
                    f"💰 {chain} Wallet\n\nImport a wallet or return to the menu.",
                    reply_markup=wallet_keyboard(),
                )
                return

        if data == "support":
            await query.edit_message_text(
                screen_text("support"), reply_markup=import_keyboard("support")
            )
            return

        if data in {"positions", "lp_sniper", "copy_trade", "limit_orders", "referral", "bridge", "settings"}:
            await query.edit_message_text(
                screen_text(data), reply_markup=screen_keyboard(data)
            )
            return

        # Covers refresh buttons on every secondary screen, including any
        # older messages still containing callback IDs from the previous bot.
        if data.endswith("_refresh"):
            base = data[:-8]
            if base in {"positions", "lp_sniper", "copy_trade", "limit_orders", "referral", "bridge", "settings"}:
                await query.edit_message_text(
                    screen_text(base), reply_markup=screen_keyboard(base)
                )
                return

        logger.warning("Unhandled callback: %s", data)
        await query.answer("This button is not available.", show_alert=True)

    except Exception:
        logger.exception("Button handler failed: callback=%s", data)
        try:
            await query.answer("Something went wrong. Please try again.", show_alert=True)
        except Exception:
            pass


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    if context.user_data.get("awaiting_wallet"):
        user_wallets[update.effective_user.id] = update.effective_message.text or ""
        context.user_data.pop("awaiting_wallet", None)
        await update.effective_message.reply_text(
            "✅ Wallet received. You can now use the menu.", reply_markup=menu_keyboard()
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled update error", exc_info=context.error)


def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_error_handler(error_handler)
    logger.info("Bot running with inline callback handler")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
