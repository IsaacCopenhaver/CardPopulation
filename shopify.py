import sys
import requests


def get_access_token(SHOP, CLIENT_ID, CLIENT_SECRET):
    if not SHOP or not CLIENT_ID or not CLIENT_SECRET:
        print(
            "Missing required env vars. Copy .env.example to .env and fill in your values."
        )
        sys.exit(1)

    response = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (compatible; MyShopifyApp/1.0)",
            "Accept": "application/json",
        },
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )

    if not response.ok:
        raise Exception(
            f"Token request failed ({response.status_code}): {response.text}"
        )

    access_token = response.json()["access_token"]

    return access_token


def run_graphql_query(SHOP, access_token, query):
    response = requests.post(
        f"https://{SHOP}/admin/api/2026-04/graphql.json",
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        },
        json={"query": query},
    )

    if not response.ok:
        raise Exception(
            f"GraphQL request failed ({response.status_code}): {response.text}"
        )

    response_data = response.json()
    if "errors" in response_data:
        raise Exception(f"GraphQL query returned errors: {response_data['errors']}")
    
    return response_data