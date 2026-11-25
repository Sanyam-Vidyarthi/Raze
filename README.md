# RAZE

RAZE is a CBSE Class XII Python–MySQL project that simulates a video game marketplace. The starter catalogue contains 32 games with prices in Indian rupees.

## Run RAZE

Start your local MySQL 8.0 server. In the project folder, run these commands with your Python environment active. Install the dependency once.

```sh
python -m pip install -r requirements.txt
python main.py
```

Enter your local MySQL username and password. The terminal displays the password as you type. On the first launch, `main.py` calls `setup.py` to create `raze_simple_db` and load all 32 games. The account needs `CREATE` and `REFERENCES` for setup, and `SELECT`, `INSERT` and `UPDATE` to use RAZE. Later launches keep your purchases, catalogue edits and sale availability. RAZE reports an error if it finds an incomplete or incompatible schema. The existing `raze` database is separate.

The three application files are `main.py` for the terminal menus, `store.py` for marketplace queries, and `setup.py` for database creation, schema checks and the starter catalogue. Run `python main.py` for both first-time setup and regular use.

Use the game IDs shown in the listings to view games and add them to the cart. The cart lasts for the current session. Simulated checkout saves purchases to one shared library. Use `raze-admin` to open the Administrator Panel.
