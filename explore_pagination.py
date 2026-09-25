import os
from dotenv import load_dotenv

from shopify import get_access_token, run_graphql_query

load_dotenv()

SHOP = os.getenv("SHOP")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

access_token = get_access_token(SHOP, CLIENT_ID, CLIENT_SECRET)

PAGE_SIZE = 3

def fetch_page(cursor=None):
    after_clause = f', after: "{cursor}"' if cursor else ""
    query = f"""
    {{
      products(
        first: {PAGE_SIZE}{after_clause}
        query: "tag:single"
        sortKey: CREATED_AT
        reverse: true
      ) {{
        edges {{
          cursor
          node {{
            legacyResourceId
            title
            tags
            cardName: metafield(namespace: "custom", key: "card_name") {{
              value
            }}
            rarity: metafield(namespace: "custom", key: "rarity") {{
              value
            }}
            collectorNumber: metafield(namespace: "custom", key: "number") {{
              value
            }}
            tcgProductId: metafield(namespace: "custom", key: "productId") {{
              value
            }}
            categoryId: metafield(namespace: "custom", key: "category_id") {{
              value
            }}
            gameName: metafield(namespace: "custom", key: "game") {{
              value
            }}
            groupId: metafield(namespace: "custom", key: "group_id") {{
              value
            }}
            setName: metafield(namespace: "custom", key: "set") {{
              value
            }}
            pricing: metafield(namespace: "custom", key: "pricing") {{
              value
            }}
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
    """
    result = run_graphql_query(SHOP, access_token, query)
    return result["data"]["products"]


# fetching the very first page, by hand
print("=== Step 1: first page ===")
page = fetch_page()
for edge in page["edges"]:
    print(f"this page's edges: {edge}")

# manually taking that cursor and ask for the next page
print("\n=== Step 2: second page, using endCursor from step 1 ===")
next_cursor = page["pageInfo"]["endCursor"]
page_2 = fetch_page(cursor=next_cursor)
for edge in page_2["edges"]:
        print(f"this page's edges: {edge}")

# turning the manual step-2 move into a loop
print("\n=== Step 3: looping through a few pages automatically ===")
cursor = None
for page_number in range(1, 4):  # capped at 3 pages for this experiment
    page = fetch_page(cursor)
    print(f"\n--- page {page_number} ---")
    for i, edge in enumerate(page["edges"]):
        print(f"\n  SINGLE NUMBER {i + 1}")
        print(f"  cursor={edge['cursor']}")
        print(f"  id={edge['node']['legacyResourceId']}")
        print(f"  title={edge['node']['title']}")
        print(f"  tags={edge['node']['tags']}")
        print(f"  cardName={edge['node']['cardName']}")
        print(f"  rarity={edge['node']['rarity']}")
        print(f"  collectorNumber={edge['node']['collectorNumber']}")
        print(f"  gameName={edge['node']['gameName']}")
        print(f"  groupId={edge['node']['groupId']}")
        print(f"  setName={edge['node']['setName']}")
        print(f"  pricing={edge['node']['pricing']}")
        print(f"  tcgProductId={edge['node']['tcgProductId']}")
        print(f"  categoryId={edge['node']['categoryId']}")

    if not page["pageInfo"]["hasNextPage"]:
        print("(reached the last page)")
        break
    cursor = page["pageInfo"]["endCursor"]
