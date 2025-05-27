import re
from app.github import GitHubService
from app.db_handler import DbHandler
from flask_service_tools import Config, AIGatewayClient
from .logger import global_logger


class ChangelogParser:
    """
    Analyse le contenu d'un changelog pour en extraire des sections spécifiques.
    """

    def __init__(self):
        self.github_service = None
        self.ai_client = AIGatewayClient(Config.AI_GATEWAY_URL, global_logger)

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

    def determine_line_type_and_process_db(self, db_handler, section_lines):
        """
        Détermine le type de chaque ligne de contenu pertinente et l'insère dans la base de données.
        Les en-têtes de section, séparateurs, et l'en-tête principal du changelog sont ignorés pour l'insertion.
        """
        print(
            f"ℹ️  Préparation de l'insertion des lignes de contenu dans la table {db_handler.table_name}..."
        )
        # current_db_line_type sera 'user' ou 'dev' pour les éléments de changelog.
        # Initialisé à None pour les lignes qui pourraient apparaître avant une section définie.
        current_db_line_type = None
        lines_inserted_count = 0
        # La phrase exacte à ignorer (en minuscules pour une comparaison insensible à la casse)
        # Assurez-vous que cette phrase correspond exactement, y compris la ponctuation finale comme le ':' si présent.
        warning_preamble_line_to_skip = "the following changes may create regressions for some external modules, but were necessary to make dolibarr better:"

        for line_text in section_lines:
            stripped_line = line_text.strip()

            # 1. Ignorer les lignes complètement vides
            if not stripped_line:
                continue

            # 2. Identifier les en-têtes de section et les lignes de contrôle pour mettre à jour le contexte
            #    et sauter leur insertion.
            if stripped_line.lower() == "for users:":
                current_db_line_type = "user"
                print(f" contexte changé à : {current_db_line_type}")
                continue  # Ne pas insérer cette ligne d'en-tête
            elif stripped_line.lower() == "for developers:":
                current_db_line_type = "dev"
                print(f" contexte changé à : {current_db_line_type}")
                continue  # Ne pas insérer cette ligne d'en-tête
            elif stripped_line.lower() == "warning:":
                current_db_line_type = "dev"  # Changement: les avertissements sont maintenant de type 'dev'
                print(f" contexte changé à : {current_db_line_type} (depuis la section Warning)")
                continue  # Ne pas insérer cette ligne d'en-tête
            elif stripped_line.startswith("***** ChangeLog for") and stripped_line.endswith("*****"):
                current_db_line_type = None  # Réinitialiser le contexte après l'en-tête principal
                continue  # Ne pas insérer l'en-tête principal du changelog
            elif re.fullmatch(r"^-+$", stripped_line): # Vérifie si la ligne est constituée uniquement de tirets (au moins un)
                continue  # Ne pas insérer les lignes de séparation
            elif stripped_line.lower() == warning_preamble_line_to_skip:
                print(f"  Ligne de préambule Warning ignorée : {stripped_line[:60]}...")
                continue

            # 3. Si nous sommes arrivés ici, la ligne n'est pas vide, ni un en-tête, ni un séparateur.
            #    C'est donc une ligne de contenu à insérer.
            #    Le type à utiliser pour la base de données est la valeur actuelle de current_db_line_type.
            #    Si aucune section n'a encore été rencontrée, current_db_line_type sera None,
            #    et la ligne sera insérée avec un type NULL dans la BDD, ce qui est acceptable.

            # Insérer la ligne nettoyée (stripped_line) pour la cohérence et la contrainte UNIQUE.
            inserted_id = db_handler.insert_changelog_line(
                line_content=stripped_line,
                line_type=current_db_line_type
            )

            if inserted_id is not None:
                lines_inserted_count += 1

        print(
            f"✅ {lines_inserted_count} nouvelle(s) ligne(s) de contenu insérée(s) dans la table {db_handler.table_name}.")

    def _extract_pr_number_from_text(self, text: str):  # Ajout de self
        """
        Extrait le premier numéro de PR (ex: #12345) d'une chaîne de caractères.
        """
        if not text: return None
        match = re.search(r"#(\d+)", text)
        return int(match.group(1)) if match else None

    def _get_pr_details_by_number(self,
                                  pr_number: int):  # Ajout de self, github_service est accessible via self.github_service
        """
        Récupère les détails et le lien d'une PR via son numéro.
        Retourne (pr_details, pr_link) ou (None, None) en cas d'échec.
        """
        print(f"  PR #️⃣ Tentative de récupération des détails pour PR #{pr_number}")

        pr_details = self.github_service.get_pr_details(pr_number)
        if pr_details:
            pr_link = pr_details.get('html_url')
            if not pr_link:
                print(f"  ⚠️ PR #{pr_number}: html_url non trouvé dans les détails.")
            return pr_details, pr_link
        print(f"  ⚠️ Impossible de récupérer les détails pour la PR #{pr_number}.")
        return None, None

    def _search_pr_by_description(self, line_content: str):  # Ajout de self
        """
        Recherche une PR par description (contenu de la ligne).
        Retourne (pr_details, pr_number, pr_link) ou (None, None, None) et une raison d'échec.
        """
        print("  PR 🔍 Recherche de PR par description...")
        search_term_full = line_content.strip()

        if ":" in search_term_full:
            potential_search_term = search_term_full.split(":", 1)[1].strip()
            search_term = potential_search_term if len(potential_search_term) > 10 else search_term_full
        else:
            search_term = search_term_full

        search_term = search_term[:150]
        if len(search_term) < 10:
            reason = f"Terme de recherche trop court: '{search_term}'"
            print(f"  ⚠️ {reason}")
            return None, None, None, reason

        found_prs = self.github_service.search_prs_by_text(search_term, only_merged=True)

        if not found_prs or not isinstance(found_prs, list):
            reason = f"Aucune PR trouvée ou erreur de recherche pour '{search_term}'."
            print(f"  PR ❌ {reason}")
            return None, None, None, reason

        if len(found_prs) == 1:
            pr_data_from_search = found_prs[0]
            pr_number_from_search = pr_data_from_search.get('number')
            if not pr_number_from_search:
                reason = f"PR trouvée par recherche sans numéro: {pr_data_from_search.get('title', 'N/A')}"
                print(f"  ⚠️ {reason}")
                return None, None, None, reason

            print(
                f"  PR ✅ Une seule PR trouvée par recherche : #{pr_number_from_search} - {pr_data_from_search.get('title', 'N/A')}")

            pr_details, pr_link = self._get_pr_details_by_number(pr_number_from_search)
            if pr_details:
                return pr_details, pr_number_from_search, pr_link, None
            else:
                reason = f"Impossible de récupérer les détails pour la PR #{pr_number_from_search} trouvée par recherche."
                print(f"  ⚠️ {reason}")
                return None, None, None, reason
        else:
            reason = f"{len(found_prs)} PRs trouvées pour '{search_term}', ambiguïté."
            print(f"  PR ⚠️ {reason}")
            return None, None, None, reason

    def _attempt_pr_identification(self, line_content: str):  # Ajout de self
        """
        Tente d'identifier une PR, d'abord par numéro direct, puis par recherche.
        Retourne un dictionnaire de statut.
        """

        pr_number = self._extract_pr_number_from_text(line_content)

        if pr_number:
            pr_details, pr_link = self._get_pr_details_by_number(pr_number)
            if pr_details:
                return {'status': 'success', 'pr_details': pr_details, 'pr_number': pr_number, 'pr_link': pr_link}
            else:
                return {'status': 'failure',
                        'reason': f'Détails PR #{pr_number} (extraite directement) non récupérables'}


        pr_details, pr_number_search, pr_link_search, reason = self._search_pr_by_description(line_content)
        if pr_details:
            return {'status': 'success', 'pr_details': pr_details, 'pr_number': pr_number_search,
                    'pr_link': pr_link_search}
        else:
            return {'status': 'failure', 'reason': reason or "Aucune PR identifiable par description"}
        
        
    def _prepare_data_for_llm_and_db(self, line_content: str, pr_info: dict, pr_diff_content: str, changelog_line_type: str = 'user'):
        """
        Prépare les données pour la DB et le prompt LLM.
        Le prompt LLM est adapté en fonction du type de public ('user' ou 'dev')
        et instruit le LLM de se baser sur la ligne originale du changelog,
        les détails de la PR et le diff.

        Args:
            line_content (str): Le contenu original de la ligne du changelog.
            pr_info (dict): Dictionnaire des informations de la PR identifiée
                            (incluant 'pr_details', 'pr_number', 'pr_link').
            pr_diff_content (str): Le contenu textuel du diff de la PR.
            changelog_line_type (str, optional): Type de la ligne ('user' ou 'dev').
                                                 Détermine le style du résumé LLM. Défaut 'user'.

        Returns:
            tuple: Un tuple contenant (db_update_payload: dict, llm_prompt: str).
        """
        pr_details = pr_info['pr_details']
        pr_number = pr_info['pr_number']
        pr_link = pr_info['pr_link']

        pr_title = pr_details.get('title', '')
        pr_description = pr_details.get('body', '')

        db_update_payload = {
            'pr_desc': f"Titre PR: {pr_title}\n\nDescription PR:\n{pr_description if pr_description else 'Aucune description fournie.'}",
            'link': pr_link,
            'diff': pr_diff_content,
            'type': changelog_line_type,
            'not_supported': False,
            'not_supported_reason': None
        }

        # Définition de l'instruction pour le résumé, en incluant la line_content
        if changelog_line_type == 'dev':
            summary_instruction = (
                "En te basant sur la 'Ligne originale du changelog', la description de la PR et son diff, "
                "génère un résumé technique concis (1 à 2 phrases maximum). Ce résumé doit expliquer "
                "la nature et l'impact technique principal du changement pour un autre développeur. "
                "Si l'ensemble de ces informations n'est pas suffisant pour un résumé pertinent, indique 'Information insuffisante pour résumer'."
            )
            audience_target = "un développeur"
        else: # 'user' ou autre
            summary_instruction = (
                "En te basant sur la 'Ligne originale du changelog' et les détails techniques fournis (description PR, diff), "
                "reformule cette nouveauté ou correction en 1 à 2 phrases simples pour un utilisateur final de Dolibarr. "
                "Explique clairement ce que cela change ou apporte pour lui dans son utilisation quotidienne, en évitant le jargon technique. "
                "Indique comment accéder au fonctionnalité, comme si l'utilisateur était vraiment débutant sur l'outil. "
                "Si l'ensemble de ces informations n'est pas suffisant pour un résumé pertinent, indique 'Information insuffisante pour résumer'."
            )
            audience_target = "un utilisateur final de Dolibarr"

        llm_prompt = f"""Contexte : Tu es un assistant IA chargé de rédiger des notes de version claires et concises pour le logiciel Dolibarr, en adaptant le message à l'audience cible.
    
    Informations disponibles pour générer le résumé :
    
    1.  **Ligne originale du changelog :** "{line_content}"
    
    2.  **Informations techniques de la Pull Request (PR) #{pr_number} associée :**
        * Titre de la PR : {pr_title}
        * Description de la PR :
            {pr_description if pr_description else "Aucune description fournie."}
    
    3.  **Diff des modifications (extrait potentiellement tronqué) :**
        ```diff
    {pr_diff_content[:3500]}
        ```
        (Note: Le diff ci-dessus peut être tronqué à 3500 caractères.)
    
    Ta tâche est de générer un résumé pour {audience_target}.
    
    Instruction spécifique pour le résumé :
    {summary_instruction}
    
    Règles importantes pour le résumé :
    - Ne mentionne PAS le numéro de la PR.
    - Commence directement par le résumé.
    - Si tu estimes que l'information est insuffisante, réponds UNIQUEMENT par la phrase 'Information insuffisante pour résumer'.
    """

        print(f"  LLM 🤖 Prompt pour LLM (type: {changelog_line_type}, basé sur line_content+PR) préparé (longueur approx: {len(llm_prompt)}).")
        print("  ✨ Données prêtes pour màj BD et prompt LLM généré.")

        return db_update_payload, llm_prompt
    
    def process_changelog_lines_refactored(self, db_handler: 'DbHandler', github_service: 'GitHubService'):
        """
        Traite les lignes du changelog en enrichissant chaque entrée.
        
        Pour chaque ligne du changelog non traitée:
        1. Identifie la PR GitHub associée (par numéro ou recherche)
        2. Récupère les détails de la PR (description, diff)  
        3. Génère un résumé explicatif via IA pour utilisateur final ou développeur
        4. Met à jour la ligne dans la base de données avec les informations enrichies
        
        Args:
            db_handler (DbHandler): Gestionnaire d'accès à la base de données
            github_service (GitHubService): Service d'accès à l'API GitHub
            
        Returns:
            str: Texte concaténé des prompts et résumés générés, ou None si aucune ligne à traiter
            
        Note:
            Les lignes sont traitées par lots de 10 maximum pour éviter la surcharge API
            Les erreurs sont gérées individuellement par ligne pour permettre le traitement des autres
        """
        lines_to_process = db_handler.get_lines_to_process(limit=10) #TODO Changer la limite
        self.github_service = github_service;
        if not lines_to_process:
            print("ℹ️ Aucune ligne à traiter dans la base de données.")
            return
        
        print(f"🚀 Début du traitement de {len(lines_to_process)} lignes du changelog...")
        all_generated_prompts = []
        for line_row in lines_to_process:
            line_id = line_row['id']
            line_content = line_row['line_content']
            db_update_payload = None # Initialisation pour chaque ligne
        
            if line_content is None:
                print(f"  ⚠️ Ligne ID {line_id} a un contenu vide (None), ignorée.")
                db_update_payload = {'not_supported': True, 'not_supported_reason': 'Contenu de ligne vide (None)'}
                db_handler.update_changelog_line(line_id, db_update_payload)
                continue
        
            print(f"\n🔎 Traitement de la ligne ID {line_id}: {line_content[:100]}...")
        
            pr_identification_result = self._attempt_pr_identification(line_content)
        
            if pr_identification_result['status'] == 'success':
                pr_info = pr_identification_result
                pr_number_identified = pr_info['pr_number']
        
                print(f"   DIFF 🔄 Récupération du diff pour PR #{pr_number_identified}...")
                pr_diff_content = github_service.get_pr_diff(pr_number_identified)
        
                if pr_diff_content:
                    print(f"  DIFF ✅ Diff récupéré (longueur: {len(pr_diff_content)} caractères).")
                    db_update_payload, generated_llm_prompt = self._prepare_data_for_llm_and_db(line_content, pr_info, pr_diff_content, line_row['type'])
                    print("  LLM 🤖 Requête envoyée à l'IA...")
                    # print("-------------------------")
                    # print(generated_llm_prompt)
                    # print("-------------------------")
                    response = self.ai_client.chat_predict('chat-gpt4o-mini', messages=[{"role": "user", "content":generated_llm_prompt}])
                    # print(response)
                    print(
                        f"  LLM ✅ Réponse reçue - Modèle: {response['model']}, Tokens prompt: {response['prompt_tokens']}, Tokens complétion: {response['completion_tokens']}, Temps: {response['response_time_ms']}ms")
                    prompt_tokens = response["prompt_tokens"]
                    completion_tokens = response["completion_tokens"]
                    result = response["response"]
                    if generated_llm_prompt:  # C'est une bonne pratique de vérifier si le prompt n'est pas vide
                        all_generated_prompts.append(f"Ligne originale: {line_content}\n\nRésumé généré: {result}")
                        db_update_payload.update(
                            {'is_done': True, 'desc_and_diff_tokens': prompt_tokens + completion_tokens})
                else:
                    all_generated_prompts.append(f"Ligne originale: {line_content}\n\nPas de Diff trouvé, pas de résumé généré.")
                    reason = f'Diff non récupérable pour PR #{pr_number_identified}'
                    print(f"  DIFF ❌ {reason}.")
                    db_update_payload = {'not_supported': True, 'not_supported_reason': reason}
            else: # Échec de l'identification de la PR
                all_generated_prompts.append(
                    f"Ligne originale: {line_content}\n\nPas de PR trouvée, pas de résumé généré.")
                reason = pr_identification_result.get('reason', 'Raison inconnue d\'échec d\'identification PR')
                print(f"  PR IDENTIFICATION ❌ {reason}")
                db_update_payload = {'not_supported': True, 'not_supported_reason': reason}
        
            if db_update_payload:
                db_handler.update_changelog_line(line_id, db_update_payload)
                print(f"  💾 Ligne ID {line_id} mise à jour dans la base de données.")
            else:
                # Ce cas ne devrait pas arriver si la logique est correcte,
                # car db_update_payload devrait toujours être défini.
                print(f"  ⚠️ Aucune action de mise à jour pour la ligne ID {line_id} (inattendu).")

        if all_generated_prompts:
            prompt_separator = f"\n\n========== {line_row['type']} ==========\n\n"
            concatenated_prompts = prompt_separator.join(all_generated_prompts)

        print("\n🏁 Traitement des lignes terminé.")
        return concatenated_prompts

    #TODO Revoir la gestion des erreurs
    #TODO Refacto https://gemini.google.com/gem/coding-partner/aa5af5f2633f3ea4
    #TODO Gestion access manager sur branche à part
    #TODO Readme pour expliquer comment ça fonctionne et comment utiliser