
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timezone
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
    "User-Agent": "PoliteScraper/1.0 (educational project)"
}

MAX_PAGES = 3
REQUEST_DELAY = 0.5

stats = {
    "pages_fetched": 0,
    "cache_hits": 0,
    "failed_urls": [],
}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def fetch_with_retry(url):
    """Retry a timeout or HTTP 5xx error once."""
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=10,
            )

            # Retry server errors once, but not 403 or 404.
            if 500 <= response.status_code <= 599:
                if attempt == 0:
                    print("Server error; retrying once:", url)
                    time.sleep(1)
                    continue

            response.raise_for_status()
            stats["pages_fetched"] += 1
            return response.text

        except requests.Timeout:
            if attempt == 0:
                print("Timeout; retrying once:", url)
                time.sleep(1)
                continue
            raise

    raise requests.RequestException(
        f"Request failed after retry: {url}"
    )


def get_cached_page(url, cache_file):
    """Read cached HTML or fetch and cache it."""
    global_last_request = getattr(get_cached_page, "last_request", 0)

    if cache_file.exists():
        stats["cache_hits"] += 1
        return cache_file.read_text(encoding="utf-8"), False

    # Keep at least 500 ms between real requests.
    elapsed = time.monotonic() - global_last_request
    if global_last_request and elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

    try:
        html = fetch_with_retry(url)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(html, encoding="utf-8")
        get_cached_page.last_request = time.monotonic()
        return html, True
    except requests.RequestException as error:
        stats["failed_urls"].append({
            "url": url,
            "reason": str(error),
        })
        print("Failed page; skipping:", url, error)
        return None, False


def extract_book_links(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for book in soup.select("article.product_pod"):
        link = book.select_one("h3 a")
        if link and link.get("href"):
            links.append(urljoin(page_url, link["href"]))

    return list(dict.fromkeys(links))


def get_next_page_url(html, current_url):
    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.select_one("li.next a")

    if next_link and next_link.get("href"):
        return urljoin(current_url, next_link["href"])

    return None


def discover_books():
    current_url = START_URL
    all_links = []

    for page_number in range(1, MAX_PAGES + 1):
        if not current_url:
            break

        cache_file = CACHE_DIR / f"catalogue-page-{page_number}.html"
        html, _ = get_cached_page(current_url, cache_file)

        if html is None:
            current_url = None
            continue

        links = extract_book_links(html, current_url)
        all_links.extend(links)
        print(f"Catalogue page {page_number}: {len(links)} books")

        current_url = get_next_page_url(html, current_url)

    unique_links = list(dict.fromkeys(all_links))
    print("Unique book URLs:", len(unique_links))
    return unique_links


def extract_book_details(html, product_url, source_page):
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
                item for item in rating.get("class", [])
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


def scrape_books(book_urls):
    records = []

    for index, url in enumerate(book_urls, start=1):
        cache_file = DETAIL_CACHE_DIR / f"book-{index}.html"
        record_file = DETAIL_CACHE_DIR / f"book-{index}.json"

        html, fetched_now = get_cached_page(url, cache_file)
        if html is None:
            continue

        try:
            if not fetched_now and record_file.exists():
                # Preserve the original fetch timestamp on cache hits.
                record = json.loads(
                    record_file.read_text(encoding="utf-8")
                )
            else:
                source_page = ((index - 1) // 20) + 1
                record = extract_book_details(
                    html, url, source_page
                )
                record_file.write_text(
                    json.dumps(record, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

            records.append(record)

        except (ValueError, json.JSONDecodeError) as error:
            stats["failed_urls"].append({
                "url": url,
                "reason": f"Could not process cached record: {error}",
            })
            print("Failed to process:", url, error)

    return records


def write_report(start_time, started_at):
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

    # Read validation counts if clean_validate.py has already run.
    clean_file = OUTPUT_DIR / "books.json"
    error_file = OUTPUT_DIR / "errors.json"

    if clean_file.exists():
        try:
            report["valid_records"] = len(
                json.loads(clean_file.read_text(encoding="utf-8"))
            )
        except (ValueError, OSError):
            pass

    if error_file.exists():
        try:
            report["invalid_records"] = len(
                json.loads(error_file.read_text(encoding="utf-8"))
            )
        except (ValueError, OSError):
            pass

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
    started_at = now_utc()
    start_time = time.monotonic()

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        book_urls = discover_books()
        records = scrape_books(book_urls)

        RAW_FILE.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\nBook URLs discovered:", len(book_urls))
        print("Raw records saved:", len(records))

    finally:
        # Ensure a report is written even if an unexpected error occurs.
        write_report(start_time, started_at)


if __name__ == "__main__":
    main()
