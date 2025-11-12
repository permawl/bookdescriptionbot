import logging
import os
import urllib.parse

import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

# ------------------------------------------------------------
# 1️⃣ Logging
# ------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 2️⃣ Bot token
# ------------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "❌ TELEGRAM_BOT_TOKEN environment variable not set! "
        "Add it to your deployment platform before starting the bot."
    )

# ------------------------------------------------------------
# 3️⃣ Fetch description (still works)
# ------------------------------------------------------------
def _fetch_description(book_url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    try:
        resp = requests.get(book_url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"Failed to fetch description for {book_url}: {exc}")
        return "Could not load description."

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try multiple selectors for description
    for selector in [
        "div.BookPageMetadataSection__description",
        "div.description",
        "span#freeTextContainer",
        "div#description",
    ]:
        desc_div = soup.select_one(selector)
        if desc_div:
            for hidden in desc_div.find_all("span", {"style": "display:none"}):
                hidden.decompose()
            text = desc_div.get_text(" ", strip=True)
            return (text[:800] + "...") if len(text) > 800 else text

    return "No description available."


# ------------------------------------------------------------
# 4️⃣ Search Goodreads – FIXED & MORE ROBUST
# ------------------------------------------------------------
def search_goodreads(query: str, limit: int = 5):
    encoded = urllib.parse.quote(query)
    search_url = f"https://www.goodreads.com/search?q={encoded}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        resp = requests.get(search_url, headers=headers, timeout=15)
        logger.info(f"Goodreads search status: {resp.status_code}")

        if resp.status_code == 429:
            logger.error("Rate limited by Goodreads (429 Too Many Requests)")
            return []
        if resp.status_code != 200:
            logger.error(f"Unexpected status: {resp.status_code}")
            return []

    except Exception as exc:
        logger.error(f"Search request failed: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # NEW: Try multiple selectors for results
    results = []

    # Try 1: Modern layout (data-testid="result")
    items = soup.select("[data-testid='searchResultItem']")
    if items:
        for item in items[:limit]:
            title_tag = item.select_one("a[href*='/book/show']")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            author_tag = item.select_one("a[href*='/author/show']")
            author = author_tag.get_text(strip=True) if author_tag else "Unknown"

            url = "https://www.goodreads.com" + title_tag["href"]

            results.append({"title": title, "author": author, "url": url})
        return results

    # Try 2: Legacy table layout
    rows = soup.select("tr.bookalike.review")
    for row in rows[:limit]:
        title_tag = row.select_one("a.bookTitle")
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)

        author_tag = row.select_one("a.authorName")
        author = author_tag.get_text(strip=True) if author_tag else "Unknown"

        url = "https://www.goodreads.com" + title_tag["href"]

        results.append({"title": title, "author": author, "url": url})

    return results


# ------------------------------------------------------------
# 5️⃣ /start command
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
# 6️⃣ /book command – core logic
# ------------------------------------------------------------
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("UsageId: /book <book title>")
        return

    query = " ".join(context.args)
    await update.message.reply_text(
        f"🔍 Searching Goodreads for *{query}*…", parse_mode="Markdown"
    )

    results = search_goodreads(query, limit=5)

    if not results:
        await update.message.reply_text(
            "❌ No books found. Try a different title or check spelling."
        )
        return

    context.user_data["search_results"] = results

    if len(results) == 1:
        book = results[0]
        description = _fetch_description(book["url"])
        await _send_book_reply(update, book, description)
        return

    # Multiple matches → inline keyboard
    keyboard = []
    for idx, book in enumerate(results):
        button_text = f"{book['title']} — {book['author']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=str(idx))])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔎 Multiple matches found – please choose the correct one:",
        reply_markup=reply_markup,
    )


# ------------------------------------------------------------
# 7️⃣ Send final reply
# ------------------------------------------------------------
async def _send_book_reply(update: Update, book: dict, description: str, is_callback: bool = False):
    text = f"✅ *Found on Goodreads!*\n\n"
    text += f"📘 [{book['title']}]({book['url']})\n"
    text += f"✍️ *Author:* {book['author']}\n\n"
    text += f"*Description:*\n_{description}_"

    if is_callback:
        query = update.callback_query
        await query.edit_message_text(
            text=text, parse_mode="Markdown", disable_web_page_preview=False
        )
        await query.answer()
    else:
        await update.message.reply_text(
            text=text, parse_mode="Markdown", disable_web_page_preview=False
        )


# ------------------------------------------------------------
# 8️⃣ Callback handler
# ------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    results = context.user_data.get("search_results")
    if not results:
        await query.edit_message_text("⚠️ No search data found. Please try again.")
        return

    try:
        idx = int(query.data)
        chosen = results[idx]
    except (ValueError, IndexError):
        await query.edit_message_text("⚠️ Invalid selection.")
        return

    description = _fetch_description(chosen["url"])
    await _send_book_reply(update, chosen, description, is_callback=True)


# ------------------------------------------------------------
# 9️⃣ Main
# ------------------------------------------------------------
def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("book", book))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("✅ Bot started – polling for updates.")
    app.run_polling()


if __name__ == "__main__":
    main()