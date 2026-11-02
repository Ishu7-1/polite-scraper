# The Polite Scraper

A Python web-scraping project that collects book information from [Books to Scrape](https://books.toscrape.com/), cleans and validates the collected data, and saves structured JSON outputs. The project emphasizes responsible request handling, caching, data quality, and fault tolerance.

## 1. Project Objective

The objective is to scrape the first three catalogue pages of Books to Scrape, collect information from 60 book detail pages, normalize the collected data, validate each record, and report failures without losing successfully processed records.

## 2. Technologies Used

- **Python** — main programming language
- **Requests** — HTTP requests and response handling
- **Beautiful Soup** — HTML parsing and data extraction
- **Regular Expressions (`re`)** — price normalization
- **Pydantic** — data validation
- **JSON** — storing raw data, cleaned data, errors, and run reports
- **Git** — version control

## 3. Project Structure

```text
scraper/
├── src/
│   ├── main.py
│   └── clean_validate.py
├── cache/
│   ├── catalogue-page-1.html
│   ├── catalogue-page-2.html
│   ├── catalogue-page-3.html
│   └── books/
├── output/
│   ├── books-raw.json
│   ├── books.json
│   ├── errors.json
│   └── run-report.json
├── .gitignore
└── readme.md
```

**Note:** The `cache/` directory contains downloaded HTML pages and is excluded from version control. The `output/` directory contains generated results.

## 4. Complete Workflow

### Stage 1: Discover Catalogue Pages

The scraper starts at the Books to Scrape homepage and visits the first three catalogue pages.

For each catalogue page, it:

1. Fetches the HTML or reads it from the local cache.
2. Parses the HTML using Beautiful Soup.
3. Finds book links inside product listing elements.
4. Converts relative links into absolute URLs.
5. Collects unique book URLs.
6. Follows the next-page link until three catalogue pages have been processed.

Each catalogue page contains 20 books, giving 60 unique book URLs.

### Stage 2: Fetch Book Details

The scraper visits the detail page for each discovered book.

It extracts the following raw fields:

- `title` — book title
- `product_url` — absolute URL of the book
- `price_text` — original price text
- `availability_text` — stock availability information
- `rating_text` — rating written as a word
- `description` — book description, or `null` if missing
- `source_page` — catalogue page number
- `fetched_at` — timestamp of extraction

The extracted records are saved to `output/books-raw.json`.

### Stage 3: Responsible Request Handling

The scraper uses a descriptive User-Agent and a request timeout.

It also:

- Checks HTTP response status codes.
- Waits at least 500 milliseconds between real requests.
- Retries a timeout or HTTP 5xx response once after a short delay.
- Avoids retrying HTTP 403 and 404 responses.
- Records failed URLs and their error reasons.
- Uses cached HTML during development to avoid unnecessary network requests.

The site's `robots.txt` endpoint returned HTTP 404 during the check. This response does not establish permission to scrape, so the site's applicable access rules should be checked before running live requests.

### Stage 4: Cache Management

Downloaded HTML pages are stored locally in the `cache/` directory.

Before making a network request, the scraper checks whether the required HTML file is already cached.

- If the cache exists, the saved HTML is reused.
- If the cache does not exist, the scraper fetches the page and saves its HTML.
- Cached book records can also be reused to avoid unnecessary reprocessing.

This makes development faster and reduces repeated requests to the website.

The cache directory is excluded from Git because it contains downloaded website content.

### Stage 5: Clean and Normalize Data

The `clean_validate.py` script reads `output/books-raw.json` and normalizes each record.

**Price normalization**

The original price text is preserved, and a numeric `price_gbp` field is created.

For example:

```text
price_text: "£51.77"
price_gbp: 51.77
```

Common encoding issues affecting the pound symbol are handled before parsing the price.

**Rating normalization**

Word-based ratings are converted to numbers:

| Raw rating | Numeric rating |
|---|---:|
| One | 1 |
| Two | 2 |
| Three | 3 |
| Four | 4 |
| Five | 5 |

Missing descriptions are represented as `null`. Text fields are trimmed to remove unnecessary surrounding whitespace.

### Stage 6: Validate Records

Pydantic validates the cleaned data against the `BookRecord` schema.

Validation checks include:

- Required fields and non-empty text values
- Valid HTTP or HTTPS product URLs
- Non-negative numeric prices
- Ratings within the range of 1–5
- Catalogue page numbers within the range of 1–3
- Valid ISO-formatted timestamps
- Correct field types

Valid records are written to `output/books.json`.

Invalid records are written to `output/errors.json`, including the record number, product URL when available, original record, and validation error reason.

A failed record does not prevent other records from being processed.

### Stage 7: Error Handling and Run Reporting

The scraper handles failed page requests without terminating the entire run.

It records information such as:

- Start time
- Total duration
- Number of pages fetched from the network
- Number of cache hits
- Number of valid records
- Number of invalid records
- Number of failed pages
- Failure URLs and reasons

This information is stored in `output/run-report.json`.

A deliberately invalid URL can be used to test whether the scraper records a failure while preserving successful records.

### Stage 8: Repeatability

The project uses caching and structured JSON output to make development and repeated processing easier.

The expected catalogue contains 60 unique books. With all required pages available and no validation errors, the expected output is 60 valid records and zero invalid records.

## 5. Installation

Python 3.10 or later is recommended.

Install the required packages:

```bash
python -m pip install requests beautifulsoup4 pydantic
```

Clone the repository or navigate to the project directory.

## 6. How to Run

Run these commands from the project root.

**Step 1: Collect raw book data**

```bash
python src/main.py
```

This discovers book URLs, retrieves or reuses cached pages, extracts details, and writes `output/books-raw.json`.

**Step 2: Clean and validate the data**

```bash
python src/clean_validate.py
```

This generates:

- `output/books.json`
- `output/errors.json`

It also updates the validation counts in `output/run-report.json`, when that report exists.

## 7. Output Files

| File | Purpose |
|---|---|
| `books-raw.json` | Raw extracted book records |
| `books.json` | Cleaned and validated records |
| `errors.json` | Invalid records and error reasons |
| `run-report.json` | Scraping statistics and failed-page details |

These files are generated by running the scripts. They do not need to be manually edited.

## 8. Testing

The project can be checked using the following tests:

1. Confirm that three catalogue pages produce 60 unique book URLs.
2. Confirm that the raw JSON contains the expected extracted fields.
3. Run the cleaning and validation script and inspect the valid and invalid record counts.
4. Run the scraper again to verify that cached HTML is reused.
5. Test a deliberately invalid URL and verify that the failure appears in the run report.
6. Confirm that a failed page does not prevent the other book records from being processed.
7. Check that `cache/` is ignored by Git.

Example of a successful validation result:

```text
Raw records: 60
Valid records: 60
Invalid records: 0
```

The exact network request and cache-hit counts depend on whether pages have already been cached.

## 9. Version Control

The `.gitignore` file excludes Python-generated files, virtual environments, cached pages, and environment secrets.

The project source files and README should be committed to Git. Only the sample output files required for submission should be selected for version control; cached HTML should not be committed.

## 10. Limitations

- The extraction logic is tailored to the current HTML structure of Books to Scrape.
- Website changes may require changes to the HTML selectors.
- Network failures can result in fewer raw records in a particular run.
- A `robots.txt` 404 response does not establish permission to scrape.
- This is an educational scraping project, not a production crawler.

## 11. Conclusion

This project demonstrates a structured web-scraping pipeline, from discovering catalogue links and extracting book details to caching, data normalization, Pydantic validation, and failure reporting.

It emphasizes responsible request handling, reusable cached data, clear error logs, and separation between raw and validated output.
## Responsible Scraping and Ethics

This project is intended for educational practice using Books to Scrape, a website designed for scraping exercises. Before scraping a website, check its `robots.txt`, terms of service, and applicable usage rules. Keep request rates low, use caching to avoid unnecessary requests, and collect only the information required for the task. If an official API is available, prefer using it. Never bypass logins, paywalls, or access restrictions.

I will not reuse this code on another site without checking its rules and terms first.
### Why a Browser Is Not Required

Books to Scrape provides the required book information directly in its server-sent HTML. Therefore, Python Requests can download the HTML and Beautiful Soup can extract the information without executing JavaScript. Using browser automation would add unnecessary processing time, memory usage, and complexity to this project.
### Sample Run Report

The following report was generated during a cached run and a failure-handling test. The intentionally invalid URL was used to verify that a failed request is recorded without affecting the 60 successfully validated records.

```json
{
  "start_time": "2026-10-28T08:53:33.687016+00:00",
  "duration_seconds": 0.86,
  "pages_fetched": 0,
  "cache_hits": 63,
  "valid_records": 60,
  "invalid_records": 0,
  "failed_pages": 1,
  "failures": [
    {
      "url": "https://example.invalid/fake-book.html",
      "reason": "Intentionally invalid test URL; request failed as expected"
    }
  ]
}
```

This is a cached-run example, not a fresh network scrape. The `pages_fetched` value is zero because the required pages were already cached.