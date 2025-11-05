import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import os

# Enable logging (helps see errors if something goes wrong)
logging.basicConfig(level=logging.INFO)

# 🔑 Replace with your own Telegram bot token from @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a book name, e.g. /book The Blade Itself")
        return

    query = " ".join(context.args)
    search_url = f"https://www.goodreads.com/search?q={quote_plus(query)}"

    try:
        # Step 1: Search Goodreads for the book
        resp = requests.get(search_url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        first_result = soup.select_one("a.bookTitle")
        if not first_result:
            await update.message.reply_text("No results found.")
            return

        book_url = "https://www.goodreads.com" + first_result["href"]

        # Step 2: Fetch the book page itself
        book_page = requests.get(book_url, timeout=10)
        page_soup = BeautifulSoup(book_page.text, "html.parser")

        # Step 3: Extract title and full description
        title_tag = page_soup.select_one("h1#bookTitle")
        desc_tags = page_soup.select("div#description span")

        if not title_tag:
            await update.message.reply_text("Couldn't extract book info.")
            return

        title = title_tag.get_text(strip=True)

        if desc_tags:
            # Goodreads usually hides full description in the *last* span
            description = desc_tags[-1].get_text(strip=True)
        else:
            description = "No description available."

        # Optional: limit extremely long text
        if len(description) > 1200:
            description = description[:1200].rsplit(" ", 1)[0] + "..."

        # Step 4: Format and send the message
        text = f"📖 *{title}*\n{book_url}\n\n_{description}_"
        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logging.exception(e)
        await update.message.reply_text("Something went wrong while fetching the book info.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("book", book))
    app.run_polling()

if __name__ == "__main__":
    main()
