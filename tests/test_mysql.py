"""Live MySQL checks. Each test creates and drops its own scratch database."""

import io
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import mysql.connector

import store
from main import DEMO_ADMIN_PASSWORD, main_menu
from store import StoreError, total_price
from update_catalogue import update_catalogue


SETUP = Path(__file__).resolve().parents[1] / "setup.sql"


@contextmanager
def fixture_cursor(settings):
    """Use a write cursor for creating and modifying isolated test fixtures."""
    with store.connect_database(settings) as connection:
        with connection.cursor(dictionary=True) as cursor:
            yield cursor
            connection.commit()


@unittest.skipUnless(os.getenv("RAZE_RUN_MYSQL_TESTS") == "1", "Live MySQL tests are opt-in")
class MySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = store.connection_settings()
        cls.server.pop("database")

    def setUp(self):
        self.schema = f"raze_test_{uuid4().hex}"
        self.settings = {**self.server, "database": self.schema}
        self.addCleanup(self.drop_database)
        self.run_setup()
        self.cart = []

    def run_setup(self):
        sql = SETUP.read_text(encoding="utf-8")
        if not sql.startswith("CREATE DATABASE IF NOT EXISTS raze\n") or "\nUSE raze;\n" not in sql:
            raise RuntimeError("Could not redirect setup to a scratch database.")
        sql = sql.replace("IF NOT EXISTS raze\n", f"IF NOT EXISTS {self.schema}\n", 1)
        sql = sql.replace("USE raze;", f"USE {self.schema};", 1)
        with fixture_cursor(self.server) as cursor:
            cursor.execute(sql)
            while cursor.nextset():
                pass

    def drop_database(self):
        with fixture_cursor(self.server) as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {self.schema}")

    def test_catalogue_discovery_and_validation(self):
        catalogue_ids = [game["id"] for game in store.catalogue(self.settings)]
        self.assertEqual(len(catalogue_ids), 32)
        self.assertEqual(catalogue_ids, sorted(catalogue_ids))
        self.assertEqual([g["id"] for g in store.catalogue(self.settings, search="cYbEr")], [3])
        search_ids = [game["id"] for game in store.catalogue(self.settings, search="ghost")]
        self.assertEqual(search_ids, [25, 26])
        self.assertEqual([g["id"] for g in store.catalogue(self.settings, search="director's cut")], [25])
        self.assertEqual(store.catalogue(self.settings, search="yotei")[0]["platform"], "PS5")
        self.assertEqual(store.catalogue(self.settings, search="%"), [])
        self.assertIn("RPG", store.genres(self.settings))
        rpgs = store.catalogue(self.settings, genre="rpg")
        self.assertEqual([g["id"] for g in rpgs], [3, 5, 17, 40, 41, 42])
        with self.assertRaisesRegex(StoreError, "No game"):
            store.add_to_cart(self.settings, self.cart, 99999)
        with self.assertRaisesRegex(StoreError, "empty"):
            store.checkout_quote(self.settings, self.cart)
        game = store.get_game(self.settings, 4)
        for price in ("-1", "12.345", "NaN", "1e3", "100000000"):
            with self.subTest(price=price), self.assertRaisesRegex(StoreError, "price"):
                store.save_game(self.settings, {**game, "price": price}, 4)
        with self.assertRaisesRegex(StoreError, "Title must"):
            store.save_game(self.settings, {**game, "title": "  ", "price": "1.00"}, 4)

    def test_cart_checkout_history_and_repeat_setup(self):
        for game_id in (4, 2, 3):
            store.add_to_cart(self.settings, self.cart, game_id)
        with self.assertRaisesRegex(StoreError, "already in"):
            store.add_to_cart(self.settings, self.cart, 4)
        store.remove_from_cart(self.cart, 3)
        quote = store.checkout_quote(self.settings, self.cart)
        self.assertEqual([game["id"] for game in quote], [2, 4])
        self.assertEqual(total_price(quote), Decimal("5698.00"))
        order_id = store.checkout(self.settings, self.cart, quote)
        self.assertEqual(self.cart, [])

        reopened_cart = []
        self.assertTrue(store.get_game(self.settings, 4)["owned"])
        with self.assertRaisesRegex(StoreError, "already owned"):
            store.add_to_cart(self.settings, reopened_cart, 4)
        game = store.get_game(self.settings, 4)
        store.save_game(self.settings, {**game, "title": "RDR2", "price": "9.99"}, 4)
        store.remove_from_sale(self.settings, 4)
        self.run_setup()
        self.assertFalse(store.catalogue(self.settings, search="Red Dead"))
        self.assertEqual(len(store.catalogue(self.settings, include_unavailable=True)), 32)
        store.remove_from_sale(self.settings, 5)
        with self.assertRaisesRegex(StoreError, "no longer for sale"):
            store.add_to_cart(self.settings, reopened_cart, 5)
        library = {row["id"]: row for row in store.library(self.settings)}
        self.assertEqual(list(library), [2, 4])
        self.assertEqual({row["order_id"] for row in library.values()}, {order_id})
        self.assertEqual(library[4]["title"], "RDR2")
        self.assertEqual(library[4]["price"], Decimal("3199.00"))
        self.assertFalse(library[4]["is_available"])
        self.assertEqual(store.sales_summary(self.settings), {"games_sold": 2, "revenue": Decimal("5698.00")})

    def test_catalogue_update_preserves_old_purchases_and_game_ids(self):
        expected_titles = {game["title"] for game in store.catalogue(self.settings)}
        with fixture_cursor(self.settings) as cursor:
            cursor.execute("DELETE FROM games WHERE id >= 25")
            cursor.execute("UPDATE games SET title = 'Grand Theft Auto V Enhanced' WHERE id = 2")
            cursor.execute("""
                INSERT INTO games (id, title, genre, price, developer, platform) VALUES
                (1, 'Minecraft: Java Edition', 'Sandbox', 1999.00, 'Mojang Studios', 'Windows'),
                (25, 'Extra Game', 'Puzzle', 10.00, 'Test Studio', 'Windows')
            """)
        store.add_to_cart(self.settings, self.cart, 1)
        store.add_to_cart(self.settings, self.cart, 2)
        order_id = store.checkout(self.settings, self.cart, store.checkout_quote(self.settings, self.cart))

        for _ in range(2):
            self.assertEqual(update_catalogue(self.settings), 32)
            self.assertEqual({game["title"] for game in store.catalogue(self.settings)}, expected_titles)
            self.assertFalse(store.get_game(self.settings, 25)["is_available"])
            library = {game["id"]: game for game in store.library(self.settings)}
            self.assertEqual(set(library), {1, 2})
            self.assertFalse(library[1]["is_available"])
            self.assertEqual(library[1]["price"], Decimal("1999.00"))
            self.assertEqual(library[2]["title"], "Grand Theft Auto V")
            self.assertEqual(library[2]["order_id"], order_id)
            self.assertTrue(store.get_game(self.settings, 2)["owned"])

    def test_admin_edits_and_stale_checkout(self):
        new_game = {
            "title": "Test Game", "genre": "Puzzle", "developer": "Test Studio",
            "platform": "Windows", "price": "25.99",
        }
        game_id = store.save_game(self.settings, new_game)
        with self.assertRaisesRegex(StoreError, "already in the catalogue"):
            store.save_game(self.settings, {**new_game, "title": "test game"})
        store.add_to_cart(self.settings, self.cart, game_id)
        quote = store.checkout_quote(self.settings, self.cart)
        edited = {
            "title": "Test Game 2", "genre": "Strategy", "developer": "Second Studio",
            "platform": "Linux", "price": "2.50",
        }
        store.save_game(self.settings, edited, game_id)
        store.save_game(self.settings, edited, game_id)
        record = store.get_game(self.settings, game_id)
        self.assertEqual({key: str(record[key]) for key in edited}, edited)
        with self.assertRaisesRegex(StoreError, "title or price changed"):
            store.checkout(self.settings, self.cart, quote)
        updated_quote = store.checkout_quote(self.settings, self.cart)
        store.remove_from_sale(self.settings, game_id)
        with self.assertRaisesRegex(StoreError, "no longer for sale"):
            store.checkout(self.settings, self.cart, updated_quote)
        self.assertEqual(store.sales_summary(self.settings)["games_sold"], 0)
        self.assertEqual(self.cart, [game_id])

    def test_second_item_failure_rolls_back_entire_order(self):
        store.add_to_cart(self.settings, self.cart, 2)
        store.add_to_cart(self.settings, self.cart, 3)
        quote = store.checkout_quote(self.settings, self.cart)
        with fixture_cursor(self.settings) as cursor:
            cursor.execute("""
                CREATE TRIGGER fail_second_item BEFORE INSERT ON order_items
                FOR EACH ROW SET NEW.price_paid = IF(NEW.game_id = 3, -1, NEW.price_paid)
            """)
        with self.assertRaises(mysql.connector.Error):
            store.checkout(self.settings, self.cart, quote)
        self.assertEqual(self.cart, [2, 3])
        self.assertEqual(store.library(self.settings), [])
        with fixture_cursor(self.settings) as cursor:
            cursor.execute("SELECT COUNT(*) AS orders_written FROM orders")
            self.assertEqual(cursor.fetchone()["orders_written"], 0)
            cursor.execute("DROP TRIGGER fail_second_item")
        store.checkout(self.settings, self.cart, quote)
        self.assertEqual(store.sales_summary(self.settings)["games_sold"], 2)

    def test_concurrent_checkouts_cannot_duplicate_ownership(self):
        other_cart = []
        start = Barrier(2, timeout=5)
        for cart, additional_id in ((self.cart, 2), (other_cart, 3)):
            store.add_to_cart(self.settings, cart, 4)
            store.add_to_cart(self.settings, cart, additional_id)

        def buy(cart):
            quote = store.checkout_quote(self.settings, cart)
            start.wait()
            try:
                store.checkout(self.settings, cart, quote)
                return "purchased"
            except StoreError as error:
                self.assertIn("already owned", str(error))
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(buy, (self.cart, other_cart)))
        self.assertCountEqual(outcomes, ["purchased", "rejected"])
        self.assertEqual(store.sales_summary(self.settings)["games_sold"], 2)
        self.assertEqual(len({row["order_id"] for row in store.library(self.settings)}), 1)

    def test_sales_summary_counts_free_games_and_preserves_paid_prices(self):
        self.assertEqual(
            store.sales_summary(self.settings), {"games_sold": 0, "revenue": Decimal("0.00")}
        )
        for game_id in (3, 7):
            store.add_to_cart(self.settings, self.cart, game_id)
        quote = store.checkout_quote(self.settings, self.cart)
        store.checkout(self.settings, self.cart, quote)
        store.add_to_cart(self.settings, self.cart, 37)  # Counter-Strike 2 is free.
        quote = store.checkout_quote(self.settings, self.cart)
        store.checkout(self.settings, self.cart, quote)

        game = store.get_game(self.settings, 3)
        store.save_game(self.settings, {**game, "price": "99.00"}, 3)
        store.remove_from_sale(self.settings, 3)

        summary = store.sales_summary(self.settings)
        self.assertEqual(summary, {"games_sold": 3, "revenue": Decimal("3598.00")})
        library = {game["id"]: game for game in store.library(self.settings)}
        self.assertEqual(library[37]["price"], Decimal("0.00"))
        self.assertEqual(library[3]["price"], Decimal("2999.00"))
        self.assertFalse(library[3]["is_available"])


    def test_terminal_flow(self):
        inputs = [
            "bogus", "1", "0", "3", "1", "0", "0",
            "2", "no such title", "2", "cyber", "oops", "3", "1", "y",
            "2", "hollow", "1", "y", "2", "grand theft", "1", "y",
            "4", "1", "1", "2", "n", "2", "y", "3",
            "5", "1", "6", "6", "3", "2", "", "", "", "", "100", "y",
            "4", "2", "y", "5", "6", "1", "n", "6", "1", "y", "6",
            "2", "Viva Demo Game", "Puzzle", "Demo Studio", "Windows", "12.34", "y",
            "7", "5", "0", "7",
        ]
        output = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs),
            patch("main.getpass", side_effect=["wrong", DEMO_ADMIN_PASSWORD]),
            redirect_stdout(output),
        ):
            main_menu(self.settings, self.cart)
        terminal_text = output.getvalue()
        for heading, count in (
            ("Browse Games", 32),
            ("Action-Adventure", len(store.catalogue(self.settings, genre="Action-Adventure"))),
        ):
            listing = terminal_text.split(f"\n{heading}\n", 1)[1].split("Enter a game number", 1)[0]
            numbers = [int(line[:3]) for line in listing.splitlines() if line[:3].strip().isdigit()]
            self.assertEqual(numbers, list(range(1, count + 1)))
        for message in (
            "Choose one of the numbered options.", "No games found.",
            "Enter a game number from 1 to 1, or 0 to go back.", "Checkout cancelled.",
            "Game removed from your cart.",
            "Final total  ₹3,598.00", "Order #1 complete.", "Administrator access denied.",
            "Game details saved.", "Game removed from sale.", "Simulated revenue  ₹3,598.00",
            "Cyberpunk 2077 is back on sale.", "No games are off sale.",
            "Viva Demo Game added to the catalogue.",
        ):
            self.assertIn(message, terminal_text)
        self.assertNotIn("Order History", terminal_text)
        self.assertEqual(store.catalogue(self.settings, search="Viva Demo Game")[0]["price"], Decimal("12.34"))
        self.assertEqual(store.get_game(self.settings, 3)["price"], Decimal("100.00"))
        self.assertTrue(store.get_game(self.settings, 3)["is_available"])
        with self.assertRaisesRegex(StoreError, "already owned"):
            store.add_to_cart(self.settings, self.cart, 3)
        self.assertEqual([game["id"] for game in store.library(self.settings)], [3, 7])
