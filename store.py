"""Catalogue, cart and purchasing rules shared by any RAZE interface."""

import re
from decimal import Decimal

from mysql.connector import IntegrityError, errorcode

from db import database_cursor


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
    if not re.fullmatch(r"[0-9]{1,8}(\.[0-9]{1,2})?", value.strip()):
        raise StoreError("Enter a price from 0 to 99999999.99 with at most two decimal places.")
    return Decimal(value)


def total_price(games):
    return sum((game["price"] for game in games), Decimal("0.00"))


def check_purchasable(game):
    if game["owned"]:
        raise StoreError(f'{game["title"]} is already owned.')
    if not game["is_available"]:
        raise StoreError(f'{game["title"]} is no longer for sale.')


class Marketplace:
    def __init__(self, settings):
        self.settings = settings
        self.cart_ids = []

    def catalogue(self, *, search=None, genre=None, include_unavailable=False):
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
        with database_cursor(self.settings) as cursor:
            cursor.execute(query + " ORDER BY g.id", tuple(params))
            return cursor.fetchall()

    def genres(self):
        with database_cursor(self.settings) as cursor:
            cursor.execute(
                "SELECT DISTINCT genre FROM games WHERE is_available = TRUE ORDER BY genre"
            )
            return [row["genre"] for row in cursor.fetchall()]

    def get_game(self, game_id):
        with database_cursor(self.settings) as cursor:
            cursor.execute(GAME_LIST + " WHERE g.id = %s", (game_id,))
            game = cursor.fetchone()
        if game is None:
            raise StoreError("No game has that ID.")
        return game

    def add_to_cart(self, game_id):
        if game_id in self.cart_ids:
            raise StoreError("That game is already in your cart.")
        game = self.get_game(game_id)
        check_purchasable(game)
        self.cart_ids.append(game_id)
        return game

    def remove_from_cart(self, game_id):
        if game_id not in self.cart_ids:
            raise StoreError("That game is not in your cart.")
        self.cart_ids.remove(game_id)

    def cart_games(self):
        if not self.cart_ids:
            return []
        placeholders = ", ".join(["%s"] * len(self.cart_ids))
        with database_cursor(self.settings) as cursor:
            cursor.execute(
                GAME_LIST + f" WHERE g.id IN ({placeholders}) ORDER BY g.id",
                tuple(self.cart_ids),
            )
            return cursor.fetchall()

    def checkout_quote(self):
        games = self.cart_games()
        if not self.cart_ids:
            raise StoreError("Your cart is empty.")
        if len(games) != len(self.cart_ids):
            raise StoreError("A game no longer exists. Remove it from your cart.")
        for game in games:
            check_purchasable(game)
        return games

    def checkout(self, confirmed_games):
        """Record the complete order at the prices the customer confirmed."""
        confirmed = {game["id"]: (game["title"], game["price"]) for game in confirmed_games}
        if not self.cart_ids or set(confirmed) != set(self.cart_ids):
            raise StoreError("The cart changed. Review it and confirm checkout again.")

        game_ids = tuple(sorted(confirmed))
        placeholders = ", ".join(["%s"] * len(game_ids))
        with database_cursor(self.settings, write=True) as cursor:
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
            owned_ids = {row["game_id"] for row in cursor.fetchall()}
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

        self.cart_ids.clear()
        return order_id

    def library(self):
        with database_cursor(self.settings) as cursor:
            cursor.execute("""
                SELECT g.id, g.title, g.genre, g.developer, g.platform, g.is_available,
                       oi.price_paid AS price, oi.order_id, o.purchased_at
                FROM order_items AS oi
                JOIN games AS g ON g.id = oi.game_id
                JOIN orders AS o ON o.id = oi.order_id
                ORDER BY g.id
            """)
            return cursor.fetchall()

    def save_game(self, details, game_id=None):
        fields = [
            validate_text(details[key], label, length)
            for key, label, length in GAME_FIELDS
        ]
        fields.append(parse_price(details["price"]))

        try:
            with database_cursor(self.settings, write=True) as cursor:
                if game_id is None:
                    cursor.execute(
                        """INSERT INTO games (title, genre, developer, platform, price)
                           VALUES (%s, %s, %s, %s, %s)""",
                        tuple(fields),
                    )
                    return cursor.lastrowid

                cursor.execute(
                    """UPDATE games SET title = %s, genre = %s, developer = %s,
                                        platform = %s, price = %s WHERE id = %s""",
                    (*fields, game_id),
                )
                # MySQL reports zero changed rows when every value stayed the same.
                if cursor.rowcount == 0:
                    cursor.execute("SELECT id FROM games WHERE id = %s", (game_id,))
                    if cursor.fetchone() is None:
                        raise StoreError("No game has that ID.")
                return game_id
        except IntegrityError as error:
            if error.errno == errorcode.ER_DUP_ENTRY:
                raise StoreError("A game with that title is already in the catalogue.") from error
            raise

    def remove_from_sale(self, game_id):
        self._set_sale_availability(game_id, False)

    def put_back_on_sale(self, game_id):
        self._set_sale_availability(game_id, True)

    def _set_sale_availability(self, game_id, available):
        with database_cursor(self.settings, write=True) as cursor:
            cursor.execute(
                "UPDATE games SET is_available = %s WHERE id = %s AND is_available <> %s",
                (available, game_id, available),
            )
            if cursor.rowcount == 0:
                status = "on sale" if available else "off sale"
                raise StoreError(f"That game is already {status} or its ID does not exist.")

    def sales_summary(self):
        with database_cursor(self.settings) as cursor:
            cursor.execute("""
                SELECT COUNT(*) AS games_sold, COALESCE(SUM(price_paid), 0.00) AS revenue
                FROM order_items
            """)
            return cursor.fetchone()

    def sales_report(self):
        """Group purchase records into orders and calculate totals from the same read."""
        purchases = self.library()
        orders = {}
        for game in purchases:
            order_id = game["order_id"]
            if order_id not in orders:
                orders[order_id] = {
                    "id": order_id,
                    "purchased_at": game["purchased_at"],
                    "games": [],
                }
            orders[order_id]["games"].append(game)

        return {
            "games_sold": len(purchases),
            "revenue": total_price(purchases),
            "orders": sorted(
                orders.values(), key=lambda order: (order["purchased_at"], order["id"]), reverse=True
            ),
        }
