import logging
import os
import urllib.parse

import requests
from bs4 import BeautifulSoup
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ------------------------------------------------------------
# 1️⃣  Logging
# ------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 2️⃣  Bot token (read from the Render/Heroku/etc. environment)
# ------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "❌ TELEGRAM_BOT_TOKEN environment variable not set! "
        "Add it to your deployment platform before starting the bot."
    )

# ------------------------------------------------------------
# 3️⃣  Helper: fetch the description of a *single* book page
# ------------------------------------------------------------
def _fetch_description(book_url: str) -> str:
    """
    Download the Goodreads page for a book and return a cleaned description.
    If something goes wrong we return a short fallback string.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36"
        )
    }

    try:
        resp = requests.get(book_url, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"Failed to fetch description for {book_url}: {exc}")
        return "Could not load description."

    soup = BeautifulSoup(resp.text, "html.parser")

    # Goodreads uses a few different class names depending on the layout.
    description_div = soup.find("div", class_="BookPageMetadataSection__description")
    if not description_div:
        description_div = soup.find("div", class_="description")

    if not description_div:
        return "No description available."

    # Strip out hidden "more/less" spans that Goodreads injects.
    for hidden in description_div.find_all("span", {"style": "display:none"}):
        hidden.decompose()

    description = description_div.get_text(separator=" ", strip=True)
    if not description:
        return "No description available."

    # Keep the description short enough for a Telegram message.
    MAX_LEN = 800
    if len(description) > MAX_LEN:
        description = description[:MAX_LEN].rstrip() + "…"

    return description


# ------------------------------------------------------------
# 4️⃣  Search Goodreads – returns a list of dicts (title, author, url)
# ------------------------------------------------------------
def search_goodreads(query: str, limit: int = 5):
    """
    Perform a Goodreads search and return up to `limit` results.
    Each result is a dict:
        {
            "title": "Book title",
            "author": "First Author",
            "url": "https://www.goodreads.com/…"
        }
    """
    encoded = urllib.parse.quote(query)
    search_url = f"https://www.goodreads.com/search?q={encoded}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36"
        )
    }

    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception as exc:
        logger.error(f"Search request failed: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # Each search result row is a <tr> with class "bookalike review"
    rows = soup.select("tr.bookalike.review")
    for row in rows[:limit]:
        # Title link
        title_tag = row.select_one("a.bookTitle")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)

        # Author (first one displayed)
        author_tag = row.select_one("a.authorName")
        author = author_tag.get_text(strip=True) if author_tag else "Unknown"

        # Full Goodreads URL
        url = "https://www.goodreads.com" + title_tag["href"]

        results.append({"title": title, "author": author, "url": url})

    return results


# ------------------------------------------------------------
# 5️⃣  /start command
# ------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *Welcome to the Goodreads Book Finder Bot!*\n\n"
        "Send a book title with:\n"
        "`/book <title>`\n"
        "If more than one match is found, you’ll be asked to pick the right one.",
        parse_mode="Markdown",
    )


# ------------------------------------------------------------
# 6️⃣  /book command – core logic
# ------------------------------------------------------------
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /book <book title>")
        return

    query = " ".join(context.args)
    await update.message.reply_text(
        f"🔍 Searching Goodreads for *{query}*…", parse_mode="Markdown"
    )

    results = search_goodreads(query, limit=5)

    if not results:
        await update.message.reply_text("❌ No books found.")
        return

    # Store the list for the current user (so the callback can retrieve it)
    context.user_data["search_results"] = results

    if len(results) == 1:
        # Only one match → send it immediately.
        book = results[0]
        description = _fetch_description(book["url"])
        await _send_book_reply(update, book, description)
        return

    # ------------------------------
    # Multiple matches → ask the user to pick one via inline keyboard
    # ------------------------------
    keyboard = []
    for idx, book in enumerate(results):
        button_text = f"{book['title']} — {book['author']}"
        # Callback data can only be 64 bytes → we just send the index.
        keyboard.append(
            [InlineKeyboardButton(button_text, callback_data=str(idx))]
        )
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔎 Multiple matches found – please choose the correct one:",
        reply_markup=reply_markup,
    )


# ------------------------------------------------------------
# 7️⃣  Helper: send the final reply (link + description)
# ------------------------------------------------------------
async def _send_book_reply(
    update: Update, book: dict, description: str, is_callback: bool = False
):
    """
    Formats and sends the final message.
    `is_callback` tells us whether we are replying to a callback query
    (so we can answer it) or to a normal message.
    """
    text = f"✅ *Found on Goodreads!*\n\n"
    text += f"📘 [{book['title']}]({book['url']})\n"
    text += f"✍️ *Author:* {book['author']}\n\n"
    text += f"*Description:*\n_{description}_"

    if is_callback:
        # For callbacks we edit the original message (the one with the keyboard)
        query = update.callback_query
        await query.edit_message_text(
            text=text, parse_mode="Markdown", disable_web_page_preview=False
        )
        await query.answer()  # removes the "loading…" animation
    else:
        await update.message.reply_text(
            text=text, parse_mode="Markdown", disable_web_page_preview=False
        )


# ------------------------------------------------------------
# 8️⃣  Callback handler – user chose a book from the list
# ------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # acknowledge the click (removes loading spinner)

    # Retrieve the stored list of results
    results = context.user_data.get("search_results")
    if not results:
        await query.edit_message_text("⚠️ No search data found. Please try again.")
        return

    # The callback data is the index (as a string)
    try:
        idx = int(query.data)
        chosen = results[idx]
    except (ValueError, IndexError):
        await query.edit_message_text("⚠️ Invalid selection.")
        return

    # Fetch description for the chosen book
    description = _fetch_description(chosen["url"])

    # Send final answer (editing the original message that had the keyboard)
    await _send_book_reply(update, chosen, description, is_callback=True)


# ------------------------------------------------------------
# 9️⃣  Main entry point
# ------------------------------------------------------------
def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("book", book))

    # Inline‑keyboard callbacks
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("✅ Bot started – polling for updates.")
    app.run_polling()


if __name__ == "__main__":
    main()