import argparse
import traceback
from typing import Tuple, Dict, Any, List, Optional

# Import des classes de l'application
from app.db_handler import DbHandler
from app.github import GitHubService
from app.changelog_parser import ChangelogParser
from app.changelog_writer import ChangelogWriter
from app.changelog_processor import ChangelogProcessor
from app.logger import global_logger

# Import des outils de service
from flask_service_tools import Config, AIGatewayClient


def parse_arguments() -> Tuple[str, str]:
    """Analyse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(description='Traiter le changelog de Dolibarr')
    parser.add_argument('--version', '-v', type=str, required=True,
                        help='Numéro de version de Dolibarr (ex: 19 ou 19.0)')
    parser.add_argument('--token', '-t', type=str, required=True,
                        help='Token d\'accès GitHub')
    args = parser.parse_args()
    return args.version, args.token


def initialize_services(github_token: str, dolibarr_version: str) -> Dict[str, Any]:
    """Initialise et retourne tous les services et gestionnaires nécessaires."""
    global_logger.info("🔧 Initialisation des services...")
    github_service = GitHubService(github_token)
    changelog_parser = ChangelogParser()
    changelog_writer = ChangelogWriter()
    db_handler = DbHandler(dolibarr_version)
    ai_client = AIGatewayClient(Config.AI_GATEWAY_URL, global_logger)
    processor = ChangelogProcessor(db_handler, github_service, ai_client, changelog_parser)

    services = {
        "github_service": github_service,
        "parser": changelog_parser,
        "writer": changelog_writer,
        "db_handler": db_handler,
        "processor": processor,
    }
    global_logger.info("  ✅ Services initialisés.")
    return services


def fetch_and_prepare_changelog_section(
        github_service: GitHubService,
        parser: ChangelogParser,
        writer: ChangelogWriter,
        version: str
) -> Optional[List[str]]:
    """Télécharge, extrait et sauvegarde la section cible du changelog."""
    global_logger.info(f"\n📥 Étape 1: Téléchargement du ChangeLog Dolibarr...")
    changelog_content = github_service.fetch_raw_file_content(
        owner='Dolibarr',
        repo='dolibarr',
        branch='develop',
        filepath='ChangeLog'
    )

    if not changelog_content:
        global_logger.error("  ❌ Téléchargement du fichier ChangeLog échoué.")
        return None
    global_logger.info("  ✅ ChangeLog téléchargé.")

    global_logger.info(f"\n🔎 Étape 2: Extraction de la section pour la v{version}...")
    section_lines = parser.extract_version_section(changelog_content, version)

    if not section_lines:
        global_logger.warning(f"  ℹ️ Section pour la v{version} non trouvée dans le ChangeLog ou vide.")
        return None

    global_logger.info(f"  ✅ Section v{version} extraite ({len(section_lines)} lignes).")
    try:
        writer.save_lines_to_file(section_lines, version)
        global_logger.info(f"  📄 Section sauvegardée localement dans 'data/changelog_v{version}.txt'.")
    except IOError as e:
        global_logger.error(f"  ⚠️ Erreur lors de la sauvegarde locale de la section : {e}")

    return section_lines


def process_changelog_database(
        processor: ChangelogProcessor,
        db_handler: DbHandler,
        section_lines: List[str],
        writer: ChangelogWriter
) -> None:
    """Traite la base de données : création, insertion, et enrichissement."""
    global_logger.info(f"\n🗃️ Étape 3: Traitement de la base de données...")

    global_logger.info("  [Phase 1 BD] Préparation table et insertion initiale...")
    db_handler.create_changelog_table()

    if hasattr(processor, 'determine_line_type_and_process_db'):
        processor.determine_line_type_and_process_db(section_lines)
    else:
        global_logger.warning(
            "  ⚠️ 'determine_line_type_and_process_db' non trouvée sur le processor. "
            "L'insertion initiale peut être incomplète.\n"
            "     Veuillez implémenter cette logique ou une alternative pour peupler la base de données."
        )

    global_logger.info("\n  [Phase 2 BD] Enrichissement des données via l'API GitHub et l'IA...")
    concatenated_prompts = processor.process_changelog_lines_refactored()

    if concatenated_prompts:
        try:
            writer.save_text_block(concatenated_prompts, 'data/prompts_summary.txt')
            global_logger.info("  📄 Prompts et résumés sauvegardés dans 'data/prompts_summary.txt'.")
        except IOError as e:
            global_logger.error(f"  ⚠️ Erreur lors de la sauvegarde des prompts : {e}")
    else:
        global_logger.info("  ℹ️ Aucun prompt n'a été généré ou retourné par le processeur.")

    global_logger.info("\n✅ Traitement de la base de données terminé.")


def main() -> None:
    """Fonction principale orchestrant le traitement du changelog."""
    try:
        current_dolibarr_version, current_github_token = parse_arguments()
        global_logger.info(f"🚀 Démarrage du traitement du changelog pour Dolibarr v{current_dolibarr_version}")

        services = initialize_services(current_github_token, current_dolibarr_version)

        section_lines = fetch_and_prepare_changelog_section(
            services["github_service"], services["parser"], services["writer"], current_dolibarr_version
        )

        if not section_lines:
            global_logger.warning("ℹ️ Arrêt du traitement car la section du changelog n'a pas pu être obtenue.")
            return

        process_changelog_database(
            services["processor"], services["db_handler"], section_lines, services["writer"]
        )

        global_logger.info("\n🎉 Traitement du changelog terminé avec succès!")

    except Exception as e:
        # Remplacement de .critical et .exception par .error, comme demandé.
        global_logger.error(f"❌ Erreur majeure durant le traitement global : {e}")
        global_logger.error(f"Traceback de l'erreur :\n{traceback.format_exc()}")
        global_logger.info("ℹ️ Le traitement a été interrompu en raison d'une erreur.")


if __name__ == "__main__":
    main()