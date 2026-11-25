"""Terminal menus and user input for RAZE."""

from mysql.connector import Error

import store


DEMO_ADMIN_PASSWORD = "raze-admin"


def read_game_id(prompt, allow_back=False):
    try:
        game_id = int(input(prompt))
        if game_id > 0:
            return game_id
        if allow_back and game_id == 0:
            return None
    except ValueError:
        pass
    print("Enter a valid game ID.")
    return None


def confirm(prompt):
    while True:
        answer = input(prompt + " (Y/N): ").strip().upper()
        if answer == "Y":
            return True
        if answer == "N":
            return False
        print("Enter Y or N.")


def choose_game(connection, cursor, games, cart):
    if not games:
        print("No games found.")
        return

    owned_ids = store.get_owned_ids(cursor)
    for game in games:
        status = "Unowned"
        if game[0] in owned_ids:
            status = "Owned"
        print(game[0], "-", game[1], "|", game[2], "| INR", game[3], "|", status)

    game_id = read_game_id("Enter a game ID to view details (0 to go back): ", True)
    if game_id is None:
        return
    for game in games:
        if game[0] == game_id:
            show_game_details(connection, cursor, game, cart, owned_ids)
            return
    print("No game with that ID is in this list.")


def show_game_details(connection, cursor, game, cart, owned_ids):
    print("\nTitle:", game[1])
    print("Genre:", game[2])
    print("Developer:", game[4])
    print("Platform:", game[5])
    print("Price: INR", game[3])

    problem = store.purchase_problem(game, owned_ids)
    if problem:
        print(problem)
    elif game[0] in cart:
        print("That game is already in your cart.")
    elif confirm("Add this game to your cart?"):
        # Read again in case the catalogue or library changed during the prompt.
        connection.rollback()
        current_game = store.get_game(cursor, game[0])
        problem = store.purchase_problem(current_game, store.get_owned_ids(cursor))
        if problem:
            print(problem)
        else:
            cart.append(game[0])
            print(game[1], "added to your cart.")


def browse_genres(connection, cursor, cart):
    genres = store.get_genres(cursor)
    if not genres:
        print("No genres are available.")
        return
    for row in genres:
        print(row[0])
    genre = input("Enter a genre (blank to go back): ").strip()
    if genre:
        choose_game(connection, cursor, store.get_games(cursor, genre=genre), cart)


def view_cart(cursor, cart):
    if not cart:
        print("Your cart is empty.")
        return
    total = 0
    for game_id in cart:
        game = store.get_game(cursor, game_id)
        if game is None:
            print(game_id, "- Game no longer in the catalogue")
        else:
            status = ""
            if not game[6]:
                status = "(Off sale)"
            print(game_id, "-", game[1], "| INR", game[3], status)
            total += game[3]
    print("Cart total: INR", total)


def checkout(connection, cursor, cart):
    games, problem = store.get_purchase_games(cursor, cart)
    if problem:
        print(problem)
        return

    print("\nSimulated Purchase")
    prices = []
    total = 0
    for game in games:
        print(game[0], "-", game[1], "| INR", game[3])
        prices.append(game[3])
        total += game[3]
    print("Final total: INR", total)
    if not confirm("Complete this purchase?"):
        print("Checkout cancelled. Your cart is saved.")
        return

    order_id, problem = store.purchase_games(connection, cursor, cart, prices)
    if problem:
        print(problem)
    else:
        cart[:] = []
        print("Order", order_id, "complete. Find your games in My Game Library.")


def shopping_cart(connection, cursor, cart):
    while True:
        print("\nShopping Cart")
        print("1. View Cart\n2. Remove a Game\n3. Checkout\n4. Back")
        choice = input("Enter your choice: ").strip()
        connection.rollback()
        if choice == "1":
            view_cart(cursor, cart)
        elif choice == "2":
            if not cart:
                print("Your cart is empty.")
            else:
                view_cart(cursor, cart)
                game_id = read_game_id("Enter the game ID to remove: ")
                if game_id in cart:
                    cart.remove(game_id)
                    print("Game removed from your cart.")
                elif game_id is not None:
                    print("That game is not in your cart.")
        elif choice == "3":
            checkout(connection, cursor, cart)
        elif choice == "4":
            return
        else:
            print("Invalid menu choice.")


def my_library(cursor):
    games = store.get_library(cursor)
    if not games:
        print("Your library is empty.")
    for game_id, title, genre, developer, platform, price, order_id, date in games:
        print("\n", game_id, "-", title, "|", genre)
        print("Developer:", developer, "| Platform:", platform)
        print("Paid: INR", price, "| Order:", order_id, "| Purchased:", date)


def valid_price(price):
    rupees, point, paise = price.partition(".")
    digits = "0123456789"
    if not rupees or len(rupees) > 8 or rupees.strip(digits):
        return False
    if point and (not paise or len(paise) > 2 or paise.strip(digits)):
        return False
    return True


