"""Create and check RAZE's MySQL database."""

import mysql.connector


# Each game has an ID, title, genre, price, developer and platform.
# Prices are passed as text so MySQL stores them exactly as DECIMAL.
CATALOGUE = (
    (4, "Red Dead Redemption 2", "Action-Adventure", "3199.00", "Rockstar Games", "Windows"),
    (3, "Cyberpunk 2077", "RPG", "2999.00", "CD Projekt Red", "Windows"),
    (2, "Grand Theft Auto V", "Action-Adventure", "2499.00", "Rockstar North", "Windows"),
    (17, "The Witcher 3: Wild Hunt", "RPG", "1499.00", "CD Projekt Red", "Windows"),
    (25, "Ghost of Tsushima Director's Cut", "Action-Adventure", "3999.00", "Sucker Punch Productions / Nixxes Software", "Windows"),
    (26, "Ghost of Yōtei", "Action-Adventure", "4999.00", "Sucker Punch Productions", "PS5"),
    (27, "God of War Ragnarök", "Action-Adventure", "3999.00", "Santa Monica Studio / Jetpack Interactive", "Windows"),
    (13, "Forza Horizon 5", "Racing", "3499.00", "Playground Games", "Windows"),
    (22, "Subnautica", "Survival", "999.00", "Unknown Worlds Entertainment", "Windows"),
    (28, "Days Gone", "Action-Adventure", "2499.00", "Bend Studio", "Windows"),
    (29, "Detroit: Become Human", "Narrative Adventure", "1799.00", "Quantic Dream", "Windows"),
    (30, "The Last of Us Part I", "Action-Adventure", "3999.00", "Naughty Dog / Iron Galaxy Studios", "Windows"),
    (31, "Max Payne", "Shooter", "349.00", "Remedy Entertainment", "Windows"),
    (32, "Mafia: Definitive Edition", "Action-Adventure", "1999.00", "Hangar 13", "Windows"),
    (33, "Sleeping Dogs: Definitive Edition", "Action-Adventure", "999.00", "United Front Games", "Windows"),
    (34, "Uncharted: Legacy of Thieves Collection", "Action-Adventure", "3299.00", "Naughty Dog / Iron Galaxy Studios", "Windows"),
    (35, "Alan Wake 2", "Survival Horror", "3299.00", "Remedy Entertainment", "Windows"),
    (36, "Resident Evil 4 Remake", "Survival Horror", "2999.00", "Capcom", "Windows"),
    (37, "Counter-Strike 2", "Shooter", "0.00", "Valve", "Windows"),
    (38, "Life is Strange", "Narrative Adventure", "799.00", "Dontnod Entertainment", "Windows"),
    (5, "Elden Ring", "RPG", "3599.00", "FromSoftware", "Windows"),
    (39, "Sekiro: Shadows Die Twice", "Action-Adventure", "3299.00", "FromSoftware", "Windows"),
    (40, "Dark Souls III", "RPG", "2999.00", "FromSoftware", "Windows"),
    (41, "Lies of P", "RPG", "2999.00", "NEOWIZ / Round8 Studio", "Windows"),
    (42, "Black Myth: Wukong", "RPG", "3599.00", "Game Science", "Windows"),
    (7, "Hollow Knight", "Metroidvania", "599.00", "Team Cherry", "Windows"),
    (43, "Schedule I", "Simulation", "899.00", "TVGS", "Windows"),
    (44, "Lethal Company", "Survival Horror", "499.00", "Zeekerss", "Windows"),
    (45, "Phasmophobia", "Survival Horror", "899.00", "Kinetic Games", "Windows"),
    (46, "Fears to Fathom", "Horror", "499.00", "Rayll", "Windows"),
    (47, "Pacify", "Horror", "299.00", "Shawn Hitchcock", "Windows"),
    (48, "Getting Over It with Bennett Foddy", "Platformer", "349.00", "Bennett Foddy", "Windows"),
)


def setup_database(username, password):
    connection = mysql.connector.connect(
        host="127.0.0.1", user=username, password=password, charset="utf8mb4"
    )
    cursor = None
    ready = False
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW DATABASES")
        if ("raze_simple_db",) in cursor.fetchall():
            cursor.execute("USE raze_simple_db")
        else:
            create_database(connection, cursor)

        ready = check_schema(cursor)
        if ready:
            return connection
        return None
    finally:
        if cursor is not None:
            cursor.close()
        if not ready:
            connection.close()


def create_database(connection, cursor):
    cursor.execute("""
        CREATE DATABASE raze_simple_db
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    """)
    cursor.execute("USE raze_simple_db")
    cursor.execute("""
        CREATE TABLE games (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(120) NOT NULL UNIQUE,
            genre VARCHAR(40) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            developer VARCHAR(100) NOT NULL,
            platform VARCHAR(80) NOT NULL,
            is_available INT NOT NULL DEFAULT 1
        ) ENGINE = InnoDB
    """)
    cursor.execute("""
        CREATE TABLE orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            purchased_on DATE NOT NULL
        ) ENGINE = InnoDB
    """)

    for game in CATALOGUE:
        cursor.execute("""
            INSERT INTO games (id, title, genre, price, developer, platform)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, game)
    connection.commit()

    # The final table marks a completed setup after the catalogue is saved.
    cursor.execute("""
        CREATE TABLE order_items (
            game_id INT PRIMARY KEY,
            order_id INT NOT NULL,
            price_paid DECIMAL(10, 2) NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games(id),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        ) ENGINE = InnoDB
    """)


def check_schema(cursor):
    cursor.execute("SHOW TABLES")
    if sorted(cursor.fetchall()) != [("games",), ("order_items",), ("orders",)]:
        return False

    # DESCRIBE reports the name, type, nullability, key, default and extra details.
    columns = {
        "games": [
            ("id", "int", "NO", "PRI", None, "auto_increment"),
            ("title", "varchar(120)", "NO", "UNI", None, ""),
            ("genre", "varchar(40)", "NO", "", None, ""),
            ("price", "decimal(10,2)", "NO", "", None, ""),
            ("developer", "varchar(100)", "NO", "", None, ""),
            ("platform", "varchar(80)", "NO", "", None, ""),
            ("is_available", "int", "NO", "", "1", ""),
        ],
        "orders": [
            ("id", "int", "NO", "PRI", None, "auto_increment"),
            ("purchased_on", "date", "NO", "", None, ""),
        ],
        "order_items": [
            ("game_id", "int", "NO", "PRI", None, ""),
            ("order_id", "int", "NO", "MUL", None, ""),
            ("price_paid", "decimal(10,2)", "NO", "", None, ""),
        ],
    }
    for table in columns:
        cursor.execute("DESCRIBE " + table)
        if cursor.fetchall() != columns[table]:
            return False

        cursor.execute("SHOW CREATE TABLE " + table)
        definition = cursor.fetchone()[1]
        if "ENGINE=InnoDB" not in definition:
            return False
        if table == "order_items":
            if "FOREIGN KEY (`game_id`) REFERENCES `games` (`id`)" not in definition:
                return False
            if "FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`)" not in definition:
                return False

    cursor.execute("SHOW FULL COLUMNS FROM games WHERE Field IN ('title', 'genre')")
    for column in cursor.fetchall():
        if column[2] != "utf8mb4_0900_ai_ci":
            return False
    return True
