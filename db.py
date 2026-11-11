"""MySQL settings, connection and transaction lifetime."""

import os
from contextlib import contextmanager, suppress
from getpass import getpass

import mysql.connector


def connection_settings():
    """Load local settings and prompt for the MySQL password if needed."""
    try:
        port = int(os.getenv("RAZE_DB_PORT", "3306"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("RAZE_DB_PORT must be a number from 1 to 65535.") from None

    user = os.getenv("RAZE_DB_USER", "root")
    password = os.getenv("RAZE_DB_PASSWORD")
    if password is None:
        password = getpass(f"MySQL password for {user}: ")
    return {
        "host": os.getenv("RAZE_DB_HOST", "127.0.0.1"),
        "port": port,
        "user": user,
        "password": password,
        "database": "raze",
        "charset": "utf8mb4",
        "connection_timeout": 5,
        "autocommit": False,
    }


@contextmanager
def database_cursor(settings, *, write=False):
    """Give each operation its own connection and commit only completed writes."""
    with mysql.connector.connect(**settings) as connection:
        with connection.cursor(dictionary=True) as cursor:
            try:
                yield cursor
                if write:
                    connection.commit()
            except BaseException:
                # If the connection itself failed, preserve the original error.
                with suppress(mysql.connector.Error):
                    connection.rollback()
                raise


def database_error_message(error):
    if error.errno in (1044, 1045, 1142):
        return "MySQL denied access. Check your MySQL credentials and database permissions."
    if error.errno in (1049, 1146):
        return "The RAZE database is missing or incomplete. Run setup.sql first."
    if error.errno in (1205, 1213):
        return "MySQL is busy. Please try again."
    if error.errno in (2002, 2003, 2005):
        return "Could not reach MySQL. Check that it is running and verify the host and port."
    if error.errno in (2006, 2013, 2055):
        return "MySQL disconnected. Check the library or catalogue before retrying a change."
    return f"MySQL could not complete the operation (error {error.errno})."
