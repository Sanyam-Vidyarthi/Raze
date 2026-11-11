# RAZE

RAZE is a single-library video game marketplace for the Windows terminal. The initial MySQL catalogue contains 32 games, each listed with a genre, developer, platform and illustrative price in Indian rupees. The catalogue includes Windows games and Ghost of Yōtei for PS5.

## Run on Windows

Use Python 3.12 and MySQL Server 8.0.16 or later. The app was tested with Python 3.12 and MySQL 8.0.46.

1. Start the MySQL service if it is stopped. On this PC it is named `MySQL80`. You can start it from Windows Services or run `Start-Service MySQL80` in an administrator PowerShell window.
2. For a fresh installation, connect to the local server in MySQL Workbench with a MySQL account that can create databases. Open `setup.sql` as an SQL script and execute the entire file. It creates and seeds the `raze` database. If you already installed the original 24-game catalogue, use the update below.
3. In PowerShell, open the project directory and run:

   ```powershell
   Set-Location D:\Tech\Raze
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe main.py
   ```

4. At the startup prompt, enter your **MySQL account password**. The default connection is `root` on `127.0.0.1:3306`. Inside RAZE, the separate demo administrator password is **`raze-admin`**.

To run setup from the MySQL command-line client instead of Workbench, connect with `mysql --default-character-set=utf8mb4 -u root -p` and enter `source D:/Tech/Raze/setup.sql` at the `mysql>` prompt. If `mysql` is missing from PATH, run `mysql.exe` from the MySQL installation's `bin` folder.

### Update the original 24-game catalogue

From the project directory, run `.\.venv\Scripts\python.exe update_catalogue.py` and sign in with your MySQL account. The update puts the requested 32 titles on sale and takes the previous titles outside that list off sale. It preserves orders, library ownership and historical prices. The account running the update also needs permission to create temporary tables.

### Connection settings

Set these PowerShell environment variables before launching if your server uses different settings. The defaults are in `db.py`.

| Variable | Default |
| --- | --- |
| `RAZE_DB_HOST` | `127.0.0.1` |
| `RAZE_DB_PORT` | `3306` |
| `RAZE_DB_USER` | `root` |
| `RAZE_DB_PASSWORD` | Prompted on startup if unset |

For example, `$env:RAZE_DB_PORT = '3307'` sets the port for the current PowerShell session. An account used to run RAZE needs `SELECT`, `INSERT` and `UPDATE` privileges on `raze.*`.

### Try a purchase

Open Browse Games, Search Games or Browse by Genre. Enter the number next to a game in the current list to see its details and add it to your cart. Numbering starts at 1 in each list. Repeat for a second game. Open Shopping Cart, select Checkout and confirm the simulated purchase. Both games will appear in My Game Library, including after you close and reopen RAZE.

In the Administrator Panel, choose **Put a Game Back on Sale** to restore a game to customer browsing. **View Sales Summary** shows total orders, games purchased, simulated revenue and the games and prices paid in each order.

## Code and database

| File | Responsibility |
| --- | --- |
| `main.py` | Terminal menus, prompts and formatting |
| `store.py` | Catalogue queries, cart rules, checkout, library and admin operations |
| `db.py` | MySQL settings, connection handling and transaction boundaries |
| `setup.sql` | Tables, constraints and the initial catalogue |

The cart holds game IDs in memory. The `games` table stores catalogue data and sale availability. One `orders` row represents a completed checkout, and one `order_items` row per game stores its order ID and price paid. The library and sales summary query those purchase records. A Tkinter interface can call the same `Marketplace` methods.

### Concepts for the viva

- **Transactions.** Checkout validates the cart, inserts the order and adds each item in one transaction. `commit()` saves the complete purchase. If a write fails, `rollback()` undoes the earlier writes in that checkout.
- **Row locks and keys.** `SELECT ... FOR UPDATE` locks selected game rows while checkout checks availability, ownership and the confirmed prices. The primary key on `order_items.game_id` enforces one purchase per game for the shared library. Foreign keys link each purchase to an existing game and order.
- **Exact prices.** MySQL `DECIMAL` and Python `Decimal` represent rupees and paise exactly. Storing `price_paid` in the order item preserves the sale price when an administrator edits the catalogue price.
- **Parameterized SQL and soft deletion.** Values supplied through `cursor.execute()` parameters are treated as data, including titles with apostrophes. Removing a game from sale updates its availability flag, preserving the catalogue row referenced by past purchases.

## Run the live checks

The integration suite creates and drops randomly named `raze_test_…` databases. Use a local MySQL account with permission to create and drop schemas and create triggers. The tests use the same connection settings as the application.

```powershell
$env:RAZE_RUN_MYSQL_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:RAZE_RUN_MYSQL_TESTS
```

The checks exercise discovery, validation, checkout, ownership persistence, sales, administrator edits, concurrent purchases, rollback after a forced item failure and the terminal menu flow.