def add_game(connection, cursor):
    title = input("Title: ").strip()
    genre = input("Genre: ").strip()
    developer = input("Developer: ").strip()
    platform = input("Platform: ").strip()
    price = input("Price in INR: ").strip()
    if not title or not genre or not developer or not platform:
        print("Title, genre, developer and platform are required.")
    elif not valid_price(price):
        print("Enter a price from 0 to 99999999.99 with at most two decimal places.")
    else:
        store.save_game(connection, cursor, (title, genre, developer, platform, price))
        print(title, "added to the catalogue.")


def edit_game(connection, cursor, game):
    print("Press Enter to keep the current value.")
    title = input("Title [" + game[1] + "]: ").strip() or game[1]
    genre = input("Genre [" + game[2] + "]: ").strip() or game[2]
    developer = input("Developer [" + game[4] + "]: ").strip() or game[4]
    platform = input("Platform [" + game[5] + "]: ").strip() or game[5]
    current_price = str(game[3])
    price = input("Price in INR [" + current_price + "]: ").strip() or current_price
    if not valid_price(price):
        print("Enter a price from 0 to 99999999.99 with at most two decimal places.")
        return
    store.save_game(connection, cursor, (title, genre, developer, platform, price), game[0])
    print("Game details saved.")


def admin_menu(connection, cursor):
    password = input("Demo administrator password (blank to go back): ")
    if not password:
        return
    if password != DEMO_ADMIN_PASSWORD:
        print("Administrator access denied.")
        return

    while True:
        print("\nAdministrator Panel")
        print("1. View Catalogue\n2. Add a Game\n3. Edit a Game")
        print("4. Remove a Game from Sale\n5. View Sales Summary")
        print("6. Put a Game Back on Sale\n7. Back")
        choice = input("Enter your choice: ").strip()
        try:
            connection.rollback()
            if choice == "1":
                for game in store.get_catalogue(cursor):
                    status = "Off sale"
                    if game[6]:
                        status = "For sale"
                    print(game[0], "-", game[1], "|", game[2], "| INR", game[3], "|", status)
            elif choice == "2":
                add_game(connection, cursor)
            elif choice in ("3", "4", "6"):
                game_id = read_game_id("Enter the game ID: ")
                if game_id is None:
                    continue
                game = store.get_game(cursor, game_id)
                if game is None:
                    print("No game has that ID.")
                elif choice == "3":
                    edit_game(connection, cursor, game)
                elif choice == "4":
                    if not game[6]:
                        print("That game is already off sale.")
                    elif confirm("Remove " + game[1] + " from sale?"):
                        store.change_availability(connection, cursor, game_id, 0)
                        print("Game removed from sale.")
                elif game[6]:
                    print("That game is already on sale.")
                else:
                    store.change_availability(connection, cursor, game_id, 1)
                    print("Game is back on sale.")
            elif choice == "5":
                quantity, revenue = store.sales_summary(cursor)
                print("Games purchased:", quantity)
                print("Simulated revenue: INR", revenue)
            elif choice == "7":
                return
            else:
                print("Invalid menu choice.")
        except Error as error:
            connection.rollback()
            print("MySQL could not complete the change:", error)


def main_menu(connection, cursor):
    cart = []
    while True:
        print("\nRAZE — VIDEO GAME MARKETPLACE")
        print("1. Browse Games\n2. Search Games\n3. Browse by Genre")
        print("4. Shopping Cart\n5. My Game Library\n6. Administrator Panel\n7. Exit")
        choice = input("Enter your choice: ").strip()
        try:
            connection.rollback()
            if choice == "1":
                choose_game(connection, cursor, store.get_games(cursor), cart)
            elif choice == "2":
                title = input("Search by title (blank to go back): ").strip()
                if title:
                    choose_game(connection, cursor, store.get_games(cursor, title=title), cart)
            elif choice == "3":
                browse_genres(connection, cursor, cart)
            elif choice == "4":
                shopping_cart(connection, cursor, cart)
            elif choice == "5":
                my_library(cursor)
            elif choice == "6":
                admin_menu(connection, cursor)
            elif choice == "7":
                return
            else:
                print("Invalid menu choice.")
        except Error as error:
            connection.rollback()
            print("MySQL could not complete the operation:", error)


def main():
    connection = None
    cursor = None
    try:
        username = input("MySQL username: ").strip()
        password = input("MySQL password: ")
        try:
            connection = store.connect_database(username, password)
            cursor = connection.cursor()
            if not store.setup_database(connection, cursor):
                print("Setup error: raze_simple_db has an incomplete or incompatible schema.")
                return
        except Error as error:
            print("MySQL setup failed. Check that MySQL is running and your account has access.")
            print(error)
            return
        except OSError as error:
            print("Setup could not read setup.sql:", error)
            return

        main_menu(connection, cursor)
    except (EOFError, KeyboardInterrupt):
        print("\nSession ended.")
    except Error as error:
        print("MySQL connection error:", error)
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
