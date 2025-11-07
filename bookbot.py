import requests
from bs4 import BeautifulSoup
import re
import time

def get_book_description(book_title):
    # Use Goodreads search API with proper parameters
    search_url = "https://www.goodreads.com/search/index.xml"
    
    params = {
        'key': GOODREADS_API_KEY,  # You need to set this
        'q': book_title,
        'search': 'title'
    }
    
    try:
        response = requests.get(search_url, params=params)
        response.raise_for_status()
        
        # Parse XML response
        soup = BeautifulSoup(response.content, 'xml')
        
        # Find first book result
        work = soup.find('work')
        if not work:
            return "No Goodreads page found for that book."
            
        # Get book ID from the first result
        best_book = work.find('best_book')
        if not best_book:
            return "No Goodreads page found for that book."
            
        book_id = best_book.find('id').text
        
        # Get detailed book information
        book_details_url = f"https://www.goodreads.com/book/show/{book_id}.xml?format=xml"
        book_response = requests.get(book_details_url, params={'key': GOODREADS_API_KEY})
        book_soup = BeautifulSoup(book_response.content, 'xml')
        
        # Extract book details
        title = book_soup.find('title')
        author = book_soup.find('name')
        description = book_soup.find('description')
        rating = book_soup.find('average_rating')
        
        if not title:
            return "No Goodreads page found for that book."
            
        # Format response
        message = f"📚 *{title.text.strip()}*\n\n"
        
        if author:
            message += f"👤 Author: {author.text.strip()}\n"
            
        if rating:
            message += f"⭐ Rating: {rating.text.strip()}/5.0\n\n"
            
        if description:
            # Clean up description and limit length
            desc_text = re.sub(r'<[^>]+>', '', description.text.strip())
            desc_text = re.sub(r'\s+', ' ', desc_text)
            if len(desc_text) > 2000:
                desc_text = desc_text[:2000] + "..."
            message += f"📖 Description:\n{desc_text}"
            
        return message
        
    except Exception as e:
        print(f"Error fetching book info: {e}")
        return "No Goodreads page found for that book."