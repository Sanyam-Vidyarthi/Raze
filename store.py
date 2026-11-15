"""Catalogue, cart and purchasing rules shared by any RAZE interface."""

import os
from decimal import Decimal
from getpass import getpass

import mysql.connector
from mysql.connector import Error, IntegrityError, errorcode


class StoreError(Exception):
    """A marketplace rule prevented the requested action."""


GAME_FIELDS = (
    ("title", "Title", 120),
    ("genre", "Genre", 40),
    ("developer", "Developer", 100),
    ("platform", "Platform", 80),
)

GAME_LIST = """
    SELECT g.id, g.title, g.genre, g.price, g.developer, g.platform,
           g.is_available, oi.game_id IS NOT NULL AS owned
    FROM games AS g
    LEFT JOIN order_items AS oi ON oi.game_id = g.id
"""


def validate_text(value, label, max_length):
    value = value.strip()
    if not value or len(value) > max_length or not value.isprintable():
        raise StoreError(f"{label} must contain 1 to {max_length} printable characters.")
    return value


def parse_price(value):
    value = value.strip()
    parts = value.split(".")
    message = "Enter a price from 0 to 99999999.99 with at most two decimal places."
    if len(parts) > 2:
        raise StoreError(message)
    if not parts[0].isascii() or not parts[0].isdigit() or len(parts[0]) > 8:
        raise StoreError(message)
    if len(parts) == 2:
        paise = parts[1]
        if not paise.isascii() or not paise.isdigit() or len(paise) > 2:
            raise StoreError(message)
    return Decimal(value)


def total_price(games):
    total = Decimal("0.00")
    for game in games:
        total += game["price"]
    return total


def check_purchasable(game):
    if game["owned"]:
        raise StoreError(f'{game["title"]} is already owned.')
    if not game["is_available"]:
        raise StoreError(f'{game["title"]} is no longer for sale.')


