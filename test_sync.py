import pytest
from unittest.mock import patch, MagicMock
from database import build_card_data, get_database_connection, insert_card
from shopify import (
    get_access_token,
    start_bulk_operation,
    poll_bulk_operation,
    download_bulk_results,
)
from main import run
from bulk_sync import sync_products, run_bulk_sync

# --- build_card_data ---
# Pure function, no network or database involved, so no mocking needed here,
# just real inputs and checking the real outputs.


def test_build_card_data_happy_path():
    product = {
        "legacyResourceId": "8042708992090",
        "cardName": {"value": "Kai'Sa, Survivor"},
        "rarity": {"value": "Epic"},
        "collectorNumber": {"value": "SP1/006"},
        "tcgProductId": {"value": "707648"},
        "categoryId": {"value": "89"},
        "gameName": {"value": "Riftbound"},
        "groupId": {"value": "24698"},
        "setName": {"value": "Vendetta"},
        "pricing": {"value": '{"Foil":{"market":151.5,"low":153.74}}'},
    }

    result = build_card_data(product)

    assert result["game"] == {"id": 89, "name": "Riftbound"}
    assert result["set"] == {"id": 24698, "name": "Vendetta"}
    assert result["card"]["shopifyProductId"] == "8042708992090"
    assert result["card"]["tcgProductId"] == 707648


def test_build_card_data_missing_field_raises_key_error():
    # Edge case: what if a metafield is missing entirely, e.g. an
    # uncategorized product like the ones we found earlier in Shopify?
    product = {
        "legacyResourceId": "123",
        "cardName": {"value": "Test Card"},
        # "rarity" left out on purpose
        "collectorNumber": {"value": "001"},
        "tcgProductId": {"value": "1"},
        "categoryId": {"value": "1"},
        "gameName": {"value": "Test Game"},
        "groupId": {"value": "1"},
        "setName": {"value": "Test Set"},
        "pricing": {"value": "{}"},
    }

    with pytest.raises(KeyError):
        build_card_data(product)


def test_build_card_data_non_numeric_id_raises_value_error():
    # Edge case: categoryId/groupId/tcgProductId are always strings coming
    # from GraphQL, what if one isn't actually numeric text?
    product = {
        "legacyResourceId": "123",
        "cardName": {"value": "Test Card"},
        "rarity": {"value": "Common"},
        "collectorNumber": {"value": "001"},
        "tcgProductId": {"value": "1"},
        "categoryId": {"value": "not-a-number"},
        "gameName": {"value": "Test Game"},
        "groupId": {"value": "1"},
        "setName": {"value": "Test Set"},
        "pricing": {"value": "{}"},
    }

    with pytest.raises(ValueError):
        build_card_data(product)


# --- get_access_token ---
# This one makes a real network call, so we mock requests.post instead of
# actually hitting Shopify every time we run the tests.


def test_get_access_token_missing_credentials_exits():
    # get_access_token calls sys.exit(1) when credentials are missing,
    # pytest.raises(SystemExit) is how you test that a function tries to
    # exit the program, instead of the test itself crashing.
    with pytest.raises(SystemExit):
        get_access_token(None, None, None)


@patch("shopify.requests.post")
def test_get_access_token_success(mock_post):
    # Note: we patch "shopify.requests.post", not "requests.post", because
    # we need to replace the requests.post that shopify.py actually calls,
    # not some other copy of it.
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.json.return_value = {"access_token": "fake-token-123"}
    mock_post.return_value = mock_response

    token = get_access_token("shop.myshopify.com", "id", "secret")

    assert token == "fake-token-123"


@patch("shopify.requests.post")
def test_get_access_token_failed_request_raises(mock_post):
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 400
    mock_response.text = "Bad request"
    mock_post.return_value = mock_response

    with pytest.raises(Exception):
        get_access_token("shop.myshopify.com", "id", "secret")


# --- start_bulk_operation ---
# This one wraps run_graphql_query in a mutation, so we mock that instead of
# requests.post directly -- we're testing how start_bulk_operation reacts to
# the response shape, not the HTTP layer underneath it.


