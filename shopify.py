import json
import sys
import time

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


def start_bulk_operation(SHOP, access_token, bulk_query):
    """Kick off an async bulk query job. bulk_query is the *inner* GraphQL
    query (e.g. "{ products { edges { node { id } } } }") with no first/after
    -- Shopify paginates the whole thing server-side. Only one bulk operation
    can be running per shop at a time; a second call while one is in flight
    comes back as a userError, not an exception, so we raise on that here.
    """
    mutation = f'''
    mutation {{
      bulkOperationRunQuery(
        query: """
        {bulk_query}
        """
      ) {{
        bulkOperation {{
          id
          status
        }}
        userErrors {{
          field
          message
        }}
      }}
    }}
    '''

    result = run_graphql_query(SHOP, access_token, mutation)
    payload = result["data"]["bulkOperationRunQuery"]
    if payload["userErrors"]:
        raise Exception(f"Bulk operation failed to start: {payload['userErrors']}")

    return payload["bulkOperation"]

CURRENT_BULK_OPERATION_QUERY = """
{
  currentBulkOperation {
    id
    status
    errorCode
    objectCount
    url
    partialDataUrl
  }
}
"""

def poll_bulk_operation(SHOP, access_token, poll_interval=2, timeout=300):
    """Block until the shop's current bulk operation finishes, checking every
    poll_interval seconds. Returns the finished operation (status COMPLETED),
    including the download url. Raises if it fails/is canceled/expires, or if
    it's still running after timeout seconds.
    """
    elapsed = 0
    while elapsed < timeout:
        result = run_graphql_query(SHOP, access_token, CURRENT_BULK_OPERATION_QUERY)
        operation = result["data"]["currentBulkOperation"]

        if operation is None:
            raise Exception("No bulk operation found for this shop.")
        if operation["status"] == "COMPLETED":
            return operation
        if operation["status"] in ("FAILED", "CANCELED", "EXPIRED"):
            raise Exception(
                f"Bulk operation ended with status {operation['status']} "
                f"(errorCode={operation.get('errorCode')})"
            )

        time.sleep(poll_interval)
        elapsed += poll_interval

    raise TimeoutError(f"Bulk operation still running after {timeout}s")


def download_bulk_results(url):
    """Download and parse a completed bulk operation's JSONL output. url is
    None when the query matched zero objects -- Shopify doesn't create a file
    for an empty result, so we return an empty list instead of requesting it.
    """
    if url is None:
        return []

    response = requests.get(url)
    if not response.ok:
        raise Exception(f"Failed to download bulk results ({response.status_code})")

    return [json.loads(line) for line in response.text.splitlines() if line]