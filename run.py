import argparse
import traceback  # Importé en haut pour la clarté

from app.db_handler import DbHandler
from app.github import GitHubService
from app.changelog_parser import ChangelogParser
from app.changelog_writer import ChangelogWriter
from app.changelog_processor import ChangelogProcessor
from flask_service_tools import Config, AIGatewayClient  # Assurez-vous que Config est bien initialisé/accessible
from app.logger import global_logger


# TODO: Gestion des permissions d'accès
# TODO: Vérifier que le token a les bons droits/authentique via un appel à Access Control

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Process Dolibarr changelog')
    parser.add_argument('--version', '-v', type=str, required=True,  # type=str pour correspondre à l'usage
                        help='Dolibarr version number (ex: 19 ou 19.0)')
    parser.add_argument('--token', '-t', type=str, required=True,
                        help='GitHub access token')
    args = parser.parse_args()
    return args.version, args.token


def initialize_services(github_token: str, dolibarr_version: str):
    """Initialize and return all necessary services and handlers."""
    print("🔧 Initialisation des services...")
    github_service = GitHubService(github_token)
    changelog_parser = ChangelogParser()
    changelog_writer = ChangelogWriter()
    db_handler = DbHandler(dolibarr_version)
    # Assurez-vous que Config.AI_GATEWAY_URL est correctement configuré
    ai_client = AIGatewayClient(Config.AI_GATEWAY_URL, global_logger)
    processor = ChangelogProcessor(db_handler, github_service, ai_client, changelog_parser)

    services = {
        "github_service": github_service,
        "parser": changelog_parser,
        "writer": changelog_writer,
        "db_handler": db_handler,
        "processor": processor,
    }
    print("  ✅ Services initialisés.")
    return services


def fetch_and_prepare_changelog_section(
        github_service: GitHubService,
        parser: ChangelogParser,
        writer: ChangelogWriter,
        version: str
) -> list[str] | None:
    """Fetch, extract, and save the target changelog section."""
    print(f"\n📥 Étape 1: Téléchargement du ChangeLog Dolibarr...")
    changelog_content = github_service.fetch_raw_file_content(
        owner='Dolibarr',
        repo='dolibarr',
        branch='develop',
        filepath='ChangeLog'
    )

    if not changelog_content:
        print("  ❌ Téléchargement du fichier ChangeLog échoué.")
        return None
    print("  ✅ ChangeLog téléchargé.")

    print(f"\n🔎 Étape 2: Extraction de la section pour la v{version}...")
    section_lines = parser.extract_version_section(changelog_content, version)

    if not section_lines:
        print(f"  ℹ️ Section pour la v{version} non trouvée dans le ChangeLog ou vide.")
        return None

    print(f"  ✅ Section v{version} extraite ({len(section_lines)} lignes).")
    try:
        writer.save_lines_to_file(section_lines, version)
        print(f"  📄 Section sauvegardée localement dans 'data/changelog_v{version}.txt'.")
    except IOError as e:
        print(f"  ⚠️ Erreur lors de la sauvegarde locale de la section : {e}")
        # Décider si c'est une erreur bloquante ou non. Ici, on continue.

    return section_lines


def process_changelog_database(
        processor: ChangelogProcessor,
        db_handler: DbHandler,
        section_lines: list[str],
        writer: ChangelogWriter
):
    """Process database: create table, insert initial lines, and enrich data."""
    print(f"\n🗃️ Étape 3: Traitement de la base de données...")

    # Phase 1 BD: Préparation de la table et insertion initiale des lignes brutes.
    print("  [Phase 1 BD] Préparation table et insertion initiale...")
    db_handler.create_changelog_table()  # Assure que la table pour la version existe.

    # La méthode `determine_line_type_and_process_db` analyse `section_lines`,
    # détermine le type de chaque ligne, et l'insère en base.
    if hasattr(processor, 'determine_line_type_and_process_db'):
        processor.determine_line_type_and_process_db(section_lines)
    else:
        # Avertissement si la méthode d'insertion/parsing initiale est manquante.
        print(
            "  ⚠️ 'determine_line_type_and_process_db' non trouvée sur le processor. L'insertion initiale peut être incomplète.")
        print("     Veuillez implémenter cette logique ou une alternative pour peupler la base de données.")

    # Phase 2 BD: Enrichissement des lignes stockées en base.
    print("\n  [Phase 2 BD] Enrichissement des données via l'API GitHub et l'IA...")
    concatenated_prompts = processor.process_changelog_lines_refactored()  # Limite par défaut à 10 lignes

    if concatenated_prompts:
        try:
            writer.save_text_block(concatenated_prompts, 'data/prompts_summary.txt')  # Nom de fichier plus descriptif
            print("  📄 Prompts et résumés sauvegardés dans 'data/prompts_summary.txt'.")
        except IOError as e:
            print(f"  ⚠️ Erreur lors de la sauvegarde des prompts : {e}")
    else:
        print("  ℹ️ Aucun prompt n'a été généré ou retourné par le processeur.")

    print("\n✅ Traitement de la base de données terminé.")


def main():
    """Main function to orchestrate changelog processing."""
    current_dolibarr_version, current_github_token = parse_arguments()

    print(f"🚀 Démarrage du traitement du changelog pour Dolibarr v{current_dolibarr_version}")

    # --- Initialisation des Services ---
    services = initialize_services(current_github_token, current_dolibarr_version)

    github_service = services["github_service"]
    parser = services["parser"]
    writer = services["writer"]
    db_handler = services["db_handler"]
    processor = services["processor"]

    # --- Étape 1 & 2: Téléchargement et Extraction de la Section ---
    section_lines = fetch_and_prepare_changelog_section(
        github_service, parser, writer, current_dolibarr_version
    )

    if not section_lines:
        print("ℹ️ Arrêt du traitement car la section du changelog n'a pas pu être obtenue.")
        return

    # --- Étape 3: Traitement et Intégration Base de Données ---
    try:
        process_changelog_database(processor, db_handler, section_lines, writer)
    except Exception as e:
        print(f"❌ Erreur majeure durant le traitement global : {e}")
        traceback.print_exc()
        print("ℹ️ Le traitement a été interrompu en raison d'une erreur.")
    else:
        print("\n🎉 Traitement du changelog terminé avec succès!")


if __name__ == "__main__":
    main()
