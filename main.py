"""Run RAZE in a Windows terminal."""

import sys
from getpass import getpass
from textwrap import wrap

from mysql.connector import Error as MySQLError

import store
from store import StoreError


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


def show_games(games, price_label="Price", show_availability=False):
    print(f'{"No.":>3} {"Game":26} {"Genre":19} {price_label:>14} Status')
    print("-" * 79)
    for index in range(len(games)):
        game = games[index]
        title_lines = wrap(game["title"], 26, break_on_hyphens=False)
        genre_lines = wrap(game["genre"], 19, break_on_hyphens=False)
        price = "—"
        if game["price"] is not None:
            price = money(game["price"])
        game_status = status(game)
        if show_availability:
            if game["is_available"]:
                game_status = "For sale"
            else:
                game_status = "Off sale"

        for line in range(max(len(title_lines), len(genre_lines))):
            title = ""
            genre = ""
            if line < len(title_lines):
                title = title_lines[line]
            if line < len(genre_lines):
                genre = genre_lines[line]
            if line == 0:
                print(f"{index + 1:>3} {title:26} {genre:19} {price:>14} {game_status}".rstrip())
            else:
                print(f"    {title:26} {genre}".rstrip())


def show_details(game, price_label="Price"):
    heading(game["title"])
    print(f'Genre      {game["genre"]}')
    print(f'Developer  {game["developer"]}')
    print(f'Platform   {game["platform"]}')
    print(f'{price_label:10} {money(game["price"])}')
    game_status = status(game)
    if game_status:
        print(f"Status     {game_status}")


def show_error(error):
    if isinstance(error, MySQLError):
        message = store.database_error_message(error)
    else:
        message = str(error)
    print(f"\n{message}")


def read_menu_choice(options, exit_label="Back"):
    print()
    for index in range(len(options)):
        print(f"{index + 1}. {options[index]}")
    exit_number = len(options) + 1
    print(f"{exit_number}. {exit_label}")

    while True:
        choice = input("Choose an option: ").strip()
        if choice == "0" or choice == str(exit_number):
            return 0
        for number in range(1, exit_number):
            if choice == str(number):
                return number
        print("Choose one of the numbered options.")


def main_menu(settings, cart_ids):
    options = (
        "Browse Games",
        "Search Games",
        "Browse by Genre",
        "Shopping Cart",
        "My Game Library",
        "Administrator Panel",
    )
    while True:
        heading("RAZE | VIDEO GAME MARKETPLACE")
        choice = read_menu_choice(options, "Exit")
        try:
            if choice == 0:
                return
            if choice == 1:
                game_picker(settings, cart_ids, "Browse Games", store.catalogue(settings))
            elif choice == 2:
                search(settings, cart_ids)
            elif choice == 3:
                browse_genres(settings, cart_ids)
            elif choice == 4:
                cart_menu(settings, cart_ids)
            elif choice == 5:
                library(settings)
            elif choice == 6:
                admin_menu(settings)
        except (StoreError, MySQLError) as error:
            show_error(error)


def search(settings, cart_ids):
    term = input("Search by title (blank to go back): ").strip()
    if term:
        game_picker(settings, cart_ids, "Search Results", store.catalogue(settings, search=term))

def browse_genres(settings, cart_ids):
    genres = store.genres(settings)
    if not genres:
        print("There are no genres available to browse.")
        return

    while True:
        heading("Browse by Genre")
        choice = read_menu_choice(genres)
        if choice == 0:
            return
        genre = genres[choice - 1]
        try:
            game_picker(settings, cart_ids, genre, store.catalogue(settings, genre=genre))
        except (StoreError, MySQLError) as error:
            show_error(error)


def game_picker(settings, cart_ids, title, games):
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
        store.add_to_cart(settings, cart_ids, game["id"])
        print(f'{game["title"]} added to your cart.')

def cart_menu(settings, cart_ids):
    options = ("Remove a Game", "Checkout")
    while True:
        heading("Shopping Cart")
        try:
            games = show_cart(settings, cart_ids)
            choice = read_menu_choice(options)
            if choice == 0:
                return
            if choice == 1:
                remove_cart_game(cart_ids, games)
            elif choice == 2:
                checkout(settings, cart_ids)
        except StoreError as error:
            show_error(error)
        except MySQLError as error:
            show_error(error)
            return


def show_cart(settings, cart_ids):
    catalogue_games = store.cart_games(settings, cart_ids)
    total = store.total_price(catalogue_games)

    # A deleted catalogue row can still be removed from the session's cart.
    games_by_id = {}
    for game in catalogue_games:
        games_by_id[game["id"]] = game

    games = []
    for game_id in sorted(cart_ids):
        if game_id in games_by_id:
            games.append(games_by_id[game_id])
        else:
            games.append({
                "id": game_id,
                "title": "Game no longer in catalogue",
                "genre": "",
                "price": None,
                "is_available": False,
            })

    if games:
        show_games(games)
    else:
        print("Your cart is empty.")
    print(f"Cart total  {money(total)}")
    return games


