#TODO Gestion des permissions d'accès
#from flask_service_tools import APIResponse, RequestValidator, DBManager, AuthManager, Config, AIGatewayClient
from app.db_handler import DbHandler
from app.github import GitHubService
from app.changelog_parser import ChangelogParser
from app.changelog_writer import ChangelogWriter

def main():
    while True:
        current_dolibarr_version = input("Veuillez entrer le numéro de version de Dolibarr (ex: 19) : ").strip()
        if current_dolibarr_version.isdigit():  # Vérifier si l'utilisateur a entré quelque chose
            break
        else:
            print("Entrée invalide. Veuillez entrer uniquement un numéro de version entier (ex: 19, 20).")

    # Demander le token GitHub interactivement
    while True:
        current_github_token = input("Veuillez entrer votre token d'accès GitHub : ").strip()
        if not current_github_token:
            print("Le token GitHub ne peut pas être vide. Veuillez réessayer.")
        else:
            break
            
#TODO Vérifier que le token a les bon droits/authentique via un appel à Access Control
    # --- Initialisation des Services et Gestionnaires ---
    print("🔧 Initialisation des services...")
    github_service = GitHubService(current_github_token)  # Service pour l'API GitHub
    parser = ChangelogParser()  # Parser pour le texte du ChangeLog
    writer = ChangelogWriter()  # Utilitaire d'écriture de fichiers (usage optionnel ici)
    db = DbHandler(current_dolibarr_version)  # Gestionnaire BD (SQLite) pour la version cible

    # --- Étape 1: Téléchargement du Fichier ChangeLog ---
    print(f"\n📥 Étape 1: Téléchargement du ChangeLog Dolibarr...")
    changelog_content = github_service.fetch_raw_file_content(
        owner='Dolibarr',
        repo='dolibarr',
        branch='develop',
        filepath='ChangeLog'
    )

    if changelog_content:
        print("  ✅ ChangeLog téléchargé.")

        # --- Étape 2: Extraction de la Section pour la Version Cible ---
        print(f"\n🔎 Étape 2: Extraction de la section pour la v{current_dolibarr_version}...")
        # `section_lines` doit être une liste de chaînes (lignes de la section).
        section_lines = parser.extract_version_section(changelog_content, current_dolibarr_version)

        if section_lines:  # Si la section est trouvée et non vide
            print(f"  ✅ Section v{current_dolibarr_version} extraite ({len(section_lines)} lignes).")

            writer.save_lines_to_file(section_lines, current_dolibarr_version)
            print(f"  📄 Section sauvegardée localement.")

            # --- Étape 3: Traitement et Intégration Base de Données ---
            print(f"\n🗃️ Étape 3: Traitement de la base de données pour la v{current_dolibarr_version}...")
            try:
                # Phase 1 BD: Préparation de la table et insertion initiale des lignes brutes.
                print("  [Phase 1 BD] Préparation table et insertion initiale...")
                db.create_changelog_table()  # Assure que la table pour la version existe.

                # La méthode `determine_line_type_and_process_db` doit analyser `section_lines`,
                # déterminer le type de chaque ligne, et l'insérer en base via `db.insert_changelog_line`.
                # Les lignes sont insérées avec `is_done=False`, `not_supported=False`.
                if hasattr(parser, 'determine_line_type_and_process_db'):
                    parser.determine_line_type_and_process_db(db, section_lines)
                else:
                    # Avertissement si la méthode d'insertion/parsing initiale est manquante.
                    print(
                        "  ⚠️ 'determine_line_type_and_process_db' non trouvée sur le parser. L'insertion initiale peut être incomplète.")
                    print("     Veuillez implémenter cette logique ou une alternative pour peupler la base de données.")

                # Phase 2 BD: Enrichissement des lignes stockées en base (infos PRs, diffs).
                print("\n  [Phase 2 BD] Enrichissement des données via l'API GitHub...")
                # La méthode `process_changelog_lines_refactored` (ou nom équivalent) :
                # 1. Lit les lignes non traitées de la BD (`db.get_lines_to_process()`).
                # 2. Contacte GitHub (via `self.github_service`) pour infos PR et diffs.
                # 3. Met à jour les lignes en BD avec les informations enrichies.
                concatenated_prompts = parser.process_changelog_lines_refactored(db_handler=db, github_service=github_service)
                writer.save_text_block(concatenated_prompts, 'prompts.txt')
                print("\n✅ Traitement de la base de données terminé.")

            except Exception as e:  # Capture les erreurs durant les opérations sur la base de données.
                print(f"❌ Erreur majeure durant le traitement de la base de données : {e}")
                import traceback

                traceback.print_exc()  # Affiche la trace complète pour faciliter le débogage.
        else:
            print(
                f"ℹ️ Section pour la v{current_dolibarr_version} non trouvée dans le ChangeLog ou vide. Arrêt du traitement.")
    else:
        print("ℹ️ Téléchargement du fichier ChangeLog échoué. Arrêt du traitement.")

if __name__ == "__main__":
    main()