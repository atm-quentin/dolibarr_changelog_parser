# app/changelog_writer.py
import os
from typing import List
from app.logger import global_logger

class ChangelogWriter:
    """
    Écrit des données de changelog dans des fichiers.
    """

    def save_lines_to_file(self, lines: List[str], version_tag: str, filename_template: str = "data/changelog_v{}.txt") -> bool:
        """
        Sauvegarde les lignes fournies dans un fichier texte.

        Args:
            lines (List[str]): Liste des lignes à sauvegarder.
            version_tag (str): Tag de version à utiliser dans le nom du fichier (ex: "19").
            filename_template (str, optional): Modèle pour le nom du fichier.

        Returns:
            bool: True si la sauvegarde est réussie, False sinon.
        """
        if not lines:
            global_logger.info("ℹ️  Aucune ligne à sauvegarder.")
            return False

        filename = filename_template.format(version_tag)
        try:
            # S'assure que le répertoire de destination existe
            os.makedirs(os.path.dirname(filename), exist_ok=True)

            with open(filename, 'w', encoding='utf-8') as f:
                for line in lines:
                    f.write(line + '\n')
            global_logger.info(f"✅ Changelog pour la version {version_tag} sauvegardé dans : {filename}")
            return True
        except IOError as e:
            global_logger.error(f"❌ Erreur lors de la sauvegarde du fichier {filename} : {e}")
            return False

    def save_text_block(self, text_content: str, filename: str = "data/output.txt") -> bool:
        """
        Sauvegarde un bloc de texte unique dans un fichier.

        Args:
            text_content (str): Le contenu textuel à sauvegarder.
            filename (str): Nom du fichier de destination.

        Returns:
            bool: True si la sauvegarde est réussie, False sinon.
        """
        if not text_content:
            global_logger.info("ℹ️  Aucun contenu à sauvegarder.")
            return False
        try:
            # S'assure que le répertoire de destination existe
            os.makedirs(os.path.dirname(filename), exist_ok=True)

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(text_content)
            global_logger.info(f"✅ Contenu sauvegardé dans : {filename}")
            return True
        except IOError as e:
            global_logger.error(f"❌ Erreur lors de la sauvegarde du fichier {filename} : {e}")
            return False