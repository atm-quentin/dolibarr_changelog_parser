import sqlite3

class DbHandler:
    """
    Manages changelog data stored in an SQLite database.
    Each instance handles operations for a specific changelog version.
    """

    def __init__(self, version: str, db_name: str = "changelog_parser.sqlite3"):
        """
        Initializes the DbHandler for a specific version.

        Args:
            version (str): The version of the changelog (e.g., "18.0").
            db_name (str, optional): The name of the SQLite database file.
                                     Defaults to "changelog_parser".
        """
        self.db_name = db_name
        self.version = version
        # Ensure the table name is valid for SQL by replacing dots or other disallowed characters if necessary.
        # For this example, assuming version format like "18.0" is fine, but be cautious with arbitrary strings.
        sanitized_version_string = str(version).replace('.', '_') # Example sanitization
        self.table_name = f"changelog_dolibarr_line_v{sanitized_version_string}"

    def _get_db_connection(self):
        """
        Establishes and returns a database connection.
        The connection is configured to return rows that can be accessed by column name.

        Returns:
            sqlite3.Connection: The database connection object.
        """
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row  # To access columns by name
        return conn

    def create_changelog_table(self):
        """
        Creates the changelog table for the instance's version if it doesn't already exist.
        The table includes columns for ID, type, content, support status, completion status,
        PR description, link, diff, and token count.
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT, -- 'dev' ou 'user'
                line_content TEXT NOT NULL UNIQUE, -- Ensure uniqueness of raw content
                not_supported BOOLEAN DEFAULT FALSE,
                not_supported_reason TEXT,
                is_done BOOLEAN DEFAULT FALSE,
                pr_desc TEXT,
                link TEXT,
                diff TEXT,
                desc_and_diff_tokens INTEGER
            )
            """)
            # The comma after desc_and_diff_tokens INTEGER was an error in your original schema
            # It has been removed above.
            conn.commit()
            print(f"Table {self.table_name} checked/created in {self.db_name}")
        except sqlite3.Error as e:
            print(f"SQLite error creating table {self.table_name}: {e}")
        finally:
            conn.close()

    def insert_changelog_line(self, line_content: str, line_type: str = None):
        """
        Inserts a raw changelog line into the database.

        Args:
            line_content (str): The raw content of the changelog line.
            line_type (str, optional): The type of the changelog line (e.g., 'dev', 'user').
                                       Defaults to None.

        Returns:
            int or None: The ID of the newly inserted row, or None if insertion failed
                         (e.g., due to a UNIQUE constraint violation or other error).
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
            INSERT INTO {self.table_name} (line_content, type)
            VALUES (?, ?)
            """, (line_content, line_type))
            conn.commit()
            # print(f"Inserted line into {self.table_name}: {line_content[:50]}...")
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            print(f"Line already exists in {self.table_name} (UNIQUE constraint): {line_content[:50]}...")
            return None
        except sqlite3.Error as e:
            print(f"SQLite error inserting line into {self.table_name}: {e}")
            return None
        finally:
            conn.close()

    def update_changelog_line(self, line_id: int, data: dict):
        """
        Updates a changelog line with processed data.

        Args:
            line_id (int): The ID of the changelog line to update.
            data (dict): A dictionary where keys are column names and values are the new data.
                         Example: {'pr_desc': 'New description', 'is_done': True}
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        set_clauses = []
        values = []
        for key, value in data.items():
            set_clauses.append(f"{key} = ?")
            values.append(value)

        if not set_clauses:
            print("No data provided for update.")
            conn.close() # Ensure connection is closed even if no update
            return

        values.append(line_id) # For the WHERE clause
        sql = f"UPDATE {self.table_name} SET {', '.join(set_clauses)} WHERE id = ?"

        try:
            cursor.execute(sql, tuple(values))
            conn.commit()
            # print(f"Updated line ID {line_id} in {self.table_name}")
        except sqlite3.Error as e:
            print(f"SQLite error updating line ID {line_id} in {self.table_name}: {e}")
        finally:
            conn.close()

    def get_lines_to_process(self, limit: int = None, random_selection: bool = False):
        """
        Fetches lines that are not yet marked as 'is_done' and not marked as 'not_supported'.

        Args:
            limit (int, optional): The maximum number of lines to fetch. Defaults to None (no limit).
            random_selection (bool, optional): If True, fetches lines in a random order.
                                               Defaults to False.

        Returns:
            list: A list of rows (as sqlite3.Row objects) to be processed.
                  Returns an empty list if an error occurs or no lines are found.
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()
        sql = f"SELECT * FROM {self.table_name} WHERE is_done = FALSE AND not_supported = FALSE"

        if random_selection:
            sql += " ORDER BY RANDOM()"
        if limit is not None: # Check for None explicitly, as limit could be 0
            sql += f" LIMIT {limit}"

        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            # print(f"Fetched {len(rows)} lines to process from {self.table_name}")
            return rows
        except sqlite3.Error as e:
            print(f"SQLite error fetching lines to process from {self.table_name}: {e}")
            return []
        finally:
            conn.close()