"""Replace the previous storefront lineup while retaining all purchase records."""

from pathlib import Path

from mysql.connector import Error

from db import connection_settings, database_cursor, database_error_message


def update_catalogue(settings):
    setup = Path(__file__).with_name("setup.sql").read_text(encoding="utf-8")
    _, marker, seed = setup.partition("-- Catalogue seed\n")
    if not marker:
        raise ValueError("Catalogue seed is missing from setup.sql.")
    seed = seed.replace("INSERT INTO games ", "INSERT INTO catalogue_seed ", 1)
    seed = seed.replace("id = games.id", "id = catalogue_seed.id", 1)

    with database_cursor(settings, write=True) as cursor:
        cursor.execute("CREATE TEMPORARY TABLE catalogue_seed LIKE games")
        cursor.execute(seed)
        cursor.execute("SELECT COUNT(*) AS total FROM catalogue_seed")
        total = cursor.fetchone()["total"]
        if total != 32:
            raise ValueError(f"Expected 32 catalogue entries, found {total}.")

        # Lock the existing catalogue while mapping names to IDs. Checkout and
        # catalogue edits use the same game rows.
        cursor.execute("SELECT id FROM games ORDER BY id FOR UPDATE")
        cursor.fetchall()

        # Reuse the old GTA V ID so a previous purchase still marks it as owned.
        cursor.execute("""
            UPDATE games AS legacy
            LEFT JOIN games AS current ON current.title = 'Grand Theft Auto V'
            SET legacy.title = 'Grand Theft Auto V'
            WHERE legacy.title = 'Grand Theft Auto V Enhanced' AND current.id IS NULL
        """)
        cursor.execute("""
            INSERT INTO games (title, genre, price, developer, platform)
            SELECT seed.title, seed.genre, seed.price, seed.developer, seed.platform
            FROM catalogue_seed AS seed
            LEFT JOIN games AS g ON g.title = seed.title
            WHERE g.id IS NULL
            ORDER BY seed.id
        """)
        cursor.execute("""
            UPDATE games AS g
            LEFT JOIN catalogue_seed AS seed ON seed.title = g.title
            SET g.is_available = (seed.id IS NOT NULL)
            WHERE g.is_available <> (seed.id IS NOT NULL)
        """)
        cursor.execute("SELECT COUNT(*) AS total FROM games WHERE is_available = TRUE")
        available = cursor.fetchone()["total"]
        if available != total:
            raise ValueError(f"Expected {total} games for sale, found {available}.")
        return available


def main():
    try:
        available = update_catalogue(connection_settings())
    except (EOFError, KeyboardInterrupt):
        print("\nCatalogue update cancelled.")
        return 1
    except ValueError as error:
        print(error)
        return 1
    except Error as error:
        print(database_error_message(error))
        return 1
    print(f"Catalogue updated. {available} games are available for sale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
