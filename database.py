import sys

import psycopg2


def get_database_connection(database_url):
    if not database_url:
        print("Missing DATABASE_URL. Set it in the environment before running.")
        sys.exit(1)
    conn = psycopg2.connect(database_url)
    return conn


def build_card_data(product):
    return {
        "game": {
            "id": int(product["categoryId"]["value"]),
            "name": product["gameName"]["value"],
        },
        "set": {
            "id": int(product["groupId"]["value"]),
            "name": product["setName"]["value"],
        },
        "card": {
            "shopifyProductId": str(product["legacyResourceId"]),
            "name": product["cardName"]["value"],
            "rarity": product["rarity"]["value"],
            "collectorNumber": product["collectorNumber"]["value"],
            "tcgProductId": int(product["tcgProductId"]["value"]),
            "marketPrice": product["pricing"]["value"],
        },
    }


def insert_card(conn, data):
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO games (id, name, "createdAt", "updatedAt")
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING""",
            (data["game"]["id"], data["game"]["name"]),
        )

        cursor.execute(
            """INSERT INTO sets (id, name, "gameId", "createdAt", "updatedAt")
            VALUES (%s, %s, %s, NOW(), NOW())
            ON CONFLICT (id) DO NOTHING""",
            (data["set"]["id"], data["set"]["name"], data["game"]["id"]),
        )

        cursor.execute(
            """INSERT INTO cards (
            "shopifyProductId", "setId", name, "collectorNumber",
            rarity, "tcgProductId", "marketPrice", "createdAt", "updatedAt"
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT ("shopifyProductId") DO NOTHING""",
            (
                data["card"]["shopifyProductId"],
                data["set"]["id"],
                data["card"]["name"],
                data["card"]["collectorNumber"],
                data["card"]["rarity"],
                data["card"]["tcgProductId"],
                data["card"]["marketPrice"],
            ),
        )
        was_inserted = cursor.rowcount == 1
        conn.commit()
        return was_inserted
    except Exception as e:
        conn.rollback()
        print(f"Error inserting card data: {e}")
        raise
    finally:
        cursor.close()
