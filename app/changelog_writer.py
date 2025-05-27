class ChangelogWriter:
    """
    Écrit des données de changelog dans des fichiers.
    """
    def save_lines_to_file(self, lines, version_tag, filename_template="changelog_v{}.txt"):
        """
        Sauvegarde les lignes fournies dans un fichier texte.

        Args:
            lines (list): Liste des lignes à sauvegarder.
            version_tag (str): Tag de version à utiliser dans le nom du fichier (ex: "19").
            filename_template (str, optional): Modèle pour le nom du fichier.

        Returns:
            bool: True si la sauvegarde est réussie, False sinon.
        """
        if not lines:
            print("ℹ️  Aucune ligne à sauvegarder.")
            return False

        filename = filename_template.format(version_tag)
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for line in lines:
                    f.write(line + '\n')
            print(f"✅ Changelog pour la version {version_tag} sauvegardé dans : {filename}")
            return True
        except IOError as e:
            print(f"❌ Erreur lors de la sauvegarde du fichier {filename} : {e}")
            return False

    def save_text_block(self, text_content, filename="output.txt"):
        """
        Sauvegarde un bloc de texte unique dans un fichier.

        Args:
            text_content (str): Le contenu textuel à sauvegarder.
            filename (str): Nom du fichier de destination.

        Returns:
            bool: True si la sauvegarde est réussie, False sinon.
        """
        if not text_content:
            print("ℹ️  Aucun contenu à sauvegarder.")
            return False
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(text_content)
            print(f"✅ Contenu sauvegardé dans : {filename}")
            return True
        except IOError as e:
            print(f"❌ Erreur lors de la sauvegarde du fichier {filename} : {e}")
            return False
