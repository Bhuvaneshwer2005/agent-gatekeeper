# Loads the merchant's product catalog from the static JSON file.
#
# The catalog is static for now, so there's no caching here - each call
# re-reads and re-validates the file. That keeps the JSON file as the one
# source of truth and means an edit to it takes effect immediately, which
# matters more at this stage than shaving a few milliseconds off a read.

import json
from pathlib import Path
from typing import List

from app.models.product import Product

CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "catalog.json"


def get_catalog() -> List[Product]:
    """Read and validate the product catalog from disk."""
    raw_items = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return [Product(**item) for item in raw_items]
