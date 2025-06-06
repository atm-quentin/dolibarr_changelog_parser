# app/changelog_parser.py
import re
from typing import List, Optional
from app.logger import global_logger

class ChangelogParser:
    """
    Analyse le contenu d'un changelog pour en extraire des sections spécifiques.
    """

    def extract_version_section(self, changelog_content: str, version_prefix_input: str) -> List[str]:
        """
        Extrait une section spécifique du changelog basée sur un préfixe/numéro de version.
        Le format attendu est: "***** ChangeLog for <version> compared to ... *****"

        Args:
            changelog_content (str): Contenu complet du changelog.
            version_prefix_input (str): Version à rechercher (ex: "22.0.0", "22.0", "22").

        Returns:
            List[str]: Une liste de lignes pour la section trouvée, ou une liste vide si non trouvée.
        """
        section_lines: List[str] = []
        in_section = False

        # Pattern pour trouver la ligne d'en-tête de la section pour la version souhaitée.
        section_header_pattern_str = (
            f"^\\*\\*\\*\\*\\* ChangeLog for {re.escape(version_prefix_input)}.0.0(?:[.\\d]*)?"
            f" compared to .* \\*\\*\\*\\*\\*$"
        )
        section_header_pattern = re.compile(section_header_pattern_str)

        # Pattern pour détecter le début de N'IMPORTE QUELLE section de changelog.
        any_changelog_header_pattern = re.compile(r"^\*\*\*\*\* ChangeLog for .* compared to .* \*\*\*\*\*$")

        global_logger.info(f"ℹ️  Recherche de la section pour la version commençant par '{version_prefix_input}'...")
        global_logger.debug(f"   (Pattern utilisé: {section_header_pattern_str})")

        lines = changelog_content.splitlines()
        for line in lines:
            if not in_section:
                if section_header_pattern.match(line):
                    in_section = True
                    section_lines.append(line)  # Inclure la ligne d'en-tête
                    global_logger.info(f"✅ Section trouvée, commençant par : {line}")
            else:
                # Si nous sommes dans une section, vérifier si la ligne actuelle est l'en-tête d'une *autre* section.
                if any_changelog_header_pattern.match(line):
                    global_logger.info(f"ℹ️  Fin de la section détectée à la ligne : {line}")
                    break
                section_lines.append(line)

        if not section_lines:
            global_logger.warning(f"⚠️ Aucune section trouvée pour la version '{version_prefix_input}' ou commençant par celle-ci.")

        return section_lines

    def extract_pr_number_from_text(self, text: str) -> Optional[int]:
        """
        Extrait le premier numéro de PR (ex: #12345) d'une chaîne de caractères.

        Args:
            text (str): La chaîne de caractères à analyser.

        Returns:
            Optional[int]: Le numéro de la PR sous forme d'entier si trouvé, sinon None.
        """
        if not text:
            return None
        match = re.search(r"#(\d+)", text)
        return int(match.group(1)) if match else None

    # TODO Refacto https://gemini.google.com/gem/coding-partner/aa5af5f2633f3ea4
    # TODO Gestion access manager sur branche à part
    # TODO Readme pour expliquer comment ça fonctionne et comment utiliser