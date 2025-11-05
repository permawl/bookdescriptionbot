import logging
import sys
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Enable logging (helps see errors if something goes wrong)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a book name, e.g. /book The Blade Itself")
        return

    book_name = " ".join(context.args)
    search_query = quote_plus(f"site:goodreads.com {book_name}")
    google_url = f"https://www.google.com/search?q={search_query}"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        # Step 1: Find Goodreads link via Google
        res = requests.get(google_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        link_tag = None
        for a in soup.find_all("a", href=True):
            if "goodreads.com/book/show" in a["href"]:
                link_tag = a
                break

        if not link_tag:
            await update.message.reply_text("No Goodreads page found for that book.")
            return

        start = link_tag["href"].find("https://www.goodreads.com/book/show")
        end = link_tag["href"].find("&", start)
        book_url = link_tag["href"][start:end] if end != -1 else link_tag["href"][start:]

        # Step 2: Fetch Goodreads page
        gr_page = requests.get(book_url, headers=headers, timeout=10)
        gr_soup = BeautifulSoup(gr_page.text, "html.parser")

        # Step 3: Extract title, author, rating, and description
        title_tag = gr_soup.select_one("h1.Text.Text__title1")
        author_tag = gr_soup.select_one("span.ContributorLink__name")
        rating_tag = gr_soup.select_one("div.RatingStatistics__rating")
        desc_tag = gr_soup.select_one("span.Formatted, div#description span")

        title = title_tag.get_text(strip=True) if title_tag else book_name
        author = author_tag.get_text(strip=True) if author_tag else "Unknown author"
        rating = rating_tag.get_text(strip=True) if rating_tag else "N/A"
        description = desc_tag.get_text(strip=True) if desc_tag else "No description available."

        # Optional: trim very long descriptions
        if len(description) > 1200:
            description = description[:1200].rsplit(" ", 1)[0] + "..."

        # Step 4: Format message
        text = (
            f"📖 *{title}*\n👤 _{author}_\n⭐ {rating}\n\n"
            f"{description}\n\n🔗 {book_url}"
        )

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
