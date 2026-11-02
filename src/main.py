
from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
import hashlib
import json
import time

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "cache"
DETAIL_CACHE_DIR = CACHE_DIR / "books"
OUTPUT_DIR = BASE_DIR / "output"

RAW_FILE = OUTPUT_DIR / "books-raw.json"
REPORT_FILE = OUTPUT_DIR / "run-report.json"

START_URL = "https://books.toscrape.com/"
HEADERS = {
    "User-Agent": (
        "PoliteScraper/1.0 "
        "(educational project; "
        "https://github.com/Ishu7-1/polite-scraper)"
    )
}

MAX_PAGES = 3
REQUEST_DELAY = 0.5
REQUEST_TIMEOUT = 10
MAX_ATTEMPTS = 2

stats = {
    "pages_fetched": 0,
    "cache_hits": 0,
    "failed_urls": [],
}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def record_failure(url, reason):
    stats["failed_urls"].append({
        "url": url,
        "reason": str(reason),
    })


def fetch_with_retry(url):
    """Fetch a page, retrying a timeout or HTTP 5xx once."""
    last_request_time = getattr(fetch_with_retry, "last_request_time", 0)

    for attempt in range(MAX_ATTEMPTS):
        elapsed = time.monotonic() - last_request_time

        if last_request_time and elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            fetch_with_retry.last_request_time = time.monotonic()
            last_request_time = fetch_with_retry.last_request_time

            if 500 <= response.status_code <= 599:
                if attempt == 0:
                    print("Server error; retrying once:", url)
                    time.sleep(1)
                    continue

            response.raise_for_status()

            # Use the response's declared encoding, or detect one if missing.
            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding

            stats["pages_fetched"] += 1
            return response.text

        except requests.Timeout:
            fetch_with_retry.last_request_time = time.monotonic()
            last_request_time = fetch_with_retry.last_request_time

            if attempt == 0:
                print("Timeout; retrying once:", url)
                time.sleep(1)
                continue
            raise

    raise requests.RequestException(
        f"Request failed after {MAX_ATTEMPTS} attempts: {url}"
    )


def get_cached_page(url, cache_file):
    """Read cached HTML or fetch it and save it locally."""
    if cache_file.exists():
        stats["cache_hits"] += 1
        return cache_file.read_text(encoding="utf-8"), False

    try:
        html = fetch_with_retry(url)

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(html, encoding="utf-8")

        return html, True

    except requests.RequestException as error:
        record_failure(url, error)
        print("Failed page; skipping:", url, error)
        return None, False


def extract_book_links(html, page_url):
    """Extract unique absolute book URLs from a catalogue page."""
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for book in soup.select("article.product_pod"):
        link = book.select_one("h3 a")

        if link and link.get("href"):
            absolute_url = urljoin(page_url, link["href"])
            links.append(absolute_url)

    return list(dict.fromkeys(links))


def get_next_page_url(html, current_url):
    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.select_one("li.next a")

    if next_link and next_link.get("href"):
        return urljoin(current_url, next_link["href"])

    return None


def discover_books():
    """Discover books on the first three catalogue pages."""
    current_url = START_URL
    book_sources = {}

    for page_number in range(1, MAX_PAGES + 1):
        if not current_url:
            break

        cache_file = CACHE_DIR / f"catalogue-page-{page_number}.html"
        html, _ = get_cached_page(current_url, cache_file)

        if html is None:
            # Do not pretend later pages were successfully processed.
            print(f"Catalogue page {page_number} failed.")
            current_url = None
            continue

        links = extract_book_links(html, current_url)

        for url in links:
            book_sources.setdefault(url, page_number)

        print(f"Catalogue page {page_number}: {len(links)} books")
        current_url = get_next_page_url(html, current_url)

    print("Unique book URLs:", len(book_sources))
    return book_sources


def extract_book_details(html, product_url, source_page):
    """Extract the required raw fields from a book detail page."""
    soup = BeautifulSoup(html, "html.parser")

    title = soup.select_one("div.product_main h1")
    price = soup.select_one("p.price_color")
    availability = soup.select_one("p.instock.availability")
    rating = soup.select_one("div.product_main p.star-rating")
    description = soup.select_one("#product_description + p")

    rating_text = None
    if rating:
        rating_text = next(
            (
                item
                for item in rating.get("class", [])
                if item in {"One", "Two", "Three", "Four", "Five"}
            ),
            None,
        )

    return {
        "title": title.get_text(strip=True) if title else None,
        "product_url": product_url,
        "price_text": price.get_text(strip=True) if price else None,
        "availability_text": (
            availability.get_text(" ", strip=True)
            if availability else None
        ),
        "rating_text": rating_text,
        "description": (
            description.get_text(strip=True) if description else None
        ),
        "source_page": source_page,
        "fetched_at": now_utc(),
    }


def cache_key_for_url(url):
    """Create a stable cache key from the complete product URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def scrape_books(book_sources):
    """Scrape each unique URL using URL-based cache filenames."""
    records = []

    for url, source_page in book_sources.items():
        cache_key = cache_key_for_url(url)
        cache_file = DETAIL_CACHE_DIR / f"{cache_key}.html"
        record_file = DETAIL_CACHE_DIR / f"{cache_key}.json"

        html, fetched_now = get_cached_page(url, cache_file)

        if html is None:
            continue

        try:
            if not fetched_now and record_file.exists():
                record = json.loads(
                    record_file.read_text(encoding="utf-8")
                )

                # Never reuse a record for a different product URL.
                if record.get("product_url") != url:
                    record = extract_book_details(
                        html, url, source_page
                    )
                    record_file.write_text(
                        json.dumps(
                            record, indent=2, ensure_ascii=False
                        ),
                        encoding="utf-8",
                    )
            else:
                record = extract_book_details(
                    html, url, source_page
                )
                record_file.write_text(
                    json.dumps(record, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

            records.append(record)

        except (ValueError, OSError) as error:
            record_failure(
                url,
                f"Could not process cached record: {error}",
            )
            print("Failed to process:", url, error)

    return records


def write_report(start_time, started_at):
    """Write current scraping statistics and any existing validation counts."""
    elapsed = time.monotonic() - start_time

    report = {
        "start_time": started_at,
        "duration_seconds": round(elapsed, 2),
        "pages_fetched": stats["pages_fetched"],
        "cache_hits": stats["cache_hits"],
        "valid_records": 0,
        "invalid_records": 0,
        "failed_pages": len(stats["failed_urls"]),
        "failures": stats["failed_urls"],
    }

    # Counts are populated by clean_validate.py after validation.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nRun report saved to:", REPORT_FILE)
    print("Pages fetched:", report["pages_fetched"])
    print("Cache hits:", report["cache_hits"])
    print("Failed pages:", report["failed_pages"])


def main():
    # Reset statistics so repeated calls in one process start cleanly.
    for key in stats:
        stats[key] = [] if key == "failed_urls" else 0

    started_at = now_utc()
    start_time = time.monotonic()

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        book_sources = discover_books()
        records = scrape_books(book_sources)

        RAW_FILE.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\nBook URLs discovered:", len(book_sources))
        print("Raw records saved:", len(records))

    finally:
        write_report(start_time, started_at)


if __name__ == "__main__":
    main()
