import re


class ChangelogParser:
    """
    Analyse le contenu d'un changelog pour en extraire des sections spécifiques.
    """

    def extract_version_section(self, changelog_content, version_prefix_input):
        """
        Extrait une section spécifique du changelog basée sur un préfixe/numéro de version.
        Le format attendu est: "***** ChangeLog for <version> compared to ... *****"

        Args:
            changelog_content (str): Contenu complet du changelog.
            version_prefix_input (str): Version à rechercher (ex: "22.0.0", "22.0", "22").

        Returns:
            list: Une liste de lignes pour la section trouvée, ou une liste vide si non trouvée.
        """
        section_lines = []
        in_section = False

        # Pattern pour trouver la ligne d'en-tête de la section pour la version souhaitée.
        # Ex: si version_prefix_input="22.0.0", cherche "***** ChangeLog for 22.0.0 compared to ... *****"
        # Ex: si version_prefix_input="22", cherche "***** ChangeLog for 22 (ou 22.x.y) compared to ... *****"
        # On échappe version_prefix_input car il peut contenir des points.
        # (?:[.\d]*) permet de matcher des suffixes comme .0 or .0.0 si l'utilisateur entre seulement "22"
        section_header_pattern_str = (
            f"^\\*\\*\\*\\*\\* ChangeLog for {re.escape(version_prefix_input)}.0.0(?:[.\\d]*)?"
            f" compared to .* \\*\\*\\*\\*\\*$"
        )
        section_header_pattern = re.compile(section_header_pattern_str)

        # Pattern pour détecter le début de N'IMPORTE QUELLE section de changelog, pour marquer la fin de la section courante.
        any_changelog_header_pattern = re.compile(r"^\*\*\*\*\* ChangeLog for .* compared to .* \*\*\*\*\*$")

        print(f"ℹ️  Recherche de la section pour la version commençant par '{version_prefix_input}'...")
        print(f"   (Pattern utilisé: {section_header_pattern_str})")

        lines = changelog_content.splitlines()
        for i, line in enumerate(lines):
            if not in_section:
                if section_header_pattern.match(line):
                    in_section = True
                    section_lines.append(line)  # Inclure la ligne d'en-tête
                    print(f"✅ Section trouvée, commençant par : {line}")
            else:
                # Si nous sommes dans une section, vérifier si la ligne actuelle est l'en-tête d'une *autre* section.
                # Important: s'assurer que ce n'est pas la même ligne qui a démarré la section (au cas où une seule ligne serait retournée)
                # Toutefois, la logique correcte est de simplement vérifier si c'est un *autre* en-tête.
                # La ligne qui a démarré la section a déjà été ajoutée.
                if any_changelog_header_pattern.match(line):
                    # C'est l'en-tête d'une section suivante, donc la section actuelle est terminée.
                    print(f"ℹ️  Fin de la section détectée à la ligne : {line}")
                    break
                section_lines.append(line)

        if not section_lines:
            print(f"⚠️ Aucune section trouvée pour la version '{version_prefix_input}' ou commençant par celle-ci.")
        return section_lines

    def extract_pr_number_from_text(self, text: str):  # Ajout de self
        """
        Extrait le premier numéro de PR (ex: #12345) d'une chaîne de caractères.
        """
        if not text: return None
        match = re.search(r"#(\d+)", text)
        return int(match.group(1)) if match else None

    # TODO Refacto https://gemini.google.com/gem/coding-partner/aa5af5f2633f3ea4
    # TODO Gestion access manager sur branche à part
    # TODO Readme pour expliquer comment ça fonctionne et comment utiliser
