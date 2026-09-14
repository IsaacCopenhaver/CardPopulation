import os
from dotenv import load_dotenv
from shopify import get_access_token, run_graphql_query

load_dotenv()

SHOP = os.getenv("SHOP")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

access_token = get_access_token(SHOP, CLIENT_ID, CLIENT_SECRET)

test_query = """
{
  product(id: "gid://shopify/Product/8042708992090") {
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
"""

result = run_graphql_query(SHOP, access_token, test_query)
print(result)
