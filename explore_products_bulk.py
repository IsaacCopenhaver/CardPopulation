import os
from dotenv import load_dotenv

from shopify import (
    get_access_token,
    start_bulk_operation,
    poll_bulk_operation,
    download_bulk_results,
)


load_dotenv()

SHOP = os.getenv("SHOP")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

access_token = get_access_token(SHOP, CLIENT_ID, CLIENT_SECRET)

bulk_query = """
{
  products(query: "tag:single") {
    edges {
      node {
        id
        legacyResourceId
        title
        tags
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

bulk_operation = start_bulk_operation(SHOP, access_token, bulk_query)
print(f"Started bulk operation {bulk_operation['id']} (status={bulk_operation['status']})")

print("Polling until it finishes...")
completed = poll_bulk_operation(SHOP, access_token)
print(f"Done: {completed['objectCount']} objects, url={completed['url']}")

products = download_bulk_results(completed["url"])
print(f"Downloaded and parsed {len(products)} rows")

print("\n--- Testing printing the first 5 products ---")
for i, product in enumerate(products[:5]):
    print(f"Product {i}: {product}")

print("\n--- Testing printing a specific card Mask Mother using a loop ---")
for row in products:
    if row["title"].startswith("Mask Mother"):
        print(row)
        break

print("\n--- Testing printing the first product with a cardName ---")
for i, row in enumerate(products):
    if row["cardName"] is not None:
        print(f"row/product #{i}: {row})")
        break