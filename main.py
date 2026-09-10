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
  products(first: 1, query: "tag:single") {
    nodes {
      title
      tags
    }
  }
}
"""

result = run_graphql_query(SHOP, access_token, test_query)
print(result)
