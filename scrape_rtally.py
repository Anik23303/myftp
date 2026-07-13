import requests
from bs4 import BeautifulSoup
import json
import time
import re
import os

# Base URL - using the site you shared
BASE_URL = "https://www.rtally.site"

# Categories to scrape (you can add or remove)
CATEGORIES = [
    "/categories/adult-18",
    "/categories/action",
    "/categories/comedy",
    "/categories/drama",
    "/categories/horror",
    "/categories/sci-fi",
    "/categories/romance",
    "/categories/anime",
    "/categories/documentary",
    "/categories/hollywood",
    "/categories/bollywood",
]

def get_movie_embed_url(movie_url):
    """Extract the embed URL from a movie page"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(movie_url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"  ⚠️ Failed to fetch {movie_url} (Status: {response.status_code})")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for iframe with video source - common patterns
        iframe_patterns = [
            r'turbovidhls\.com',
            r'vidhide',
            r'embed',
            r'player',
            r'stream',
            r'play',
            r'video',
            r'mp4',
            r'mkv'
        ]
        
        # Find all iframes
        iframes = soup.find_all('iframe')
        
        for iframe in iframes:
            src = iframe.get('src', '')
            if src:
                # Check if it matches any pattern
                for pattern in iframe_patterns:
                    if re.search(pattern, src, re.IGNORECASE):
                        return src
        
        # Alternative: look for video source in other elements
        # Check for src in video tags
        video = soup.find('video')
        if video and video.get('src'):
            return video.get('src')
        
        # Check for data-src attributes
        for tag in soup.find_all(['div', 'source', 'iframe'], {'data-src': True}):
            src = tag.get('data-src', '')
            if src:
                return src
        
        return None
    except Exception as e:
        print(f"  ❌ Error fetching {movie_url}: {e}")
        return None

def scrape_category(category_url, max_pages=3):
    """Scrape all movies from a category page"""
    movies = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        print(f"\n📂 Scraping {category_url}...")
        
        # Try multiple pages if pagination exists
        for page in range(1, max_pages + 1):
            # Adjust URL for pagination - may need to change based on site structure
            page_url = BASE_URL + category_url
            if page > 1:
                page_url = f"{BASE_URL}{category_url}?page={page}"
            
            print(f"  📄 Page {page}: {page_url}")
            
            response = requests.get(page_url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"  ⚠️ No more pages (Status: {response.status_code})")
                break
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all movie links - adjust selector based on site structure
            movie_links = []
            
            # Try different common selectors
            selectors = [
                'a[href*="/post/"]',
                'a[href*="/movie/"]',
                'a[href*="/watch/"]',
                '.post-item a',
                '.movie-item a',
                '.card a',
                'article a'
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                if links:
                    movie_links = links
                    break
            
            # If no links found, try a broader approach
            if not movie_links:
                movie_links = soup.find_all('a', href=re.compile(r'/(post|movie|watch|episode)/'))
            
            if not movie_links:
                print(f"  ⚠️ No movie links found on page {page}")
                break
            
            print(f"  Found {len(movie_links)} links on page {page}")
            
            for link in movie_links:
                movie_url = link.get('href')
                if not movie_url:
                    continue
                
                # Get full URL
                if movie_url.startswith('/'):
                    movie_url = BASE_URL + movie_url
                elif not movie_url.startswith('http'):
                    movie_url = BASE_URL + '/' + movie_url
                
                # Skip non-movie links
                if any(x in movie_url for x in ['/home', '/login', '/register', '/admin', '#', 'javascript:']):
                    continue
                
                # Get movie title
                title = link.get('title', '')
                if not title:
                    title = link.text.strip()
                if not title:
                    # Try to get from image alt
                    img = link.find('img')
                    if img and img.get('alt'):
                        title = img.get('alt')
                
                if not title or len(title) < 3:
                    continue
                
                # Clean title
                title = re.sub(r'\s+', ' ', title).strip()
                
                # Generate a unique ID
                video_id = re.sub(r'[^a-zA-Z0-9]', '_', title.lower())[:30]
                video_id = re.sub(r'_+', '_', video_id).strip('_')
                
                # Check if we already have this movie
                if any(m.get('id') == video_id for m in movies):
                    continue
                
                # Get embed URL
                print(f"    🔗 Fetching: {title[:40]}...")
                embed_url = get_movie_embed_url(movie_url)
                
                if embed_url:
                    # Extract category from URL
                    category_name = category_url.split('/')[-1].replace('-', ' ').title()
                    
                    movies.append({
                        'id': video_id,
                        'title': title,
                        'category': category_url.split('/')[-1],
                        'category_name': category_name,
                        'embed_url': embed_url,
                        'rating': 0,
                        'year': 2026,
                        'language': 'Unknown',
                        'genre': 'Unknown',
                        'views': 0,
                        'source_url': movie_url
                    })
                    print(f"    ✅ Added: {title[:40]}")
                else:
                    print(f"    ❌ No embed URL found for: {title[:40]}")
                
                # Be polite - don't hammer the server
                time.sleep(0.5)
            
            # Check if there's a next page button
            next_button = soup.find('a', string=re.compile(r'Next|»|→'))
            if not next_button:
                break
                
    except Exception as e:
        print(f"❌ Error scraping {category_url}: {e}")
    
    return movies

def main():
    """Main scraping function"""
    print("=" * 60)
    print("🎬 RTALLY MOVIE SCRAPER")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Categories to scrape: {len(CATEGORIES)}")
    print("-" * 60)
    
    all_movies = []
    
    for category in CATEGORIES:
        movies = scrape_category(category, max_pages=2)  # Adjust max_pages as needed
        print(f"📊 Found {len(movies)} movies in {category}")
        all_movies.extend(movies)
        time.sleep(1)
    
    print("\n" + "=" * 60)
    print(f"📊 Total movies scraped: {len(all_movies)}")
    
    # Load existing videos
    try:
        with open('videos.json', 'r') as f:
            existing_videos = json.load(f)
        print(f"📁 Existing videos: {len(existing_videos)}")
    except:
        existing_videos = {}
        print("📁 No existing videos.json found")
    
    # Add new movies
    added_count = 0
    for movie in all_movies:
        if movie['id'] not in existing_videos:
            existing_videos[movie['id']] = {
                'title': movie['title'],
                'category': movie['category'],
                'embed_url': movie['embed_url'],
                'rating': movie['rating'],
                'year': movie['year'],
                'language': movie['language'],
                'genre': movie['genre'],
                'views': 0
            }
            added_count += 1
            print(f"➕ Added: {movie['title']}")
    
    # Save
    with open('videos.json', 'w') as f:
        json.dump(existing_videos, f, indent=2)
    
    print("\n" + "=" * 60)
    print(f"✅ Done! Added {added_count} new movies from Rtally")
    print(f"📁 Total movies in videos.json: {len(existing_videos)}")
    print("=" * 60)

if __name__ == '__main__':
    main()