@patch("shopify.run_graphql_query")
def test_start_bulk_operation_success(mock_run_graphql_query):
    mock_run_graphql_query.return_value = {
        "data": {
            "bulkOperationRunQuery": {
                "bulkOperation": {
                    "id": "gid://shopify/BulkOperation/1",
                    "status": "CREATED",
                },
                "userErrors": [],
            }
        }
    }

    operation = start_bulk_operation(
        "shop.myshopify.com", "token", "{ products { edges { node { id } } } }"
    )

    assert operation == {"id": "gid://shopify/BulkOperation/1", "status": "CREATED"}


@patch("shopify.run_graphql_query")
def test_start_bulk_operation_user_error_raises(mock_run_graphql_query):
    # A second bulk operation while one's already running comes back as a
    # userError, not an HTTP failure, so this has to be checked separately
    # from run_graphql_query's own error handling.
    mock_run_graphql_query.return_value = {
        "data": {
            "bulkOperationRunQuery": {
                "bulkOperation": None,
                "userErrors": [{"field": ["query"], "message": "already in progress"}],
            }
        }
    }

    with pytest.raises(Exception):
        start_bulk_operation(
            "shop.myshopify.com", "token", "{ products { edges { node { id } } } }"
        )


# --- poll_bulk_operation ---
# This one polls in a loop, so we also mock time.sleep -- otherwise the
# waiting/timeout tests would actually block for real seconds instead of
# running instantly.


@patch("shopify.run_graphql_query")
def test_poll_bulk_operation_completed_immediately(mock_run_graphql_query):
    mock_run_graphql_query.return_value = {
        "data": {
            "currentBulkOperation": {
                "id": "gid://shopify/BulkOperation/1",
                "status": "COMPLETED",
                "errorCode": None,
                "objectCount": "42",
                "url": "https://example.com/results.jsonl",
                "partialDataUrl": None,
            }
        }
    }

    operation = poll_bulk_operation("shop.myshopify.com", "token")

    assert operation["status"] == "COMPLETED"
    assert operation["url"] == "https://example.com/results.jsonl"


@patch("shopify.time.sleep")
@patch("shopify.run_graphql_query")
def test_poll_bulk_operation_waits_then_completes(mock_run_graphql_query, mock_sleep):
    # First check: still running. Second check: done. poll_bulk_operation
    # should sleep exactly once in between, not raise or give up early.
    mock_run_graphql_query.side_effect = [
        {"data": {"currentBulkOperation": {"status": "RUNNING"}}},
        {
            "data": {
                "currentBulkOperation": {
                    "status": "COMPLETED",
                    "url": "https://example.com/results.jsonl",
                }
            }
        },
    ]

    operation = poll_bulk_operation("shop.myshopify.com", "token", poll_interval=2)

    assert operation["status"] == "COMPLETED"
    mock_sleep.assert_called_once_with(2)


@patch("shopify.run_graphql_query")
def test_poll_bulk_operation_failed_raises(mock_run_graphql_query):
    mock_run_graphql_query.return_value = {
        "data": {
            "currentBulkOperation": {
                "status": "FAILED",
                "errorCode": "INTERNAL_SERVER_ERROR",
            }
        }
    }

    with pytest.raises(Exception):
        poll_bulk_operation("shop.myshopify.com", "token")


@patch("shopify.run_graphql_query")
def test_poll_bulk_operation_missing_operation_raises(mock_run_graphql_query):
    # currentBulkOperation is None when the shop has never run one at all.
    mock_run_graphql_query.return_value = {"data": {"currentBulkOperation": None}}

    with pytest.raises(Exception):
        poll_bulk_operation("shop.myshopify.com", "token")


@patch("shopify.time.sleep")
@patch("shopify.run_graphql_query")
def test_poll_bulk_operation_timeout_raises(mock_run_graphql_query, mock_sleep):
    # Status never changes, so this should give up once elapsed time passes
    # timeout -- mocking sleep means this test doesn't actually wait.
    mock_run_graphql_query.return_value = {
        "data": {"currentBulkOperation": {"status": "RUNNING"}}
    }

    with pytest.raises(TimeoutError):
        poll_bulk_operation("shop.myshopify.com", "token", poll_interval=1, timeout=2)


# --- download_bulk_results ---
# This one hits requests.get directly, not run_graphql_query -- the JSONL
# file lives on Shopify's CDN, not behind the GraphQL endpoint -- so we mock
# requests.get the same way get_access_token's tests mock requests.post.


