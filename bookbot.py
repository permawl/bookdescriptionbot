import logging
import sys
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Function to fetch book info ---
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a book name, e.g. /book The Blade Itself")
        return

    book_name = " ".join(context.args)
    search_query = quote_plus(f"site:goodreads.com {book_name}")
    google_url = f"https://www.google.com/search?q={search_query}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        # Step 1: Find Goodreads link via Google
        logging.info(f"Searching Google for: {book_name}")
        res = requests.get(google_url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        book_url = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Google links start with /url?q=https://...
            if href.startswith("/url?q=") and "goodreads.com/book/show" in href:
                href = href.split("/url?q=")[1].split("&")[0]
                if href.startswith("https://www.goodreads.com/book/show"):
                    book_url = href
                    break

        if not book_url:
            await update.message.reply_text("No Goodreads page found for that book.")
            logging.warning("No Goodreads link found in Google search results.")
            return

        logging.info(f"Found Goodreads URL: {book_url}")

        # Step 2: Fetch Goodreads page
        gr_page = requests.get(book_url, headers=headers, timeout=10)
        gr_soup = BeautifulSoup(gr_page.text, "html.parser")

        # Step 3: Extract title, author, rating, and description
        title_tag = (
            gr_soup.select_one("h1.Text.Text__title1")
            or gr_soup.select_one("h1#bookTitle")
        )
        author_tag = (
            gr_soup.select_one("span.ContributorLink__name")
            or gr_soup.select_one("span[itemprop='name']")
        )
        rating_tag = (
            gr_soup.select_one("div.RatingStatistics__rating")
            or gr_soup.select_one("span[itemprop='ratingValue']")
        )
        desc_tag = (
            gr_soup.select_one("div[data-testid='description'] span")
            or gr_soup.select_one("div#description span:nth-of-type(2)")
            or gr_soup.select_one("div#description span")
        )

        title = title_tag.get_text(strip=True) if title_tag else book_name
        author = author_tag.get_text(strip=True) if author_tag else "Unknown author"
        rating = rating_tag.get_text(strip=True) if rating_tag else "N/A"
        description = desc_tag.get_text(strip=True) if desc_tag else "No description available."

        if len(description) > 1200:
            description = description[:1200].rsplit(" ", 1)[0] + "..."

        text = (
            f"📖 *{title}*\n👤 _{author}_\n⭐ {rating}\n\n"
            f"{description}\n\n🔗 {book_url}"
        )

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as e:
        logging.exception(e)
        await update.message.reply_text("Something went wrong while fetching the book info.")

# --- Run bot ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("book", book))
    app.run_polling()

if __name__ == "__main__":
    main()
