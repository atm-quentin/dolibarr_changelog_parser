# app/github.py
import requests
from typing import Optional, List, Dict, Any
from app.logger import global_logger

class GitHubService:
    """
    Gère la communication avec l'API GitHub pour récupérer des informations sur les PRs et les fichiers.
    """
    BASE_API_URL = "https://api.github.com"

    def __init__(self, github_token: str) -> None:
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
            'Authorization': f'token {self._github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self._headers_diff: Dict[str, str] = {
            'Authorization': f'token {self._github_token}',
            'Accept': 'application/vnd.github.v3.diff'
        }

    def _make_api_request(self, url: str, custom_headers: Optional[Dict[str, str]] = None,
                          params: Optional[Dict[str, Any]] = None) -> Optional[requests.Response]:
        """Méthode utilitaire pour faire des requêtes API et gérer les erreurs communes."""
        headers_to_use = custom_headers if custom_headers is not None else self._headers
        try:
            response = requests.get(url, headers=headers_to_use, params=params, timeout=20)
            response.raise_for_status()
            if 'X-RateLimit-Remaining' in response.headers and int(response.headers['X-RateLimit-Remaining']) == 0:
                global_logger.warning("⚠️ Attention : Limite de taux d'API GitHub atteinte.")
                return None
            if response.status_code == 204:
                return None
            return response
        except requests.exceptions.HTTPError as http_err:
            status_code = getattr(http_err.response, 'status_code', None)
            global_logger.error(f"❌ Erreur HTTP {status_code} lors de la requête API ({url}) : {http_err}")
            return None
        except requests.exceptions.RequestException as err:
            global_logger.error(f"❌ Erreur de requête API ({url}) : {err}")
            return None

    def search_prs_by_text(self, search_query: str, only_merged: bool = True) -> Optional[List[Dict[str, Any]]]:
        """
        Recherche des PRs basées sur une requête textuelle.
        """
        query = f'repo:{self.owner}/{self.repo} is:pr "{search_query}"'
        if only_merged:
            query += " is:merged"

        url = f"{self.BASE_API_URL}/search/issues"
        params = {'q': query, 'sort': 'updated', 'order': 'desc'}

        global_logger.info(f"ℹ️ Recherche de PRs avec la requête : {query}")
        response = self._make_api_request(url, params=params)

        if response:
            try:
                data = response.json()
                if 'items' in data:
                    global_logger.info(f"✅ {data.get('total_count', 0)} PR(s) trouvée(s).")
                    return data['items']
                return []
            except ValueError:
                global_logger.error(f"❌ Erreur de décodage JSON pour la recherche : '{search_query}'")
                return None
        return None

    def get_pr_details(self, pr_number: int) -> Optional[Dict[str, Any]]:
        """
        Récupère les détails d'une Pull Request spécifique.
        """
        url = f"{self.BASE_API_URL}/repos/{self.owner}/{self.repo}/pulls/{pr_number}"
        global_logger.info(f"ℹ️ Récupération des détails pour la PR #{pr_number}")
        response = self._make_api_request(url)
        return response.json() if response else None

    def get_pr_diff(self, pr_number: int) -> Optional[str]:
        """
        Récupère le diff d'une Pull Request spécifique.
        """
        url = f"{self.BASE_API_URL}/repos/{self.owner}/{self.repo}/pulls/{pr_number}"
        global_logger.info(f"ℹ️ Récupération du diff pour la PR #{pr_number}")
        response = self._make_api_request(url, custom_headers=self._headers_diff)
        return response.text if response else None

    def fetch_raw_file_content(self, owner: str, repo: str, branch: str, filepath: str) -> Optional[str]:
        """
        Télécharge le contenu brut d'un fichier depuis GitHub.
        """
        if not all([owner, repo, branch, filepath]):
            global_logger.error("❌ Tous les paramètres sont requis pour fetch_raw_file_content.")
            return None

        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filepath}"
        global_logger.info(f"ℹ️  Téléchargement du fichier depuis : {url}")
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            global_logger.info("✅ Fichier téléchargé avec succès.")
            return response.text
        except requests.exceptions.RequestException as err:
            global_logger.error(f"❌ Erreur lors du téléchargement du fichier {filepath}: {err}")
            return None