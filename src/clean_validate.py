
import json
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)


# ---------------- File paths ----------------

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

RAW_FILE = OUTPUT_DIR / "books-raw.json"
CLEAN_FILE = OUTPUT_DIR / "books.json"
ERROR_FILE = OUTPUT_DIR / "errors.json"
REPORT_FILE = OUTPUT_DIR / "run-report.json"


# ---------------- Validation schema ----------------

class BookRecord(BaseModel):
    model_config = ConfigDict(strict=True)

    title: str = Field(min_length=1)
    product_url: str = Field(min_length=1)
    price_text: str = Field(min_length=1)
    price_gbp: float = Field(ge=0)

    availability_text: str = Field(min_length=1)
    rating_text: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)

    description: Optional[str] = None
    source_page: int = Field(ge=1, le=3)
    fetched_at: str = Field(min_length=1)

    @field_validator("product_url")
    @classmethod
    def validate_product_url(cls, value):
        parsed = urlparse(value)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "product_url must be a valid HTTP or HTTPS URL"
            )

        return value

    @field_validator("fetched_at")
    @classmethod
    def validate_timestamp(cls, value):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                "fetched_at must be a valid ISO timestamp"
            )

        return value


# ---------------- Cleaning ----------------

RATING_MAP = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}


def clean_record(record):
    """Clean and normalize one raw book record."""

    if not isinstance(record, dict):
        raise ValueError("Record must be a JSON object")

    cleaned = record.copy()

    # Remove unnecessary whitespace.
    for field in [
        "title",
        "product_url",
        "price_text",
        "availability_text",
    ]:
        value = cleaned.get(field)

        if isinstance(value, str):
            cleaned[field] = value.strip()

    # Normalize common encoding errors in the pound symbol.
    price_text = cleaned.get("price_text")

    if not isinstance(price_text, str):
        raise ValueError("price_text must be a string")

    price_text = price_text.replace("Ã‚Â£", "£")
    price_text = price_text.replace("Â£", "£")
    price_text = price_text.replace("Ã‚", "")

    # Convert price text, e.g. £51.77, to a numeric value.
    match = re.fullmatch(
        r"\s*£\s*([\d,]+(?:\.\d{1,2})?)\s*",
        price_text,
    )

    if not match:
        raise ValueError(
            f"Invalid price format: {cleaned['price_text']!r}"
        )

    cleaned["price_gbp"] = float(
        match.group(1).replace(",", "")
    )

    # Convert rating words to numbers.
    rating_text = cleaned.get("rating_text")

    if rating_text is None:
        cleaned["rating"] = None
    elif rating_text in RATING_MAP:
        cleaned["rating"] = RATING_MAP[rating_text]
    else:
        raise ValueError(
            f"Invalid rating text: {rating_text!r}"
        )

    # Convert empty descriptions to None.
    description = cleaned.get("description")

    if isinstance(description, str):
        cleaned["description"] = description.strip() or None

    return cleaned


# ---------------- Run report ----------------

def update_run_report(valid_count, invalid_count):
    """Update validation counts in the existing run report."""

    if not REPORT_FILE.exists():
        return

    report = json.loads(
        REPORT_FILE.read_text(encoding="utf-8")
    )

    report["valid_records"] = valid_count
    report["invalid_records"] = invalid_count

    REPORT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------- Main validation process ----------------

def main():
    if not RAW_FILE.exists():
        print(f"Error: Raw data file not found: {RAW_FILE}")
        return

    with RAW_FILE.open("r", encoding="utf-8") as file:
        raw_records = json.load(file)

    if not isinstance(raw_records, list):
        raise ValueError(
            "books-raw.json must contain a JSON list"
        )

    valid_records = []
    invalid_records = []

    for index, raw in enumerate(raw_records, start=1):
        try:
            cleaned = clean_record(raw)
            validated = BookRecord(**cleaned)

            valid_records.append(validated.model_dump())

        except (ValueError, ValidationError) as error:
            invalid_records.append({
                "record_number": index,
                "product_url": (
                    raw.get("product_url")
                    if isinstance(raw, dict)
                    else None
                ),
                "reason": str(error),
                "record": raw,
            })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    CLEAN_FILE.write_text(
        json.dumps(
            valid_records,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ERROR_FILE.write_text(
        json.dumps(
            invalid_records,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Update the report with the latest validation results.
    update_run_report(
        len(valid_records),
        len(invalid_records),
    )

    print("\n--- Cleaning and Validation Summary ---")
    print("Raw records:", len(raw_records))
    print("Valid records:", len(valid_records))
    print("Invalid records:", len(invalid_records))
    print("Valid output:", CLEAN_FILE)
    print("Error output:", ERROR_FILE)


if __name__ == "__main__":
    main()
