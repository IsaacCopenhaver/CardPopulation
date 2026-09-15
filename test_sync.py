import pytest
from unittest.mock import patch, MagicMock
from database import build_card_data, get_database_connection, insert_card
from shopify import get_access_token
from main import run

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