def remove_cart_game(cart_ids, games):
    if not games:
        print("Your cart is empty.")
        return
    game = select_game(games, "remove it from your cart")
    if game is not None:
        store.remove_from_cart(cart_ids, game["id"])
        print("Game removed from your cart.")

def checkout(settings, cart_ids):
    games = store.checkout_quote(settings, cart_ids)
    heading("Confirm Simulated Purchase")
    for game in games:
        print(f'  {game["title"]}  {money(game["price"])}')
    print(f"Final total  {money(store.total_price(games))}")
    if not confirm("Complete this simulated purchase?"):
        print("Checkout cancelled. Your cart is saved for this session.")
        return
    order_id = store.checkout(settings, cart_ids, games)
    print(f"Order #{order_id} complete. Find your games in My Game Library.")

def library(settings):
    heading("My Game Library")
    games = store.library(settings)
    if not games:
        print("Your library is empty.")
        return
    show_games(games, price_label="Paid")
    game = select_game(games, "view purchase details")
    if game is not None:
        show_details(game, price_label="Paid")
        print(f'Order      #{game["order_id"]} on {game["purchased_at"]:%d %b %Y}')

def admin_menu(settings):
    password = getpass("Demo administrator password (blank to go back): ")
    if not password:
        return
    if password != DEMO_ADMIN_PASSWORD:
        print("Administrator access denied.")
        return

    options = (
        "View Catalogue",
        "Add a Game",
        "Edit a Game",
        "Remove a Game from Sale",
        "View Sales Summary",
        "Put a Game Back on Sale",
    )
    while True:
        heading("Administrator Panel")
        choice = read_menu_choice(options)
        try:
            if choice == 0:
                return
            if choice == 1:
                admin_catalogue(settings)
            elif choice == 2:
                add_game(settings)
            elif choice == 3:
                edit_game(settings)
            elif choice == 4:
                delist_game(settings)
            elif choice == 5:
                sales(settings)
            elif choice == 6:
                relist_game(settings)
        except (StoreError, MySQLError) as error:
            show_error(error)


def admin_catalogue(settings):
    heading("Full Catalogue")
    game = select_admin_game(settings, "view its details")
    if game is not None:
        show_details(game)

def select_admin_game(settings, action, off_sale_only=False):
    games = store.catalogue(settings, include_unavailable=True)
    if off_sale_only:
        off_sale_games = []
        for game in games:
            if not game["is_available"]:
                off_sale_games.append(game)
        games = off_sale_games
        if not games:
            print("No games are off sale.")
            return None
    elif not games:
        print("There are no games in the catalogue.")
        return None

    show_games(games, show_availability=True)
    return select_game(games, action)


def add_game(settings):
    heading("Add a Game")
    details = game_form()
    if confirm("Add this game to the catalogue?"):
        store.save_game(settings, details)
        print(f'{details["title"]} added to the catalogue.')

def edit_game(settings):
    game = select_admin_game(settings, "edit it")
    if game is not None:
        heading(f'Edit {game["title"]}')
        print("Press Enter to keep the current value.")
        details = game_form(game)
        if confirm("Save these changes?"):
            store.save_game(settings, details, game["id"])
            print("Game details saved.")

def delist_game(settings):
    game = select_admin_game(settings, "remove it from sale")
    if game is not None:
        if not game["is_available"]:
            print("That game is already off sale.")
        elif confirm(f'Remove {game["title"]} from sale?'):
            store.remove_from_sale(settings, game["id"])
            print("Game removed from sale. Existing purchases are still in the library.")

def relist_game(settings):
    heading("Put a Game Back on Sale")
    game = select_admin_game(settings, "put it back on sale", off_sale_only=True)
    if game is not None and confirm(f'Put {game["title"]} back on sale?'):
        store.put_back_on_sale(settings, game["id"])
        print(f'{game["title"]} is back on sale.')

def sales(settings):
    summary = store.sales_summary(settings)
    heading("Sales Summary")
    print(f'Games purchased    {summary["games_sold"]:,}')
    print(f'Simulated revenue  {money(summary["revenue"])}')
    if summary["games_sold"] == 0:
        print("No purchases recorded yet.")


def game_form(current=None):
    details = {}
    for key, label, length in store.GAME_FIELDS:
        prompt = f"{label}: "
        if current is not None:
            prompt = f"{label} [{current[key]}]: "
        while True:
            value = input(prompt).strip()
            if not value and current is not None:
                value = current[key]
            try:
                details[key] = store.validate_text(value, label, length)
                break
            except StoreError as error:
                show_error(error)

    prompt = "Price in INR: "
    if current is not None:
        prompt = f'Price in INR [{current["price"]}]: '
    while True:
        value = input(prompt).strip()
        if not value and current is not None:
            value = str(current["price"])
        try:
            store.parse_price(value)
            details["price"] = value
            return details
        except StoreError as error:
            show_error(error)


def main():
    # Use UTF-8 for the rupee symbol in both the console and redirected output.
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        settings = store.connection_settings()
        cart_ids = []
        store.sales_summary(settings)  # Detect configuration or setup errors before opening the menu.
        main_menu(settings, cart_ids)
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
