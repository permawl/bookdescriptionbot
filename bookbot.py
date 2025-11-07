import logging
import requests
from bs4 import BeautifulSoup
import urllib.parse
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Replace with your bot token
BOT_TOKEN = "7866345321:AAH_7kYB2oAt1DQADYnHYUZYIA52Od3PcMI"

# Function to search Goodreads and return the first book link
def find_goodreads_link(book_title):
    query = urllib.parse.quote(book_title)
    url = f"https://www.goodreads.com/search?q={query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching Goodreads: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the first book result
    result = soup.find("a", class_="bookTitle")
    if result and result.get('href'):
        book_path = result['href']
        return f"https://www.goodreads.com{book_path}"

    return None

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Welcome to the Goodreads Book Finder Bot!\n\n"
        "Send me a book title like: /book The Great Gatsby"
    )

# Book search command
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("UsageId: /book <book title>")
        return

    title = " ".join(context.args)
    await update.message.reply_text(f"🔍 Searching Goodreads for *{title}*...", parse_mode='Markdown')

    link = find_goodreads_link(title)

    if link:
        await update.message.reply_text(
            f"✅ Found on Goodreads!\n\n📘 {link}",
            disable_web_page_preview=False
        )
    else:
        await update.message.reply_text("❌ Could not find the book on Goodreads.")

# Main function
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("book", book))

    print("Bot is running...")
    app.run_polling()