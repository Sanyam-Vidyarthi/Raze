"""Live MySQL checks. Each test creates and drops its own scratch database."""

import io
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import mysql.connector

from db import connection_settings, database_cursor
from main import DEMO_ADMIN_PASSWORD, Terminal
from store import Marketplace, StoreError, total_price
from update_catalogue import update_catalogue


SETUP = Path(__file__).resolve().parents[1] / "setup.sql"


@unittest.skipUnless(os.getenv("RAZE_RUN_MYSQL_TESTS") == "1", "Live MySQL tests are opt-in")
class MySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = connection_settings()
        cls.server.pop("database")

    def setUp(self):
        self.schema = f"raze_test_{uuid4().hex}"
        self.settings = {**self.server, "database": self.schema}
        self.addCleanup(self.drop_database)
        self.run_setup()
        self.store = Marketplace(self.settings)

    def run_setup(self):
        sql = SETUP.read_text(encoding="utf-8")
        if not sql.startswith("CREATE DATABASE IF NOT EXISTS raze\n") or "\nUSE raze;\n" not in sql:
            raise RuntimeError("Could not redirect setup to a scratch database.")
        sql = sql.replace("IF NOT EXISTS raze\n", f"IF NOT EXISTS {self.schema}\n", 1)
        sql = sql.replace("USE raze;", f"USE {self.schema};", 1)
        with database_cursor(self.server, write=True) as cursor:
            cursor.execute(sql)
            while cursor.nextset():
                pass

    def drop_database(self):
        with database_cursor(self.server, write=True) as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {self.schema}")

    def test_catalogue_discovery_and_validation(self):
        catalogue_ids = [game["id"] for game in self.store.catalogue()]
        self.assertEqual(len(catalogue_ids), 32)
        self.assertEqual(catalogue_ids, sorted(catalogue_ids))
        self.assertEqual([g["id"] for g in self.store.catalogue(search="cYbEr")], [3])
        search_ids = [game["id"] for game in self.store.catalogue(search="ghost")]
        self.assertEqual(search_ids, [25, 26])
        self.assertEqual([g["id"] for g in self.store.catalogue(search="director's cut")], [25])
        self.assertEqual(self.store.catalogue(search="yotei")[0]["platform"], "PS5")
        self.assertEqual(self.store.catalogue(search="%"), [])
        self.assertIn("RPG", self.store.genres())
        rpgs = self.store.catalogue(genre="rpg")
        self.assertEqual([g["id"] for g in rpgs], [3, 5, 17, 40, 41, 42])
        with self.assertRaisesRegex(StoreError, "No game"):
            self.store.add_to_cart(99999)
        with self.assertRaisesRegex(StoreError, "empty"):
            self.store.checkout_quote()
        game = self.store.get_game(4)
        for price in ("-1", "12.345", "NaN", "1e3", "100000000"):
            with self.subTest(price=price), self.assertRaisesRegex(StoreError, "price"):
                self.store.save_game({**game, "price": price}, 4)
        with self.assertRaisesRegex(StoreError, "Title must"):
            self.store.save_game({**game, "title": "  ", "price": "1.00"}, 4)

    def test_cart_checkout_history_and_repeat_setup(self):
        for game_id in (4, 2, 3):
            self.store.add_to_cart(game_id)
        with self.assertRaisesRegex(StoreError, "already in"):
            self.store.add_to_cart(4)
        self.store.remove_from_cart(3)
        quote = self.store.checkout_quote()
        self.assertEqual([game["id"] for game in quote], [2, 4])
        self.assertEqual(total_price(quote), Decimal("5698.00"))
        order_id = self.store.checkout(quote)
        self.assertEqual(self.store.cart_ids, [])

        reopened = Marketplace(self.settings)
        self.assertTrue(reopened.get_game(4)["owned"])
        with self.assertRaisesRegex(StoreError, "already owned"):
            reopened.add_to_cart(4)
        game = reopened.get_game(4)
        reopened.save_game({**game, "title": "RDR2", "price": "9.99"}, 4)
        reopened.remove_from_sale(4)
        self.run_setup()
        self.assertFalse(reopened.catalogue(search="Red Dead"))
        self.assertEqual(len(reopened.catalogue(include_unavailable=True)), 32)
        reopened.remove_from_sale(5)
        with self.assertRaisesRegex(StoreError, "no longer for sale"):
            reopened.add_to_cart(5)
        library = {row["id"]: row for row in reopened.library()}
        self.assertEqual(list(library), [2, 4])
        self.assertEqual({row["order_id"] for row in library.values()}, {order_id})
        self.assertEqual(library[4]["title"], "RDR2")
        self.assertEqual(library[4]["price"], Decimal("3199.00"))
        self.assertFalse(library[4]["is_available"])
        self.assertEqual(reopened.sales_summary(), {"games_sold": 2, "revenue": Decimal("5698.00")})

    def test_catalogue_update_preserves_old_purchases_and_game_ids(self):
        expected_titles = {game["title"] for game in self.store.catalogue()}
        with database_cursor(self.settings, write=True) as cursor:
            cursor.execute("DELETE FROM games WHERE id >= 25")
            cursor.execute("UPDATE games SET title = 'Grand Theft Auto V Enhanced' WHERE id = 2")
            cursor.execute("""
                INSERT INTO games (id, title, genre, price, developer, platform) VALUES
                (1, 'Minecraft: Java Edition', 'Sandbox', 1999.00, 'Mojang Studios', 'Windows'),
                (25, 'Extra Game', 'Puzzle', 10.00, 'Test Studio', 'Windows')
            """)
        self.store.add_to_cart(1)
        self.store.add_to_cart(2)
        order_id = self.store.checkout(self.store.checkout_quote())

        for _ in range(2):
            self.assertEqual(update_catalogue(self.settings), 32)
            self.assertEqual({game["title"] for game in self.store.catalogue()}, expected_titles)
            self.assertFalse(self.store.get_game(25)["is_available"])
            library = {game["id"]: game for game in self.store.library()}
            self.assertEqual(set(library), {1, 2})
            self.assertFalse(library[1]["is_available"])
            self.assertEqual(library[1]["price"], Decimal("1999.00"))
            self.assertEqual(library[2]["title"], "Grand Theft Auto V")
            self.assertEqual(library[2]["order_id"], order_id)
            self.assertTrue(self.store.get_game(2)["owned"])

    def test_admin_edits_and_stale_checkout(self):
        new_game = {
            "title": "Test Game", "genre": "Puzzle", "developer": "Test Studio",
            "platform": "Windows", "price": "25.99",
        }
        game_id = self.store.save_game(new_game)
        with self.assertRaisesRegex(StoreError, "already in the catalogue"):
            self.store.save_game({**new_game, "title": "test game"})
        self.store.add_to_cart(game_id)
        quote = self.store.checkout_quote()
        edited = {
            "title": "Test Game 2", "genre": "Strategy", "developer": "Second Studio",
            "platform": "Linux", "price": "2.50",
        }
        self.store.save_game(edited, game_id)
        self.store.save_game(edited, game_id)
        record = self.store.get_game(game_id)
        self.assertEqual({key: str(record[key]) for key in edited}, edited)
        with self.assertRaisesRegex(StoreError, "title or price changed"):
            self.store.checkout(quote)
        updated_quote = self.store.checkout_quote()
        self.store.remove_from_sale(game_id)
        with self.assertRaisesRegex(StoreError, "no longer for sale"):
            self.store.checkout(updated_quote)
        self.assertEqual(self.store.sales_summary()["games_sold"], 0)
        self.assertEqual(self.store.cart_ids, [game_id])

    def test_second_item_failure_rolls_back_entire_order(self):
        self.store.add_to_cart(2)
        self.store.add_to_cart(3)
        quote = self.store.checkout_quote()
        with database_cursor(self.settings, write=True) as cursor:
            cursor.execute("""
                CREATE TRIGGER fail_second_item BEFORE INSERT ON order_items
                FOR EACH ROW SET NEW.price_paid = IF(NEW.game_id = 3, -1, NEW.price_paid)
            """)
        with self.assertRaises(mysql.connector.Error):
            self.store.checkout(quote)
        self.assertEqual(self.store.cart_ids, [2, 3])
        self.assertEqual(self.store.library(), [])
        with database_cursor(self.settings, write=True) as cursor:
            cursor.execute("SELECT COUNT(*) AS orders_written FROM orders")
            self.assertEqual(cursor.fetchone()["orders_written"], 0)
            cursor.execute("DROP TRIGGER fail_second_item")
        self.store.checkout(quote)
        self.assertEqual(self.store.sales_summary()["games_sold"], 2)

    def test_concurrent_checkouts_cannot_duplicate_ownership(self):
        other = Marketplace(self.settings)
        start = Barrier(2, timeout=5)
        for store, additional_id in ((self.store, 2), (other, 3)):
            store.add_to_cart(4)
            store.add_to_cart(additional_id)

        def buy(store):
            quote = store.checkout_quote()
            start.wait()
            try:
                store.checkout(quote)
                return "purchased"
            except StoreError as error:
                self.assertIn("already owned", str(error))
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(buy, (self.store, other)))
        self.assertCountEqual(outcomes, ["purchased", "rejected"])
        self.assertEqual(self.store.sales_summary()["games_sold"], 2)
        self.assertEqual(len({row["order_id"] for row in self.store.library()}), 1)

    def test_sales_report_groups_orders_and_preserves_paid_prices(self):
        self.assertEqual(self.store.sales_report()["orders"], [])
        for game_id in (3, 7):
            self.store.add_to_cart(game_id)
        first_order = self.store.checkout(self.store.checkout_quote())
        self.store.add_to_cart(37)  # Counter-Strike 2 is a zero-price purchase.
        second_order = self.store.checkout(self.store.checkout_quote())

        game = self.store.get_game(3)
        self.store.save_game({**game, "price": "99.00"}, 3)
        self.store.remove_from_sale(3)

        report = self.store.sales_report()
        self.assertEqual(report["games_sold"], 3)
        self.assertEqual(report["revenue"], Decimal("3598.00"))
        self.assertEqual([order["id"] for order in report["orders"]], [second_order, first_order])
        newest, oldest = report["orders"]
        self.assertEqual(total_price(newest["games"]), Decimal("0.00"))
        self.assertEqual([game["id"] for game in oldest["games"]], [3, 7])
        self.assertEqual(oldest["games"][0]["price"], Decimal("2999.00"))
        self.assertFalse(oldest["games"][0]["is_available"])

    def test_terminal_flow(self):
        inputs = [
            "bogus", "1", "0", "3", "1", "0", "0",
            "2", "no such title", "2", "cyber", "oops", "3", "1", "y",
            "2", "hollow", "1", "y", "2", "grand theft", "1", "y",
            "4", "1", "1", "2", "n", "2", "y", "3",
            "5", "1", "6", "6", "3", "2", "", "", "", "", "100", "y",
            "4", "2", "y", "5", "6", "1", "n", "6", "1", "y", "6", "7", "5", "0", "7",
        ]
        output = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs),
            patch("main.getpass", side_effect=["wrong", DEMO_ADMIN_PASSWORD]),
            redirect_stdout(output),
        ):
            Terminal(self.store).run()
        terminal_text = output.getvalue()
        for heading, count in (
            ("Browse Games", 32),
            ("Action-Adventure", len(self.store.catalogue(genre="Action-Adventure"))),
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
            "Orders completed   1", "Order History (newest first)", "Order total  ₹3,598.00",
            "Cyberpunk 2077 is back on sale.", "No games are off sale.",
        ):
            self.assertIn(message, terminal_text)
        self.assertEqual(self.store.get_game(3)["price"], Decimal("100.00"))
        self.assertTrue(self.store.get_game(3)["is_available"])
        with self.assertRaisesRegex(StoreError, "already owned"):
            self.store.add_to_cart(3)
        self.assertEqual([game["id"] for game in self.store.library()], [3, 7])