def test_download_bulk_results_no_url_returns_empty_list():
    # Shopify doesn't create a file when a bulk query matches zero objects,
    # so url is None in that case -- nothing to download.
    assert download_bulk_results(None) == []


@patch("shopify.requests.get")
def test_download_bulk_results_parses_jsonl(mock_get):
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.text = '{"id": 1}\n{"id": 2}\n'
    mock_get.return_value = mock_response

    results = download_bulk_results("https://example.com/results.jsonl")

    assert results == [{"id": 1}, {"id": 2}]


@patch("shopify.requests.get")
def test_download_bulk_results_failed_request_raises(mock_get):
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 500
    mock_get.return_value = mock_response

    with pytest.raises(Exception):
        download_bulk_results("https://example.com/results.jsonl")


# --- sync_products ---
# The real ingestion loop. conn is mocked (same approach as insert_card's own
# tests) so we're only testing the loop's decisions, not a real database.


def _valid_product(shopify_id="1", title="Test Card"):
    return {
        "legacyResourceId": shopify_id,
        "title": title,
        "cardName": {"value": title},
        "rarity": {"value": "Common"},
        "collectorNumber": {"value": "001"},
        "tcgProductId": {"value": "1"},
        "categoryId": {"value": "1"},
        "gameName": {"value": "Test Game"},
        "groupId": {"value": "1"},
        "setName": {"value": "Test Set"},
        "pricing": {"value": "{}"},
    }


def test_sync_products_counts_each_outcome_separately():
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.rowcount = 1

    missing_metadata = {
        "legacyResourceId": "3",
        "title": "Balefire Dragon 129/264 ISD",
        "cardName": None,
        "rarity": None,
        "collectorNumber": None,
        "tcgProductId": None,
        "categoryId": None,
        "gameName": None,
        "groupId": None,
        "setName": None,
        "pricing": None,
    }
    valid_new = _valid_product(shopify_id="1")

    counts = sync_products(mock_conn, [missing_metadata, valid_new])

    assert counts == {
        "skipped_missing_metadata": 1,
        "inserted": 1,
        "already_existing": 0,
    }
    # Only the one valid product should have ever reached the database.
    assert mock_conn.cursor.return_value.execute.call_count == 3  # games, sets, cards


def test_sync_products_counts_already_existing_separately_from_inserted():
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.rowcount = 0  # ON CONFLICT DO NOTHING skipped it

    counts = sync_products(mock_conn, [_valid_product()])

    assert counts["inserted"] == 0
    assert counts["already_existing"] == 1


def test_sync_products_lets_database_errors_surface():
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.execute.side_effect = Exception("simulated database failure")

    with pytest.raises(Exception):
        sync_products(mock_conn, [_valid_product()])


# --- run_bulk_sync ---
# Same approach as test_run_calls_everything_in_order: mock every dependency
# and confirm the orchestration wires them together correctly.


@patch("bulk_sync.sync_products")
@patch("bulk_sync.get_database_connection")
@patch("bulk_sync.download_bulk_results")
@patch("bulk_sync.poll_bulk_operation")
@patch("bulk_sync.start_bulk_operation")
@patch("bulk_sync.get_access_token")
@patch("bulk_sync.load_dotenv")
def test_run_bulk_sync_calls_everything_in_order(
    mock_load_dotenv,
    mock_get_access_token,
    mock_start_bulk_operation,
    mock_poll_bulk_operation,
    mock_download_bulk_results,
    mock_get_database_connection,
    mock_sync_products,
):
    mock_get_access_token.return_value = "fake-token"
    mock_start_bulk_operation.return_value = {"id": "gid://shopify/BulkOperation/1"}
    mock_poll_bulk_operation.return_value = {
        "objectCount": "2",
        "url": "https://example.com/results.jsonl",
    }
    mock_download_bulk_results.return_value = [{"title": "Test Card"}]
    mock_conn = MagicMock()
    mock_get_database_connection.return_value = mock_conn
    mock_sync_products.return_value = {"inserted": 1}

    result = run_bulk_sync()

    mock_download_bulk_results.assert_called_once_with("https://example.com/results.jsonl")
    mock_sync_products.assert_called_once_with(mock_conn, [{"title": "Test Card"}])
    mock_conn.close.assert_called_once()
    assert result == {"inserted": 1}


