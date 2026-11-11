"""Run RAZE in a Windows terminal."""

import sys
from getpass import getpass
from shutil import get_terminal_size
from textwrap import wrap

from mysql.connector import Error as MySQLError

from db import connection_settings, database_error_message
from store import GAME_FIELDS, Marketplace, StoreError, parse_price, total_price, validate_text


DEMO_ADMIN_PASSWORD = "raze-admin"


def money(price):
    return f"₹{price:,.2f}"


def heading(title):
    print(f"\n{title}")
    print("-" * len(title))


def select_game(games, action):
    print(f"Enter a game number to {action}.")
    while True:
        value = input("Game number (0 to go back): ").strip()
        if value.isascii() and value.isdecimal() and len(value) <= 10:
            number = int(value)
            if number == 0:
                return None
            if 1 <= number <= len(games):
                return games[number - 1]
        print(f"Enter a game number from 1 to {len(games)}, or 0 to go back.")


def confirm(prompt):
    while True:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        print("Enter Y or N.")


def status(game):
    if game.get("owned"):
        return "Already owned"
    if not game["is_available"]:
        return "Off sale"
    return ""


def show_games(games, *, price_label="Price", status_text=status):
    headers = ("No.", "Game", "Genre", price_label, "Status")
    rows = [
        (
            str(number), game["title"], game["genre"],
            money(game["price"]) if game["price"] is not None else "—",
            status_text(game),
        )
        for number, game in enumerate(games, 1)
    ]
    if not any(row[4] for row in rows):
        headers = headers[:4]
        rows = [row[:4] for row in rows]

    widths = [max(map(len, column)) for column in zip(headers, *rows)]
    terminal_width = get_terminal_size(fallback=(100, 24)).columns - 1
    gap = "  "
    if sum(widths) + len(gap) * (len(headers) - 1) > terminal_width:
        gap = " "
    fixed_width = widths[0] + sum(widths[3:]) + len(gap) * (len(headers) - 1)
    # On narrow terminals, wrap long titles and genres while keeping numbers and prices intact.
    text_width = max(len("Game") + len("Genre"), terminal_width - fixed_width)
    widths[2] = min(widths[2], max(len("Genre"), text_width // 2))
    widths[1] = min(widths[1], text_width - widths[2])

    def print_row(cells):
        aligned = [
            cell.rjust(width) if index in (0, 3) else cell.ljust(width)
            for index, (cell, width) in enumerate(zip(cells, widths))
        ]
        print(gap.join(aligned).rstrip())

    print_row(headers)
    print("-" * (sum(widths) + len(gap) * (len(headers) - 1)))
    for row in rows:
        columns = [wrap(cell, width, break_on_hyphens=False) for cell, width in zip(row, widths)]
        for line in range(max(map(len, columns))):
            print_row([column[line] if line < len(column) else "" for column in columns])


def show_details(game, price_label="Price"):
    heading(game["title"])
    print(f'Genre      {game["genre"]}')
    print(f'Developer  {game["developer"]}')
    print(f'Platform   {game["platform"]}')
    print(f'{price_label:10} {money(game["price"])}')
    if status(game):
        print(f"Status     {status(game)}")


def show_error(error):
    message = database_error_message(error) if isinstance(error, MySQLError) else str(error)
    print(f"\n{message}")


def menu(title, actions, *, exit_label="Back", show_context=None):
    while True:
        heading(title)
        try:
            if show_context is not None:
                show_context()
            print()
            for number, (label, _) in enumerate(actions, 1):
                print(f"{number}. {label}")
            exit_choice = str(len(actions) + 1)
            print(f"{exit_choice}. {exit_label}")
            choice = input("Choose an option: ").strip()
            if choice in (exit_choice, "0"):
                return
            if choice not in [str(number) for number in range(1, len(actions) + 1)]:
                print("Choose one of the numbered options.")
                continue
            actions[int(choice) - 1][1]()
        except (StoreError, MySQLError) as error:
            show_error(error)
            if show_context is not None and isinstance(error, MySQLError):
                return


class Terminal:
    def __init__(self, marketplace):
        self.store = marketplace

    def run(self):
        menu(
            "RAZE | VIDEO GAME MARKETPLACE",
            [
                ("Browse Games", self.browse),
                ("Search Games", self.search),
                ("Browse by Genre", self.browse_genres),
                ("Shopping Cart", self.cart),
                ("My Game Library", self.library),
                ("Administrator Panel", self.admin),
            ],
            exit_label="Exit",
        )

    def browse(self):
        self.game_picker("Browse Games", self.store.catalogue())

    def search(self):
        term = input("Search by title (blank to go back): ").strip()
        if term:
            self.game_picker("Search Results", self.store.catalogue(search=term))

    def browse_genres(self):
        genres = self.store.genres()
        if not genres:
            print("There are no genres available to browse.")
            return
        actions = [
            (genre, lambda genre=genre: self.game_picker(genre, self.store.catalogue(genre=genre)))
            for genre in genres
        ]
        menu("Browse by Genre", actions)

    def game_picker(self, title, games):
        heading(title)
        if not games:
            print("No games found.")
            return
        show_games(games)
        game = select_game(games, "view details or add the game to your cart")
        if game is None:
            return

        show_details(game)
        if not game["owned"] and confirm("Add to cart?"):
            self.store.add_to_cart(game["id"])
            print(f'{game["title"]} added to your cart.')

    def cart(self):
        games = []

        def refresh_cart():
            nonlocal games
            games = self.show_cart()

        menu(
            "Shopping Cart",
            [("Remove a Game", lambda: self.remove_cart_game(games)), ("Checkout", self.checkout)],
            show_context=refresh_cart,
        )

    def show_cart(self):
        games = self.store.cart_games()
        total = total_price(games)
        missing_ids = set(self.store.cart_ids) - {game["id"] for game in games}
        games.extend(
            {
                "id": game_id, "title": "Game no longer in catalogue", "genre": "",
                "price": None, "is_available": False,
            }
            for game_id in missing_ids
        )
        games.sort(key=lambda game: game["id"])
        if games:
            show_games(games)
        else:
            print("Your cart is empty.")
        print(f"Cart total  {money(total)}")
        return games

    def remove_cart_game(self, games):
        if not games:
            print("Your cart is empty.")
            return
        game = select_game(games, "remove it from your cart")
        if game is not None:
            self.store.remove_from_cart(game["id"])
            print("Game removed from your cart.")

    def checkout(self):
        games = self.store.checkout_quote()
        heading("Confirm Simulated Purchase")
        show_games(games)
        print(f"Final total  {money(total_price(games))}")
        if not confirm("Complete this simulated purchase?"):
            print("Checkout cancelled. Your cart is saved for this session.")
            return
        order_id = self.store.checkout(games)
        print(f"Order #{order_id} complete. Find your games in My Game Library.")

    def library(self):
        heading("My Game Library")
        games = self.store.library()
        if not games:
            print("Your library is empty.")
            return
        show_games(games, price_label="Paid")
        game = select_game(games, "view purchase details")
        if game is not None:
            show_details(game, price_label="Paid")
            print(f'Order      #{game["order_id"]} on {game["purchased_at"]:%d %b %Y}')

    def admin(self):
        password = getpass("Demo administrator password (blank to go back): ")
        if not password:
            return
        if password != DEMO_ADMIN_PASSWORD:
            print("Administrator access denied.")
            return
        menu(
            "Administrator Panel",
            [
                ("View Catalogue", self.admin_catalogue),
                ("Add a Game", self.add_game),
                ("Edit a Game", self.edit_game),
                ("Remove a Game from Sale", self.delist_game),
                ("View Sales Summary", self.sales),
                ("Put a Game Back on Sale", self.relist_game),
            ],
        )

    def admin_catalogue(self):
        heading("Full Catalogue")
        game = self.select_admin_game("view its details")
        if game is not None:
            show_details(game)

    def select_admin_game(self, action, *, off_sale_only=False):
        games = self.store.catalogue(include_unavailable=True)
        if off_sale_only:
            games = [game for game in games if not game["is_available"]]
        if not games:
            print("No games are off sale." if off_sale_only else "There are no games in the catalogue.")
            return None
        show_games(
            games, status_text=lambda game: "For sale" if game["is_available"] else "Off sale"
        )
        return select_game(games, action)

    def add_game(self):
        heading("Add a Game")
        details = game_form()
        if confirm("Add this game to the catalogue?"):
            self.store.save_game(details)
            print(f'{details["title"]} added to the catalogue.')

    def edit_game(self):
        game = self.select_admin_game("edit it")
        if game is not None:
            heading(f'Edit {game["title"]}')
            print("Press Enter to keep the current value.")
            details = game_form(game)
            if confirm("Save these changes?"):
                self.store.save_game(details, game["id"])
                print("Game details saved.")

    def delist_game(self):
        game = self.select_admin_game("remove it from sale")
        if game is not None:
            if not game["is_available"]:
                print("That game is already off sale.")
            elif confirm(f'Remove {game["title"]} from sale?'):
                self.store.remove_from_sale(game["id"])
                print("Game removed from sale. Existing purchases are still in the library.")

    def relist_game(self):
        heading("Put a Game Back on Sale")
        game = self.select_admin_game("put it back on sale", off_sale_only=True)
        if game is not None and confirm(f'Put {game["title"]} back on sale?'):
            self.store.put_back_on_sale(game["id"])
            print(f'{game["title"]} is back on sale.')

    def sales(self):
        report = self.store.sales_report()
        orders = report["orders"]
        heading("Sales Summary")
        print(f'Orders completed   {len(orders):,}')
        print(f'Games purchased    {report["games_sold"]:,}')
        print(f'Simulated revenue  {money(report["revenue"])}')
        if not orders:
            print("\nNo purchases recorded yet.")
            return

        heading("Order History (newest first)")
        for order in orders:
            heading(f'Order #{order["id"]} | {order["purchased_at"]:%d %b %Y, %I:%M %p}')
            games = order["games"]
            show_games(games, price_label="Paid")
            print(f"Order total  {money(total_price(games))}")


def game_form(current=None):
    details = {}
    for key, label, length in GAME_FIELDS:
        while True:
            value = input(f"{label} [{current[key]}]: " if current else f"{label}: ").strip()
            try:
                details[key] = validate_text(value or (current[key] if current else ""), label, length)
                break
            except StoreError as error:
                show_error(error)
    while True:
        prompt = f'Price in INR [{current["price"]}]: ' if current else "Price in INR: "
        value = input(prompt).strip() or (str(current["price"]) if current else "")
        try:
            parse_price(value)
            details["price"] = value
            return details
        except StoreError as error:
            show_error(error)


def main():
    # Use UTF-8 for the rupee symbol in both the console and redirected output.
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        store = Marketplace(connection_settings())
        store.sales_summary()  # Detect configuration or setup errors before opening the menu.
        Terminal(store).run()
    except (KeyboardInterrupt, EOFError):
        print("\nSession ended.")
    except (ValueError, MySQLError) as error:
        show_error(error)
        return 1
    else:
        print("\nThanks for visiting RAZE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
