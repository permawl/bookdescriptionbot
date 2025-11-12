import logging
import os
import urllib.parse

import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

# ------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# Bot token
# ------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN environment variable not set!")

# ------------------------------------------------------------
# Description fetcher (same as before)
# ------------------------------------------------------------
def _fetch_description(book_url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36"
    }

    try:
        resp = requests.get(book_url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"Failed to fetch description for {book_url}: {exc}")
        return "Could not load description."

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try multiple selectors for the description
    for selector in [
        "div.BookPageMetadataSection__description",
        "div.description",
        "div#description span",
    ]:
        desc_div = soup.select_one(selector)
        if desc_div:
            text = desc_div.get_text(" ", strip=True)
            return (text[:800] + "...") if len(text) > 800 else text

    return "No description available."

# ------------------------------------------------------------
# Goodreads search (fixed)
# ------------------------------------------------------------
def search_goodreads(query: str, limit: int = 5):
    encoded = urllib.parse.quote(query)
    search_url = f"https://www.goodreads.com/search?q={encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        logger.error(f"Search request failed: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # Goodreads modern structure (2025)
    for row in soup.select("a.bookTitle")[:limit]:
        title = row.get_text(strip=True)
        href = row.get("href", "")
        if not href.startswith("/book/show"):
            continue
        url = "https://www.goodreads.com" + href

        # Author is in the same row, nearby
        author_tag = row.find_parent("tr").select_one("a.authorName") if row.find_parent("tr") else None
        author = author_tag.get_text(strip=True) if author_tag else "Unknown"

        results.append({"title": title, "author": author, "url": url})

    logger.info(f"Found {len(results)} Goodreads results for '{query}'")
    return results

# ------------------------------------------------------------
# /start command
# ------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *Welcome to the Goodreads Book Finder Bot!*\n\n"
        "Use `/book <title>` to search.\n"
        "If multiple books match, you'll get options to choose from.",
        parse_mode="Markdown",
    )

# ------------------------------------------------------------
# /book command
# ------------------------------------------------------------
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /book <book title>")
        return

    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 Searching Goodreads for *{query}*…", parse_mode="Markdown")

    results = search_goodreads(query, limit=5)

    if not results:
        await update.message.reply_text("❌ No books found. Try a different title or check spelling.")
        return

    context.user_data["search_results"] = results

    # If one result, fetch directly
    if len(results) == 1:
        book = results[0]
        desc = _fetch_description(book["url"])
        await _send_book_reply(update, book, desc)
        return

    # Multiple options: show buttons
    keyboard = [
        [InlineKeyboardButton(f"{book['title']} — {book['author']}", callback_data=str(i))]
        for i, book in enumerate(results)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📚 Multiple results found — please choose one:",
        reply_markup=reply_markup,
    )

# ------------------------------------------------------------
# Send chosen book
# ------------------------------------------------------------
async def _send_book_reply(update: Update, book: dict, desc: str, is_callback=False):
    text = (
        f"✅ *Found on Goodreads!*\n\n"
        f"📘 [{book['title']}]({book['url']})\n"
        f"✍️ _{book['author']}_\n\n"
        f"📖 *Description:*\n_{desc}_"
    )

    if is_callback:
        await update.callback_query.edit_message_text(
            text=text, parse_mode="Markdown", disable_web_page_preview=False
        )
    else:
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)

# ------------------------------------------------------------
# Button callback
# ------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    results = context.user_data.get("search_results", [])
    try:
        idx = int(query.data)
        chosen = results[idx]
    except (ValueError, IndexError):
        await query.edit_message_text("⚠️ Invalid selection.")
        return

    desc = _fetch_description(chosen["url"])
    await _send_book_reply(update, chosen, desc, is_callback=True)

# ------------------------------------------------------------
# Main entry
# ------------------------------------------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("book", book))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("✅ Bot started and polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