# --- get_database_connection ---
# Same idea as get_access_token's missing-credentials test, a missing
# DATABASE_URL should fail loudly instead of silently falling back to some
# unintended default database.


def test_get_database_connection_missing_url_exits():
    with pytest.raises(SystemExit):
        get_database_connection(None)


# --- insert_card ---
# This one touches a database connection, so instead of connecting to a
# real database, we fake the connection object itself, MagicMock() makes
# conn.cursor() automatically return another fake object we can inspect.


def test_insert_card_success():
    mock_conn = MagicMock()
    # rowcount == 1 simulates a real new row actually being inserted, as
    # opposed to ON CONFLICT DO NOTHING silently skipping it.
    mock_conn.cursor.return_value.rowcount = 1
    data = {
        "game": {"id": 89, "name": "Riftbound"},
        "set": {"id": 24698, "name": "Vendetta"},
        "card": {
            "shopifyProductId": "8042708992090",
            "name": "Kai'Sa, Survivor",
            "rarity": "Epic",
            "collectorNumber": "SP1/006",
            "tcgProductId": 707648,
            "marketPrice": "{}",
        },
    }

    result = insert_card(mock_conn, data)

    cursor = mock_conn.cursor.return_value
    # Three inserts: games, sets, cards.
    assert cursor.execute.call_count == 3
    mock_conn.commit.assert_called_once()
    mock_conn.rollback.assert_not_called()
    assert result is True


def test_insert_card_already_exists_returns_false():
    mock_conn = MagicMock()
    # rowcount == 0 simulates ON CONFLICT DO NOTHING skipping a card that's
    # already in the database, nothing new was actually inserted.
    mock_conn.cursor.return_value.rowcount = 0
    data = {
        "game": {"id": 89, "name": "Riftbound"},
        "set": {"id": 24698, "name": "Vendetta"},
        "card": {
            "shopifyProductId": "8042708992090",
            "name": "Kai'Sa, Survivor",
            "rarity": "Epic",
            "collectorNumber": "SP1/006",
            "tcgProductId": 707648,
            "marketPrice": "{}",
        },
    }

    result = insert_card(mock_conn, data)

    assert result is False


def test_insert_card_failure_rolls_back():
    mock_conn = MagicMock()
    cursor = mock_conn.cursor.return_value
    # side_effect makes the fake cursor raise an error instead of returning
    # normally, simulating a real database failure (bad constraint, lost
    # connection, whatever).
    cursor.execute.side_effect = Exception("simulated database failure")

    data = {
        "game": {"id": 1, "name": "Test Game"},
        "set": {"id": 1, "name": "Test Set"},
        "card": {
            "shopifyProductId": "1",
            "name": "Test Card",
            "rarity": "Common",
            "collectorNumber": "1",
            "tcgProductId": 1,
            "marketPrice": "{}",
        },
    }

    with pytest.raises(Exception):
        insert_card(mock_conn, data)

    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_not_called()


# --- run() (the glue function in main.py) ---
# This one calls everything else, so we mock every piece it depends on and
# just confirm it calls them in the right order with the right values,
# without actually hitting Shopify or Postgres.


@patch("main.insert_card")
@patch("main.get_database_connection")
@patch("main.build_card_data")
@patch("main.run_graphql_query")
@patch("main.get_access_token")
@patch("main.load_dotenv")
def test_run_calls_everything_in_order(
    mock_load_dotenv,
    mock_get_access_token,
    mock_run_graphql_query,
    mock_build_card_data,
    mock_get_database_connection,
    mock_insert_card,
):
    mock_get_access_token.return_value = "fake-token"
    mock_run_graphql_query.return_value = {"data": {"product": {}}}
    mock_build_card_data.return_value = {"game": {}, "set": {}, "card": {}}
    mock_conn = MagicMock()
    mock_get_database_connection.return_value = mock_conn

    run()

    mock_get_access_token.assert_called_once()
    mock_run_graphql_query.assert_called_once()
    mock_build_card_data.assert_called_once()
    mock_get_database_connection.assert_called_once()
    mock_insert_card.assert_called_once_with(
        mock_conn, {"game": {}, "set": {}, "card": {}}
    )
    # The connection should be closed after use, no matter what.
    mock_conn.close.assert_called_once()
