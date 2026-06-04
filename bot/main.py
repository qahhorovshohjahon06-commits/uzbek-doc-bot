import logging
import os
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    filters,
)

from states import State
from database import init_db
from handlers import (
    start,
    help_command,
    plan_command,
    myid_command,
    ref_command,
    ref_copy_callback,
    open_ref_callback,
    buy_command,
    buy_plan_callback,
    open_buy_callback,
    pre_checkout_handler,
    successful_payment_handler,
    history_command,
    download_callback,
    addpremium_command,
    removepremium_command,
    stats_command,
    broadcast_command,
    choose_doc_type,
    enter_topic,
    enter_count,
    cancel,
    unknown,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    init_db()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^🏠 Bosh menyu$"), start),
        ],
        states={
            State.CHOOSING_DOC_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_doc_type),
            ],
            State.ENTERING_TOPIC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_topic),
            ],
            State.ENTERING_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_count),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("history", history_command),
            CommandHandler("plan", plan_command),
            CommandHandler("buy", buy_command),
            CommandHandler("ref", ref_command),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)

    # User commands
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("plan", plan_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("ref", ref_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("myid", myid_command))

    # Admin commands
    app.add_handler(CommandHandler("addpremium", addpremium_command))
    app.add_handler(CommandHandler("removepremium", removepremium_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    # Inline button callbacks (order matters — most specific first)
    app.add_handler(CallbackQueryHandler(download_callback,   pattern=r"^dl:"))
    app.add_handler(CallbackQueryHandler(open_buy_callback,   pattern=r"^open_buy$"))
    app.add_handler(CallbackQueryHandler(buy_plan_callback,   pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(open_ref_callback,   pattern=r"^open_ref$"))
    app.add_handler(CallbackQueryHandler(ref_copy_callback,   pattern=r"^ref_copy:"))

    # Telegram Stars payment flow
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=["message", "callback_query", "pre_checkout_query"])


if __name__ == "__main__":
    main()
