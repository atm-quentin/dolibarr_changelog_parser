# app/changelog_processor.py
import re
from app.github import GitHubService
from app.db_handler import DbHandler
from app.changelog_parser import ChangelogParser
from app.logger import global_logger
from flask_service_tools import AIGatewayClient, Config


class ChangelogProcessor:
    """
    Orchestre l'enrichissement des données du changelog
    en utilisant GitHub et l'IA.
    """
    # Constantes pour la configuration et les messages
    LLM_MODEL_NAME = 'chat-gpt4o-mini'
    MAX_DIFF_LENGTH = 3500
    INSUFFICIENT_INFO_MSG = "Information insuffisante pour résumer."
    NO_DESCRIPTION_MSG = "Aucune description fournie."
    MSG_EMPTY_CONTENT = "Contenu de ligne vide (None)"
    DEFAULT_PR_IDENTIFICATION_FAILURE_REASON = "Raison inconnue d'échec d'identification PR"
    LOG_SEPARATOR = "\n\n========== CHANGELOG ENTRY ==========\n\n"

    USER_SUMMARY_INSTRUCTION = (
        "En te basant sur la 'Ligne originale du changelog' et les détails techniques fournis (description PR, diff), "
        "reformule cette nouveauté ou correction en quelques phrases simples et concises pour un utilisateur final de Dolibarr. "
        "Explique clairement ce que cela change ou apporte pour lui dans son utilisation quotidienne, en évitant le jargon technique. "
        "Si la nouveauté introduit une nouvelle fonctionnalité ou modifie une interaction existante, indique de manière simple comment l'utilisateur peut y accéder ou la constater (ex: 'Vous trouverez cette option dans le menu X > Y' ou 'Lors de la création d'une facture, vous remarquerez que...'). Pour les corrections de bugs qui restaurent un fonctionnement attendu, concentre-toi sur le bénéfice de la correction. "
        f"Si l'ensemble de ces informations n'est pas suffisant pour un résumé pertinent, indique '{INSUFFICIENT_INFO_MSG}'."
    )
    DEV_SUMMARY_INSTRUCTION = (
        "En te basant **principalement sur le diff et la description technique de la PR**, et en t'aidant de la 'Ligne originale du changelog', "
        "génère un résumé technique concis (1 à 2 phrases maximum). Ce résumé doit expliquer "
        "la nature du changement (ex: refactoring, ajout de hook, modification d'API, optimisation de requête) et son impact technique principal (ex: modules/classes clés affectés, conséquences sur les performances, changements de dépendances, dépréciation de fonctionnalités) pour un autre développeur. "
        f"Si l'ensemble de ces informations n'est pas suffisant pour un résumé pertinent, indique '{INSUFFICIENT_INFO_MSG}'."
    )
    LLM_CONTEXT_PROMPT_TEMPLATE = """Contexte : Tu es un assistant IA chargé de rédiger des notes de version claires et concises pour le logiciel Dolibarr, en adaptant le message à l'audience cible.

    Informations disponibles pour générer le résumé :

    1.  **Ligne originale du changelog :** "{line_content}"

    2.  **Informations techniques de la Pull Request (PR) #{pr_number} associée :**
        * Titre de la PR : {pr_title}
        * Description de la PR :
            {pr_description}

    3.  **Diff des modifications (extrait potentiellement tronqué) :**
        ```diff
    {pr_diff_content}
        ```
        (Note: Le diff ci-dessus peut être tronqué à {max_diff_length} caractères.)

    Ta tâche est de générer un résumé pour {audience_target}.

    Instruction spécifique pour le résumé :
    {summary_instruction}

    Règles importantes pour le résumé :
    - Ne mentionne PAS le numéro de la PR.
    - Commence directement par le résumé.
    - Si tu estimes que l'information est insuffisante, réponds UNIQUEMENT par la phrase '{insufficient_info_msg}'.
    """

    def __init__(self, db_handler: DbHandler, github_service: GitHubService, ai_client: AIGatewayClient,
                 parser: ChangelogParser):
        self.db_handler = db_handler
        self.github_service = github_service
        self.ai_client = ai_client
        self.parser = parser
        global_logger.info("  [Processor] Initialisé.")

    def _prepare_data_for_llm_and_db(self, line_content: str, pr_info: dict, pr_diff_content: str,
                                     changelog_line_type: str = 'user'):
        """
        Prépare les données pour la DB (partie liée à la PR) et le prompt LLM.
        """
        pr_details = pr_info.get('pr_details', {})
        pr_number = pr_info.get('pr_number')
        pr_link = pr_info.get('pr_link')

        pr_title = pr_details.get('title', '')
        pr_description = pr_details.get('body', self.NO_DESCRIPTION_MSG)
        if not pr_description:  # Assurer que ce n'est jamais None ou vide pour le template
            pr_description = self.NO_DESCRIPTION_MSG

        # Données liées à la PR pour la base de données
        llm_related_db_data = {
            'pr_desc': f"Titre PR: {pr_title}\n\nDescription PR:\n{pr_description}",
            'link': pr_link,
            'diff': pr_diff_content,
        }

        if changelog_line_type == 'dev':
            summary_instruction = self.DEV_SUMMARY_INSTRUCTION
            audience_target = "un développeur"
        else:  # 'user' ou autre
            summary_instruction = self.USER_SUMMARY_INSTRUCTION
            audience_target = "un utilisateur final de Dolibarr"

        llm_prompt = self.LLM_CONTEXT_PROMPT_TEMPLATE.format(
            line_content=line_content,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_description=pr_description,
            pr_diff_content=pr_diff_content[:self.MAX_DIFF_LENGTH],
            max_diff_length=self.MAX_DIFF_LENGTH,
            audience_target=audience_target,
            summary_instruction=summary_instruction,
            insufficient_info_msg=self.INSUFFICIENT_INFO_MSG
        )

        global_logger.info(
            f"  LLM 🤖 Prompt pour LLM (type: {changelog_line_type}, basé sur line_content+PR) préparé (longueur approx: {len(llm_prompt)}).")
        return llm_related_db_data, llm_prompt

    def _process_single_changelog_line(self, line_row: dict) -> str:
        """
        Traite une seule ligne de changelog : identification PR, récupération diff,
        génération de résumé via LLM, et mise à jour en base.
        Retourne une chaîne résumant l'opération pour l'agrégation des logs.
        """
        line_id = line_row['id']
        line_content = line_row['line_content']
        changelog_type = line_row['type']

        # Payload initial pour la mise à jour de la base de données
        db_update_payload = {
            'is_done': False,
            'not_supported': False,
            'not_supported_reason': None,
            'pr_desc': None,
            'link': None,
            'diff': None,
            'desc_and_diff_tokens': None
        }

        log_message_prefix = f"{changelog_type} Ligne ID {line_id} ('{line_content}'): \n\n"

        if line_content is None:
            global_logger.info(f"  ⚠️ {log_message_prefix} Contenu vide (None), ignorée.")
            db_update_payload.update({
                'not_supported': True,
                'not_supported_reason': self.MSG_EMPTY_CONTENT
            })
            self.db_handler.update_changelog_line(line_id, db_update_payload)
            return f"{log_message_prefix} Contenu vide, ignorée."

        global_logger.info(f"\n🔎 Traitement de la {log_message_prefix}")

        pr_identification_result = self._attempt_pr_identification(line_content)

        if pr_identification_result['status'] == 'success':
            pr_info = pr_identification_result
            pr_number_identified = pr_info['pr_number']

            global_logger.info(f"   PR #{pr_number_identified} IDENTIFIÉE ({pr_info.get('method', 'N/A')}). DIFF 🔄 Récupération...")
            pr_diff_content = self.github_service.get_pr_diff(pr_number_identified)

            if pr_diff_content:
                global_logger.info(f"  DIFF ✅ Diff récupéré (longueur: {len(pr_diff_content)} caractères).")

                llm_db_data, generated_llm_prompt = self._prepare_data_for_llm_and_db(
                    line_content, pr_info, pr_diff_content, changelog_type
                )
                db_update_payload.update(llm_db_data)

                global_logger.info("  LLM 🤖 Requête envoyée à l'IA...")
                try:
                    response = self.ai_client.chat_predict(
                        self.LLM_MODEL_NAME,
                        messages=[{"role": "user", "content": generated_llm_prompt}]
                    )
                    global_logger.info(
                        f"  LLM ✅ Réponse reçue - Modèle: {response.get('model', 'N/A')}, Tokens prompt: {response.get('prompt_tokens', 'N/A')}, Tokens complétion: {response.get('completion_tokens', 'N/A')}, Temps: {response.get('response_time_ms', 'N/A')}ms")

                    summary_result = response.get("response", "")
                    prompt_tokens = response.get("prompt_tokens", 0)
                    completion_tokens = response.get("completion_tokens", 0)

                    db_update_payload.update({
                        'is_done': True,
                        'desc_and_diff_tokens': prompt_tokens + completion_tokens
                    })
                    # Mettre 'summary' dans db_update_payload si la BDD a un champ pour ça
                    # db_update_payload['generated_summary'] = summary_result
                    log_entry = f"{log_message_prefix} Résumé généré: {summary_result}"

                except Exception as e:
                    error_msg = f"Erreur lors de l'appel à l'IA: {str(e)}"
                    global_logger.error(f"  LLM ❌ {error_msg}")
                    db_update_payload.update({
                        'not_supported': True,
                        'not_supported_reason': error_msg
                    })
                    log_entry = f"{log_message_prefix} Échec de génération de résumé ({error_msg})."
            else:
                reason = f'Diff non récupérable pour PR #{pr_number_identified}'
                global_logger.error(f"  DIFF ❌ {reason}.")
                db_update_payload.update({
                    'not_supported': True,
                    'not_supported_reason': reason,
                    'link': pr_info.get('pr_link')  # On a quand même le lien de la PR
                })
                log_entry = f"{log_message_prefix} Pas de Diff trouvé, pas de résumé généré."
        else:
            reason = pr_identification_result.get('reason', self.DEFAULT_PR_IDENTIFICATION_FAILURE_REASON)
            global_logger.error(f"  PR IDENTIFICATION ❌ {reason}")
            db_update_payload.update({
                'not_supported': True,
                'not_supported_reason': reason
            })
            log_entry = f"{log_message_prefix} Pas de PR trouvée ({reason}), pas de résumé généré."

        self.db_handler.update_changelog_line(line_id, db_update_payload)
        global_logger.info(f"  💾 Ligne ID {line_id} mise à jour dans la base de données.")
        return log_entry

    def process_changelog_lines_refactored(self,
                                           process_limit: int = 10):
        """
        Traite les lignes du changelog en enrichissant chaque entrée.
        Utilise self.db_handler et self.github_service.
        """
        lines_to_process = self.db_handler.get_lines_to_process(limit=process_limit)
        if not lines_to_process:
            global_logger.info("ℹ️ Aucune ligne à traiter dans la base de données.")
            return None  # Maintenir la compatibilité du retour

        global_logger.info(f"🚀 Début du traitement de {len(lines_to_process)} lignes du changelog...")
        processed_line_logs = []
        for line_row in lines_to_process:
            try:
                log_entry = self._process_single_changelog_line(line_row)
                if log_entry:
                    processed_line_logs.append(log_entry)

            except Exception as e:
                # Si une erreur INATTENDUE se produit pendant le traitement d'UNE SEULE ligne,
                # on "l'attrape" ici.
                line_id = line_row.get('id', 'ID_INCONNU')  # Récupérer l'ID pour un bon log

                # On enregistre l'erreur pour savoir ce qui s'est passé et sur quelle ligne.
                global_logger.error(
                    f"❌ Erreur inattendue lors du traitement de la ligne ID {line_id}. L'erreur est : {e}")

        global_logger.info("\n🏁 Traitement des lignes terminé.")
        if processed_line_logs:
            return self.LOG_SEPARATOR.join(processed_line_logs)
        return None

    def _search_pr_by_description(self, line_content: str):
        """
        Recherche une PR par description (contenu de la ligne).
        Retourne (pr_details, pr_number, pr_link, method) ou (None, None, None, None) et une raison d'échec.
        """
        global_logger.info("  PR 🔍 Recherche de PR par description...")
        search_term_full = line_content.strip()

        search_term = search_term_full.split(":", 1)[1].strip() if ":" in search_term_full and len(
            search_term_full.split(":", 1)[1].strip()) > 10 else search_term_full
        search_term = search_term[:150]  # Limiter la longueur

        if len(search_term) < 10:
            reason = f"Terme de recherche trop court: '{search_term}'"
            global_logger.error(f"  ⚠️ {reason}")
            return None, None, None, None, reason

        found_prs = self.github_service.search_prs_by_text(search_term, only_merged=True)

        if not found_prs or not isinstance(found_prs, list):
            reason = f"Aucune PR trouvée ou erreur de recherche pour '{search_term}'."
            global_logger.error(f"  PR ❌ {reason}")
            return None, None, None, None, reason

        if len(found_prs) == 1:
            pr_data_from_search = found_prs[0]
            pr_number_from_search = pr_data_from_search.get('number')
            if not pr_number_from_search:
                reason = f"PR trouvée par recherche sans numéro: {pr_data_from_search.get('title', 'N/A')}"
                global_logger.error(f"  ⚠️ {reason}")
                return None, None, None, None, reason

            global_logger.error(
                f"  PR ✅ Une seule PR trouvée par recherche : #{pr_number_from_search} - {pr_data_from_search.get('title', 'N/A')}")
            pr_details, pr_link = self.get_pr_details_by_number(pr_number_from_search)  # Utilise la méthode existante
            if pr_details:
                return pr_details, pr_number_from_search, pr_link, "search", None  # Ajout de la méthode d'identification
            else:
                reason = f"Impossible de récupérer les détails pour la PR #{pr_number_from_search} trouvée par recherche."
                global_logger.error(f"  ⚠️ {reason}")
                return None, None, None, None, reason
        else:
            reason = f"{len(found_prs)} PRs trouvées pour '{search_term}', ambiguïté."
            global_logger.error(f"  PR ⚠️ {reason}")
            return None, None, None, None, reason

    def _attempt_pr_identification(self, line_content: str):
        """
        Tente d'identifier une PR, d'abord par numéro direct, puis par recherche.
        Retourne un dictionnaire de statut avec 'method' indiquant comment la PR a été trouvée.
        """
        pr_number_from_text = self.parser.extract_pr_number_from_text(line_content)

        if pr_number_from_text:
            global_logger.info(f"  PR #️⃣ Numéro PR {pr_number_from_text} extrait du texte.")
            pr_details, pr_link = self.get_pr_details_by_number(pr_number_from_text)
            if pr_details:
                return {'status': 'success', 'pr_details': pr_details, 'pr_number': pr_number_from_text,
                        'pr_link': pr_link, 'method': 'direct_extraction'}
            else:
                # Ne pas retourner échec ici, tenter la recherche par description
                global_logger.warning(
                    f"  ⚠️ Détails PR #{pr_number_from_text} (extraite directement) non récupérables, tentative par recherche...")

        pr_details_search, pr_number_search, pr_link_search, method_search, reason_search = self._search_pr_by_description(
            line_content)
        if pr_details_search:
            return {'status': 'success', 'pr_details': pr_details_search, 'pr_number': pr_number_search,
                    'pr_link': pr_link_search, 'method': method_search or 'search'}

        # Si l'extraction directe a échoué à obtenir les détails et la recherche a aussi échoué
        final_reason = reason_search or f'Détails PR #{pr_number_from_text} (extraite directement) non récupérables et recherche infructueuse.' if pr_number_from_text else reason_search
        return {'status': 'failure', 'reason': final_reason or self.DEFAULT_PR_IDENTIFICATION_FAILURE_REASON}

    def determine_line_type_and_process_db(self, section_lines: list[str]):  # db_handler est maintenant self.db_handler
        """
        Détermine le type de chaque ligne de contenu pertinente et l'insère dans la base de données.
        Utilise self.db_handler.
        """
        global_logger.info(f"ℹ️ Préparation de l'insertion des lignes de contenu dans la table {self.db_handler.table_name}...")
        current_db_line_type = None
        lines_inserted_count = 0
        warning_preamble_line_to_skip = "the following changes may create regressions for some external modules, but were necessary to make dolibarr better:"

        # Optimisation: créer des ensembles pour les vérifications de chaînes constantes en minuscules
        user_section_triggers = {"for users:"}
        dev_section_triggers = {"for developers:", "warning:"}  # "warning:" assigne aussi le type 'dev'
        main_header_prefix = "***** changelog for "  # en minuscules pour la comparaison

        for line_text in section_lines:
            stripped_line = line_text.strip()
            stripped_line_lower = stripped_line.lower()

            if not stripped_line:
                continue

            if stripped_line_lower in user_section_triggers:
                current_db_line_type = "user"
                global_logger.info(f" Contexte changé à : {current_db_line_type}")
                continue
            elif stripped_line_lower in dev_section_triggers:
                current_db_line_type = "dev"
                global_logger.info(f" Contexte changé à : {current_db_line_type} (section: {stripped_line_lower})")
                continue
            elif stripped_line_lower.startswith(main_header_prefix) and stripped_line.endswith("*****"):
                current_db_line_type = None
                continue
            elif re.fullmatch(r"^-+$", stripped_line):
                continue
            elif stripped_line_lower == warning_preamble_line_to_skip:
                global_logger.info(f"  Ligne de préambule Warning ignorée : {stripped_line[:60]}...")
                continue

            inserted_id = self.db_handler.insert_changelog_line(
                line_content=stripped_line,  # Insérer la ligne nettoyée
                line_type=current_db_line_type
            )
            if inserted_id is not None:
                lines_inserted_count += 1

        global_logger.info(
            f"✅ {lines_inserted_count} nouvelle(s) ligne(s) de contenu insérée(s) dans la table {self.db_handler.table_name}.")

    def get_pr_details_by_number(self, pr_number: int):
        """
        Récupère les détails et le lien d'une PR via son numéro.
        """
        global_logger.info(f"  PR INFO ↔️ Tentative de récupération des détails pour PR #{pr_number}")
        pr_details = self.github_service.get_pr_details(pr_number)
        if pr_details:
            pr_link = pr_details.get('html_url')
            if not pr_link:
                global_logger.warning(f"  ⚠️ PR #{pr_number}: html_url non trouvé dans les détails.")
            # S'assurer de retourner une structure cohérente même si le lien est manquant
            return pr_details, pr_link if pr_link else f"https://github.com/Dolibarr/dolibarr/pull/{pr_number}"  # Lien par défaut
        global_logger.error(f"  ⚠️ Impossible de récupérer les détails pour la PR #{pr_number}.")
        return None, None
