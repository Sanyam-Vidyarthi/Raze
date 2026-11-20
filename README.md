# RAZE

RAZE is a single-library video game marketplace for the Windows terminal. The initial MySQL catalogue contains 32 games, each listed with a genre, developer, platform and illustrative price in Indian rupees. The catalogue includes Windows games and Ghost of Yōtei for PS5.

## Setup on Windows (first installation)

You need Python 3.12 and MySQL Server 8.0.16 or later. MySQL Workbench is optional; it is a client, not the database server.

### 1. Start MySQL Server

Open Windows Services and start your MySQL service. On this PC the service is called `MySQL80`. If needed, run this in an **administrator PowerShell**:

```powershell
Start-Service MySQL80
```

### 2. Install Python dependencies

Open a normal PowerShell in the cloned repository folder (on this PC: `D:\Tech\Raze`). Run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

You do not need to activate the virtual environment; use its Python executable as shown.

### 3. Create the database and load the 32-game catalogue

Open a MySQL connection as `root` or another account allowed to create databases. In Workbench, open `setup.sql` from this repository and execute the **entire script**.

Alternatively, from the repository folder in PowerShell, open the MySQL command-line client:

```powershell
& 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe' --default-character-set=utf8mb4 -u root -p
```

Adjust that executable path if MySQL is installed elsewhere. When it shows `Enter password:`, type your **MySQL account password** and press Enter. Nothing appears while you type.

At the `mysql>` prompt, run:

```sql
source setup.sql
exit
```

`source` is a MySQL command-line client command. In Workbench, open the SQL file instead. A fresh database contains 32 games and no purchases.

### 4. Launch RAZE

Back in PowerShell, in the repository folder:

```powershell
.\.venv\Scripts\python.exe main.py
```

There are two different passwords:

| Prompt | Password to enter |
| --- | --- |
| `MySQL password for root:` at startup | Your own MySQL account password, chosen when you installed MySQL |
| Administrator Panel inside RAZE | `raze-admin` (demo password) |

RAZE uses one shared library, with no customer accounts. Checkout is simulated; it does not charge money or download games. Purchases persist in MySQL after you close the app. The cart only lasts for the current session.

## Run again after setup

Start MySQL if it is stopped, open PowerShell in the repository folder, and run:

```powershell
.\.venv\Scripts\python.exe main.py
```

You only need the setup steps once. Rerunning `setup.sql` **does not reset** purchases, catalogue edits or off-sale games.

## Reset all local RAZE data and start fresh

This permanently deletes the `raze` database, including its purchases, library ownership, added games and catalogue edits. It then restores the original 32-game catalogue. Close RAZE first. Other MySQL databases are outside this reset.

1. Start MySQL and open its command-line client from the repository folder using the command in step 3 above.
2. At the `mysql>` prompt, run:

   ```sql
   DROP DATABASE IF EXISTS raze;
   source setup.sql
   SELECT COUNT(*) AS games FROM raze.games;
   SELECT COUNT(*) AS orders FROM raze.orders;
   SELECT COUNT(*) AS purchased_games FROM raze.order_items;
   exit
   ```

   Expected counts: **32 games, 0 orders, 0 purchased games**. In Workbench, execute `DROP DATABASE IF EXISTS raze;`, then open and execute the entire `setup.sql` file.

3. If you also want to rebuild Python dependencies, run the following in PowerShell from the repository folder. These commands delete only this checkout's environment and Python caches:

   ```powershell
   Remove-Item -LiteralPath .\.venv -Recurse -Force -ErrorAction SilentlyContinue
   Remove-Item -LiteralPath .\__pycache__ -Recurse -Force -ErrorAction SilentlyContinue
   Remove-Item -LiteralPath .\tests\__pycache__ -Recurse -Force -ErrorAction SilentlyContinue
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Launch `main.py` using step 4 above. The game library will be empty.

The application stores its persistent data in MySQL, not in `.venv` or the repository. Deleting Python files or recreating `.venv` alone will not clear purchases.

## Optional: update an old catalogue without deleting purchases

Only use this if you have the original 24-game installation and want to keep its purchase history:

```powershell
.\.venv\Scripts\python.exe update_catalogue.py
```

Sign in with your MySQL account. The updater puts the current 32 titles on sale and takes titles outside that list off sale. It preserves orders, library ownership and historical prices. It is not a reset. The account also needs permission to create temporary tables.

## Connection settings

The default connection is `root` on `127.0.0.1:3306`, using database `raze`. Set these PowerShell environment variables before launching if your server uses different settings:

| Variable | Default |
| --- | --- |
| `RAZE_DB_HOST` | `127.0.0.1` |
| `RAZE_DB_PORT` | `3306` |
| `RAZE_DB_USER` | `root` |
| `RAZE_DB_PASSWORD` | Prompted on startup if unset |

For example, `$env:RAZE_DB_PORT = '3307'` sets the port for the current PowerShell session. An account used to run RAZE needs `SELECT`, `INSERT` and `UPDATE` privileges on `raze.*`. Keep passwords out of source files and Git commits.

## Troubleshooting

| Message or problem | What to do |
| --- | --- |
| Cannot connect / error 2003 | Start MySQL Server and check the host and port. Opening Workbench alone does not start the server. |
| Access denied / error 1045 | Check your MySQL username and password. `raze-admin` only works inside the application's Administrator Panel. |
| Unknown database or missing table | Execute the entire `setup.sql` file against the same server the app connects to. |
| `No module named mysql` | Install `requirements.txt` using `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`. |
| `mysql` is not recognized | Use the full `mysql.exe` path from step 3 or open the script in Workbench. |
| Old purchases or edits still appear | Follow the reset section. Rerunning setup or reinstalling Python dependencies preserves database data. |

## Try a purchase

Open Browse Games, Search Games or Browse by Genre. Enter the number next to a game in the current list to see its details and add it to your cart. Numbering starts at 1 in each list. Repeat for a second game. Open Shopping Cart, select Checkout and confirm the simulated purchase. Both games will appear in My Game Library, including after you close and reopen RAZE.

In the Administrator Panel, choose **Put a Game Back on Sale** to restore a game to customer browsing. **View Sales Summary** shows games purchased and simulated revenue. My Game Library shows each purchased game and the price paid.

## School submission files

| File | Responsibility |
| --- | --- |
| `main.py` | Terminal menus, prompts and formatting |
| `store.py` | MySQL connectivity, catalogue queries, cart rules, checkout, library and admin operations |
| `setup.sql` | Tables, constraints and the initial catalogue |

These three files are sufficient with MySQL Connector/Python installed. The repository also includes a dependency list, automated tests and the optional catalogue updater.

The cart holds game IDs in memory. The `games` table stores catalogue data and sale availability. One `orders` row represents a completed checkout, and one `order_items` row per game stores its order ID and price paid. The library and sales summary read those purchase records.

### Concepts for the viva

Trace a checkout from `main_menu()` to `cart_menu()` and then to `store.checkout()`. The menus use ordinary loops and `if/elif` statements. A list holds the session's cart and a dictionary holds its connection settings.

- **Python and MySQL.** `connect_database()` calls `mysql.connector.connect()`. A cursor runs SQL and fetches results. Browse uses `SELECT`, adding a game uses `INSERT`, and editing or changing sale availability uses `UPDATE`.
- **Transactions.** Checkout validates the cart, inserts the order and adds each item in one transaction. `commit()` saves the complete purchase. If a write fails, `rollback()` undoes the earlier writes in that checkout.
- **Resource cleanup.** A `finally` block closes the cursor and connection when a database operation ends. Checkout also attempts rollback if interrupted.
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
