import requests
class GitHubService:
    """
    Gère la communication avec l'API GitHub pour récupérer des informations sur les PRs et les fichiers.
    """
    BASE_API_URL = "https://api.github.com"
    def __init__(self, github_token):
        """
        Initialise le service GitHub avec un token d'accès.

        Args:
            github_token (str): Token d'accès GitHub.
        """
        if not github_token:
            raise ValueError("Le token GitHub ne peut pas être vide.")
        self._github_token = github_token
        self.owner = 'dolibarr'
        self.repo = 'Dolibarr'
        self._headers = {
            'Authorization': f'token {self._github_token}', # Décommenté et corrigé pour utiliser 'token'
            'Accept': 'application/vnd.github.v3+json' # Acceptation standard pour JSON
        }
        self._headers_diff = {
            'Authorization': f'token {self._github_token}',
            'Accept': 'application/vnd.github.v3.diff'  # <-- Cet en-tête est crucial pour le diff
        }

    def _make_api_request(self, url: str, custom_headers=None, params=None):
        """Méthode utilitaire pour faire des requêtes API et gérer les erreurs communes."""
        headers_to_use = custom_headers if custom_headers else self._headers
        try:
            response = requests.get(url, headers=headers_to_use, params=params, timeout=20)
            response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP 4xx/5xx
            # Vérifier si la réponse est vide ou si le rate limit est atteint
            if 'X-RateLimit-Remaining' in response.headers and int(response.headers['X-RateLimit-Remaining']) == 0:
                print("⚠️ Attention : Limite de taux d'API GitHub atteinte. Réessayez plus tard.")
                return None
            if response.status_code == 204:  # No content
                return None
            return response
        except requests.exceptions.HTTPError as http_err:
            status_code = getattr(http_err.response, 'status_code', None)
            print(f"❌ Erreur HTTP lors de la requête API ({url}) : {http_err}")
            if status_code == 401:
                print("   Assurez-vous que votre token GitHub est correct et a les permissions nécessaires.")
            elif status_code == 403:
                if 'X-RateLimit-Remaining' in http_err.response.headers and int(
                        http_err.response.headers['X-RateLimit-Remaining']) == 0:
                    print("   Limite de taux d'API GitHub atteinte. Réessayez plus tard.")
                else:
                    print(
                        "   Accès refusé. Vérifiez les permissions de votre token ou les restrictions d'accès de l'API.")
            elif status_code == 404:
                print(f"   Ressource non trouvée à l'URL : {url}.")
            elif status_code >= 500:
                print("   Erreur serveur GitHub. Veuillez réessayer plus tard.")
            return None
        except requests.exceptions.RequestException as err:
            print(f"❌ Erreur de requête API ({url}) : {err}")
            return None

    def search_prs_by_text(self, search_query: str, only_merged: bool = True):
        """
        Recherche des PRs basées sur une requête textuelle (peut être une description, un titre, etc.).

        Args:
            search_query (str): Le texte à rechercher.
            only_merged (bool): Si True, ne recherche que les PRs mergées.

        Returns:
            list: Une liste de PRs correspondantes (format JSON de l'API) ou None.
                  Chaque PR dans la liste est un dictionnaire.
        """
        query = f'repo:{self.owner}/{self.repo} is:pr "{search_query}"'  # Guillemets pour chercher la phrase exacte
        if only_merged:
            query += " is:merged"

        url = f"{self.BASE_API_URL}/search/issues"
        params = {'q': query, 'sort': 'updated', 'order': 'desc'}  # Trier par dernière mise à jour

        print(f"ℹ️ Recherche de PRs avec la requête : {query}")
        response = self._make_api_request(url, params=params)

        if response:
            try:
                data = response.json()
                if 'items' in data:
                    print(f"✅ {data.get('total_count', 0)} PR(s) trouvée(s) pour la recherche : '{search_query}'")
                    return data['items']
                else:
                    print(f"⚠️ Aucune PR trouvée ou format de réponse inattendu pour : '{search_query}'")
                    return []
            except ValueError:  # Erreur de parsing JSON
                print(f"❌ Erreur de décodage JSON pour la recherche : '{search_query}'")
                return None
        return None

    def get_pr_details(self, pr_number: int):
        """
        Récupère les détails d'une Pull Request spécifique.

        Args:
            pr_number (int): Le numéro de la Pull Request.

        Returns:
            dict: Les détails de la PR (format JSON de l'API) ou None.
        """
        url = f"{self.BASE_API_URL}/repos/{self.owner}/{self.repo}/pulls/{pr_number}"
        print(f"ℹ️ Récupération des détails pour la PR #{pr_number}")
        response = self._make_api_request(url)
        return response.json() if response else None

    def get_pr_diff(self, pr_number: int):
        """
        Récupère le diff d'une Pull Request spécifique.

        Args:
            pr_number (int): Le numéro de la Pull Request.

        Returns:
            str: Le contenu du diff ou None.
        """
        url = f"{self.BASE_API_URL}/repos/{self.owner}/{self.repo}/pulls/{pr_number}"
        print(f"ℹ️ Récupération du diff pour la PR #{pr_number}")
        response = self._make_api_request(url, custom_headers=self._headers_diff)
        return response.text if response else None

    def fetch_raw_file_content(self, owner, repo, branch, filepath):
        """
        Télécharge le contenu brut d'un fichier depuis GitHub.
        
        Args:
            owner (str): Propriétaire du dépôt
            repo (str): Nom du dépôt
            branch (str): Nom de la branche
            filepath (str): Chemin du fichier
        
        Returns:
            str|None: Contenu du fichier ou None en cas d'erreur
        """
        try:
            # Validation des paramètres
            if not all([owner, repo, branch, filepath]):
                print("❌ Tous les paramètres sont requis")
                return None
            
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filepath}"
            print(f"ℹ️  Téléchargement du fichier depuis : {url}")
            
            response = requests.get(url, headers={}, timeout=10)
            response.raise_for_status()
            
            # Vérification de la taille de la réponse
            if len(response.content) > 10 * 1024 * 1024:  # 10 MB
                print("❌ Le fichier est trop volumineux")
                return None
            
            print("✅ Fichier téléchargé avec succès.")
            return response.text
            
        except requests.exceptions.HTTPError as http_err:
            status_code = getattr(http_err.response, 'status_code', None)
            print(f"❌ Erreur HTTP lors du téléchargement : {http_err}")
            
            if status_code == 401:
                print("   Assurez-vous que votre token GitHub est correct et a les permissions nécessaires.")
            elif status_code == 403:
                print("   Accès refusé. Vérifiez vos permissions.")
            elif status_code == 404:
                print(f"   Le fichier {filepath} n'a pas été trouvé sur la branche {branch} du dépôt {owner}/{repo}.")
            elif status_code >= 500:
                print("   Erreur serveur GitHub. Veuillez réessayer plus tard.")
            
        except requests.exceptions.RequestException as err:
            print(f"❌ Erreur de requête lors du téléchargement : {err}")
        
        return None