def connection_settings():
    """Load local settings and prompt for the MySQL password if needed."""
    try:
        port = int(os.getenv("RAZE_DB_PORT", "3306"))
    except ValueError:
        raise ValueError("RAZE_DB_PORT must be a number from 1 to 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("RAZE_DB_PORT must be a number from 1 to 65535.")

    user = os.getenv("RAZE_DB_USER", "root")
    password = os.getenv("RAZE_DB_PASSWORD")
    if password is None:
        password = getpass(f"MySQL password for {user}: ")
    return {
        "host": os.getenv("RAZE_DB_HOST", "127.0.0.1"),
        "port": port,
        "user": user,
        "password": password,
        "database": "raze",
        "charset": "utf8mb4",
        "connection_timeout": 5,
        "autocommit": False,
    }


def connect_database(settings):
    return mysql.connector.connect(**settings)


def read_rows(settings, query, params=()):
    connection = connect_database(settings)
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        close_database(connection, cursor)


def rollback_write(connection):
    try:
        connection.rollback()
    except Error:
        # A disconnected server may already have rolled back the write.
        # Preserve the original error for the caller.
        pass


def close_database(connection, cursor):
    try:
        if cursor is not None:
            cursor.close()
    finally:
        connection.close()


def database_error_message(error):
    if error.errno in (1044, 1045, 1142):
        return "MySQL denied access. Check your MySQL credentials and database permissions."
    if error.errno in (1049, 1146):
        return "The RAZE database is missing or incomplete. Run setup.sql first."
    if error.errno in (1205, 1213):
        return "MySQL is busy. Please try again."
    if error.errno in (2002, 2003, 2005):
        return "Could not reach MySQL. Check that it is running and verify the host and port."
    if error.errno in (2006, 2013, 2055):
        return "MySQL disconnected. Check the library or catalogue before retrying a change."
    return f"MySQL could not complete the operation (error {error.errno})."


def catalogue(settings, search=None, genre=None, include_unavailable=False):
    filters = []
    params = []
    if not include_unavailable:
        filters.append("g.is_available = TRUE")
    if search is not None:
        # Escape the pattern characters so a search for "%" stays literal.
        escaped = search.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        filters.append("g.title LIKE %s ESCAPE '!'")
        params.append(f"%{escaped}%")
    if genre is not None:
        filters.append("g.genre = %s")
        params.append(genre)

    query = GAME_LIST
    if filters:
        query += " WHERE " + " AND ".join(filters)
    return read_rows(settings, query + " ORDER BY g.id", tuple(params))

def genres(settings):
    rows = read_rows(
        settings, "SELECT DISTINCT genre FROM games WHERE is_available = TRUE ORDER BY genre"
    )
    genres = []
    for row in rows:
        genres.append(row["genre"])
    return genres

def get_game(settings, game_id):
    games = read_rows(settings, GAME_LIST + " WHERE g.id = %s", (game_id,))
    if not games:
        raise StoreError("No game has that ID.")
    return games[0]

def add_to_cart(settings, cart_ids, game_id):
    if game_id in cart_ids:
        raise StoreError("That game is already in your cart.")
    game = get_game(settings, game_id)
    check_purchasable(game)
    cart_ids.append(game_id)
    return game

def remove_from_cart(cart_ids, game_id):
    if game_id not in cart_ids:
        raise StoreError("That game is not in your cart.")
    cart_ids.remove(game_id)

def cart_games(settings, cart_ids):
    if not cart_ids:
        return []
    placeholders = ", ".join(["%s"] * len(cart_ids))
    return read_rows(
        settings, GAME_LIST + f" WHERE g.id IN ({placeholders}) ORDER BY g.id", tuple(cart_ids)
    )

def checkout_quote(settings, cart_ids):
    games = cart_games(settings, cart_ids)
    if not cart_ids:
        raise StoreError("Your cart is empty.")
    if len(games) != len(cart_ids):
        raise StoreError("A game no longer exists. Remove it from your cart.")
    for game in games:
        check_purchasable(game)
    return games

def checkout(settings, cart_ids, confirmed_games):
    """Record the complete order at the prices the customer confirmed."""
    confirmed = {}
    for game in confirmed_games:
        confirmed[game["id"]] = (game["title"], game["price"])

    sorted_cart = sorted(cart_ids)
    if not sorted_cart or sorted(confirmed) != sorted_cart:
        raise StoreError("The cart changed. Review it and confirm checkout again.")

    game_ids = tuple(sorted_cart)
    placeholders = ", ".join(["%s"] * len(game_ids))
    connection = connect_database(settings)
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        # Lock catalogue rows before reading ownership. Another checkout of
        # these games, or an admin edit, must wait for this transaction.
        cursor.execute(
            f"""SELECT id, title, price, is_available FROM games
                WHERE id IN ({placeholders}) ORDER BY id FOR UPDATE""",
            game_ids,
        )
        games = cursor.fetchall()
        if len(games) != len(game_ids):
            raise StoreError("A game no longer exists. Remove it from your cart.")
        cursor.execute(
            f"SELECT game_id FROM order_items WHERE game_id IN ({placeholders})",
            game_ids,
        )
        owned_ids = []
        for row in cursor.fetchall():
            owned_ids.append(row["game_id"])
        for game in games:
            game["owned"] = game["id"] in owned_ids
            check_purchasable(game)
            if confirmed[game["id"]] != (game["title"], game["price"]):
                raise StoreError("A title or price changed. Review the cart and confirm again.")

        cursor.execute("INSERT INTO orders () VALUES ()")
        order_id = cursor.lastrowid
        for game in games:
            cursor.execute(
                "INSERT INTO order_items (game_id, order_id, price_paid) VALUES (%s, %s, %s)",
                (game["id"], order_id, game["price"]),
            )
        connection.commit()
        cart_ids.clear()
    except BaseException:
        rollback_write(connection)
        raise
    finally:
        close_database(connection, cursor)
    return order_id

def library(settings):
    return read_rows(settings, """
        SELECT g.id, g.title, g.genre, g.developer, g.platform, g.is_available,
               oi.price_paid AS price, oi.order_id, o.purchased_at
        FROM order_items AS oi
        JOIN games AS g ON g.id = oi.game_id
        JOIN orders AS o ON o.id = oi.order_id
        ORDER BY g.id
    """)

def save_game(settings, details, game_id=None):
    fields = []
    for key, label, length in GAME_FIELDS:
        fields.append(validate_text(details[key], label, length))
    fields.append(parse_price(details["price"]))

    connection = connect_database(settings)
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        if game_id is None:
            cursor.execute(
                """INSERT INTO games (title, genre, developer, platform, price)
                   VALUES (%s, %s, %s, %s, %s)""",
                tuple(fields),
            )
            game_id = cursor.lastrowid
        else:
            fields.append(game_id)
            cursor.execute(
                """UPDATE games SET title = %s, genre = %s, developer = %s,
                                    platform = %s, price = %s WHERE id = %s""",
                tuple(fields),
            )
            # MySQL reports zero changed rows when every value stayed the same.
            if cursor.rowcount == 0:
                cursor.execute("SELECT id FROM games WHERE id = %s", (game_id,))
                if cursor.fetchone() is None:
                    raise StoreError("No game has that ID.")
        connection.commit()
    except IntegrityError as error:
        rollback_write(connection)
        if error.errno == errorcode.ER_DUP_ENTRY:
            raise StoreError("A game with that title is already in the catalogue.") from error
        raise
    except BaseException:
        rollback_write(connection)
        raise
    finally:
        close_database(connection, cursor)
    return game_id

def remove_from_sale(settings, game_id):
    _set_sale_availability(settings, game_id, False)

def put_back_on_sale(settings, game_id):
    _set_sale_availability(settings, game_id, True)

def _set_sale_availability(settings, game_id, available):
    connection = connect_database(settings)
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE games SET is_available = %s WHERE id = %s AND is_available <> %s",
            (available, game_id, available),
        )
        if cursor.rowcount == 0:
            status = "off sale"
            if available:
                status = "on sale"
            raise StoreError(f"That game is already {status} or its ID does not exist.")
        connection.commit()
    except BaseException:
        rollback_write(connection)
        raise
    finally:
        close_database(connection, cursor)

def sales_summary(settings):
    rows = read_rows(settings, """
        SELECT COUNT(*) AS games_sold, COALESCE(SUM(price_paid), 0.00) AS revenue
        FROM order_items
    """)
    return rows[0]
