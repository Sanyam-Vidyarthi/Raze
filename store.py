"""MySQL marketplace operations for RAZE."""

import mysql.connector


# Game rows contain ID, title, genre, price, developer, platform and availability.
def get_games(cursor, title=None, genre=None):
    if title is not None:
        cursor.execute(
            "SELECT * FROM games WHERE is_available = 1 AND title LIKE %s ORDER BY id",
            ("%" + title + "%",),
        )
    elif genre is not None:
        cursor.execute(
            "SELECT * FROM games WHERE is_available = 1 AND genre = %s ORDER BY id",
            (genre,),
        )
    else:
        cursor.execute("SELECT * FROM games WHERE is_available = 1 ORDER BY id")
    return cursor.fetchall()


def get_game(cursor, game_id):
    cursor.execute("SELECT * FROM games WHERE id = %s", (game_id,))
    return cursor.fetchone()


def get_genres(cursor):
    cursor.execute("SELECT DISTINCT genre FROM games WHERE is_available = 1 ORDER BY genre")
    return cursor.fetchall()


def get_owned_ids(cursor):
    cursor.execute("SELECT game_id FROM order_items")
    owned_ids = []
    for row in cursor.fetchall():
        owned_ids.append(row[0])
    return owned_ids


def purchase_problem(game, owned_ids):
    if game is None:
        return "That game no longer exists."
    if game[0] in owned_ids:
        return game[1] + " is already owned."
    if not game[6]:
        return game[1] + " is off sale."
    return ""


def get_purchase_games(cursor, cart):
    if not cart:
        return [], "Your cart is empty."
    games = []
    owned_ids = get_owned_ids(cursor)
    for game_id in cart:
        game = get_game(cursor, game_id)
        problem = purchase_problem(game, owned_ids)
        if problem:
            return [], problem
        games.append(game)
    return games, ""


def purchase_games(connection, cursor, cart, confirmed_prices):
    # End the read from before confirmation so these queries see current values.
    connection.rollback()
    try:
        games, problem = get_purchase_games(cursor, cart)
        if problem:
            return None, problem
        for index in range(len(games)):
            if games[index][3] != confirmed_prices[index]:
                return None, "A price changed. Review the cart and confirm again."

        cursor.execute("INSERT INTO orders (purchased_on) VALUES (CURRENT_DATE)")
        order_id = cursor.lastrowid
        for game in games:
            cursor.execute(
                "INSERT INTO order_items (game_id, order_id, price_paid) VALUES (%s, %s, %s)",
                (game[0], order_id, game[3]),
            )
        connection.commit()
        return order_id, ""
    except mysql.connector.Error as error:
        connection.rollback()
        return None, "Purchase failed. " + str(error)


def get_library(cursor):
    cursor.execute("""
        SELECT games.id, games.title, games.genre, games.developer, games.platform,
               order_items.price_paid, orders.id, orders.purchased_on
        FROM games, order_items, orders
        WHERE games.id = order_items.game_id AND orders.id = order_items.order_id
        ORDER BY games.id
    """)
    return cursor.fetchall()


def get_catalogue(cursor):
    cursor.execute("SELECT * FROM games ORDER BY id")
    return cursor.fetchall()


def save_game(connection, cursor, details, game_id=None):
    if game_id is None:
        cursor.execute(
            "INSERT INTO games (title, genre, developer, platform, price) VALUES (%s, %s, %s, %s, %s)",
            details,
        )
    else:
        cursor.execute("""
            UPDATE games SET title = %s, genre = %s, developer = %s,
                             platform = %s, price = %s WHERE id = %s
        """, details + (game_id,))
    connection.commit()


def change_availability(connection, cursor, game_id, available):
    cursor.execute("UPDATE games SET is_available = %s WHERE id = %s", (available, game_id))
    connection.commit()


def sales_summary(cursor):
    cursor.execute("SELECT COUNT(*), SUM(price_paid) FROM order_items")
    quantity, revenue = cursor.fetchone()
    if revenue is None:
        revenue = 0
    return quantity, revenue
