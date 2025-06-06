# app/db_handler.py
import os
import sqlite3
from typing import List, Optional, Dict, Any
from app.logger import global_logger

class DbHandler:
    """
    Gère les données du changelog stockées dans une base de données SQLite.
    Chaque instance gère les opérations pour une version spécifique du changelog.
    """

    def __init__(self, version: str, db_name: str = "changelog_parser.sqlite3") -> None:
        """
        Initialise le DbHandler pour une version spécifique.

        Args:
            version (str): La version du changelog (ex: "18.0").
            db_name (str, optional): Le nom du fichier de base de données SQLite.
                                     Par défaut "changelog_parser.sqlite3".
        """
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)

        self.db_path = os.path.join(self.data_dir, db_name)
        self.version = version

        sanitized_version_string = str(version).replace('.', '_')
        self.table_name = f"changelog_dolibarr_line_v{sanitized_version_string}"

    def _get_db_connection(self) -> sqlite3.Connection:
        """
        Établit et retourne une connexion à la base de données.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_changelog_table(self) -> None:
        """
        Crée la table du changelog pour la version de l'instance si elle n'existe pas.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT, -- 'dev' ou 'user'
                line_content TEXT NOT NULL UNIQUE,
                not_supported BOOLEAN DEFAULT FALSE,
                not_supported_reason TEXT,
                is_done BOOLEAN DEFAULT FALSE,
                pr_desc TEXT,
                link TEXT,
                diff TEXT,
                desc_and_diff_tokens INTEGER
            )
            """)
            conn.commit()
            global_logger.info(f"Table {self.table_name} vérifiée/créée dans {self.db_path}")
        except sqlite3.Error as e:
            global_logger.error(f"Erreur SQLite lors de la création de la table {self.table_name}: {e}")
        finally:
            conn.close()

    def insert_changelog_line(self, line_content: str, line_type: Optional[str] = None) -> Optional[int]:
        """
        Insère une ligne brute du changelog dans la base de données.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
            INSERT INTO {self.table_name} (line_content, type)
            VALUES (?, ?)
            """, (line_content, line_type))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Cas normal si la ligne existe déjà (contrainte UNIQUE), un log de bas niveau est approprié.
            global_logger.debug(f"La ligne existe déjà dans {self.table_name}: {line_content[:70]}...")
            return None
        except sqlite3.Error as e:
            global_logger.error(f"Erreur SQLite lors de l'insertion dans {self.table_name}: {e}")
            return None
        finally:
            conn.close()

    def update_changelog_line(self, line_id: int, data: Dict[str, Any]) -> None:
        """
        Met à jour une ligne du changelog avec des données traitées.
        """
        if not data:
            global_logger.warning("Aucune donnée fournie pour la mise à jour de la ligne ID {line_id}.")
            return

        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            set_clauses = [f"{key} = ?" for key in data.keys()]
            values = list(data.values())
            values.append(line_id)

            sql = f"UPDATE {self.table_name} SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(sql, tuple(values))
            conn.commit()
        except sqlite3.Error as e:
            global_logger.error(f"Erreur SQLite lors de la mise à jour de la ligne ID {line_id} dans {self.table_name}: {e}")
        finally:
            conn.close()

    def get_lines_to_process(self, limit: Optional[int] = None, random_selection: bool = False) -> List[sqlite3.Row]:
        """
        Récupère les lignes qui ne sont pas encore marquées comme 'is_done' et 'not_supported'.
        """
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            sql = f"SELECT * FROM {self.table_name} WHERE is_done = FALSE AND not_supported = FALSE"

            if random_selection:
                sql += " ORDER BY RANDOM()"
            else:
                sql += " ORDER BY type"

            if limit is not None:
                sql += f" LIMIT {int(limit)}"

            cursor.execute(sql)
            rows: List[sqlite3.Row] = cursor.fetchall()
            return rows
        except sqlite3.Error as e:
            global_logger.error(f"Erreur SQLite lors de la récupération des lignes à traiter de {self.table_name}: {e}")
            return []
        finally:
            conn.close()