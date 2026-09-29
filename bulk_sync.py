import os

from dotenv import load_dotenv

from shopify import (
    get_access_token,
    start_bulk_operation,
    poll_bulk_operation,
    download_bulk_results,
)
from database import build_card_data, get_database_connection, insert_card


BULK_QUERY = """
{
  products(query: "tag:single") {
    edges {
      node {
        legacyResourceId
        title
        cardName: metafield(namespace: "custom", key: "card_name") {
          value
        }
        rarity: metafield(namespace: "custom", key: "rarity") {
          value
        }
        collectorNumber: metafield(namespace: "custom", key: "number") {
          value
        }
        tcgProductId: metafield(namespace: "custom", key: "productId") {
          value
        }
        categoryId: metafield(namespace: "custom", key: "category_id") {
          value
        }
        gameName: metafield(namespace: "custom", key: "game") {
          value
        }
        groupId: metafield(namespace: "custom", key: "group_id") {
          value
        }
        setName: metafield(namespace: "custom", key: "set") {
          value
        }
        pricing: metafield(namespace: "custom", key: "pricing") {
          value
        }
      }
    }
  }
}
"""


def sync_products(conn, products):
    """Push every product in products into conn. Every product is assumed to
    be a real card single -- tag:single is the source of truth, nothing here
    second-guesses that. Returns a count of what happened to each one instead
    of raising on the expected case (missing the metafields build_card_data
    needs) -- but a genuine DB/API failure from insert_card still propagates,
    it is not caught here.
    """
    counts = {
        "skipped_missing_metadata": 0,
        "inserted": 0,
        "already_existing": 0,
    }

    for product in products:
        try:
            card_data = build_card_data(product)
        except (KeyError, TypeError):
            # KeyError: a metafield is absent from the response entirely.
            # TypeError: a metafield exists as a key but its value is None,
            # e.g. product["categoryId"]["value"] when categoryId is None.
            counts["skipped_missing_metadata"] += 1
            continue

        was_inserted = insert_card(conn, card_data)
        if was_inserted:
            counts["inserted"] += 1
        else:
            counts["already_existing"] += 1

    return counts


def run_bulk_sync():
    load_dotenv()

    SHOP = os.getenv("SHOP")
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    DATABASE_URL = os.getenv("DATABASE_URL")

    access_token = get_access_token(SHOP, CLIENT_ID, CLIENT_SECRET)

    bulk_operation = start_bulk_operation(SHOP, access_token, BULK_QUERY)
    print(f"Started bulk operation {bulk_operation['id']}")

    completed = poll_bulk_operation(SHOP, access_token)
    print(f"Bulk operation completed: {completed['objectCount']} objects")

    products = download_bulk_results(completed["url"])
    print(f"Downloaded {len(products)} rows")

    conn = get_database_connection(DATABASE_URL)
    try:
        counts = sync_products(conn, products)
    finally:
        conn.close()

    return counts


if __name__ == "__main__":
    print(run_bulk_sync())
