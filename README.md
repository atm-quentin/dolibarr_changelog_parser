# Processeur de Changelog Dolibarr

Ce module est un script Python conçu pour télécharger, analyser, enrichir et stocker les informations du fichier `ChangeLog` du projet Dolibarr. Il utilise l'API GitHub pour récupérer les détails des Pull Requests (PR) et un service d'IA (via une AIGateway) pour générer des résumés clairs des changements. 🤖📄

## Fonctionnalités

* **Téléchargement** : Récupère le fichier `ChangeLog` brut depuis le dépôt GitHub de Dolibarr.
* **Parsing** : Extrait la section spécifique à une version donnée et analyse chaque ligne.
* **Stockage Initial** : Sauvegarde les lignes analysées dans une base de données SQLite.
* **Enrichissement** : Récupère les détails des PR via GitHub et génère un résumé via IA.
* **Stockage Final** : Met à jour la base de données et sauvegarde les résumés.
* **Conteneurisation** : Conçu pour être exécuté facilement via Docker.

---

## Prérequis

* Cloner le dépôt en local
* **Docker** et **Docker Swarm** activé. (Utiliser l'IA (Pro) pour installer ça proprement)
* Un **Token d'accès personnel GitHub (fine gained)** avec les droits nécessaires.
* Un fichier `ai-gateway-stack.yml` (https://gitlab.atm-consulting.fr/atm-consulting/ai-services-hub/swarm_stacks)  pour déployer le service AIGateway.
* Votre **clé API OpenAI** (ou du fournisseur IA utilisé par votre AIGateway).
* Un fichier `.env` (voir section Configuration).

---

## Mise en Place de l'Environnement
Cloner le dépôt
Avant de lancer le processeur de changelog, vous devez déployer l'AIGateway et configurer les secrets nécessaires.

docker swarm init --advertise-addr {one ip}

1.  **Créer le Secret Docker** :
    Créez un secret Docker pour stocker votre clé API OpenAI (ou équivalente). Remplacez `VOTRE_CLE_OPENAI` par votre clé réelle.
    ```bash
    echo "VOTRE_CLE_OPENAI" | docker secret create provider_openai_key -
    ```
    
2.  **Déployer la Stack AIGateway** :
    Déployez la stack AIGateway en utilisant votre fichier de configuration `docker-compose` ou `stack`. Cela créera les services nécessaires, y compris le réseau `aigateway_stack_ai_gateway_net`.
    ```bash
    docker stack deploy -c ai-gateway-stack.yml aigateway_stack
    ```
    Assurez-vous que la stack est bien déployée et que le réseau est disponible avant de passer à l'étape suivante.

---

## Configuration (`.env`)

Créez un fichier nommé `.env` à la racine du projet du processeur de changelog. Il doit contenir les variables d'environnement requises par le script, notamment l'URL de votre AIGateway (telle que définie dans votre stack). Par exemple :

```env
# URL de votre AIGateway
AI_GATEWAY_URL=http://aigateway_stack_ai_gateway:7000
LOG_LEVEL=DEBUG
LOG_TO_FILE=True
LOG_FILE_PATH=/var/log/app.log
LOG_MAX_FILE_SIZE=10485760
LOG_BACKUP_COUNT=5
SERVICE_NAME=dolibarr_changelog_parser
# Autres variables si nécessaire... 
```
---
## Build de l'Image Docker

Construisez l'image Docker pour le processeur de changelog (se placer à la racine):
```bash
docker build -t mon-processeur-changelog .
```
---
## Exécution via Docker Service

Lancez le traitement pour une version spécifique (par exemple, la version 22) :
```bash
docker service create \
  --name mon-processeur-changelog \
  --env-file .env \
  --network aigateway_stack_ai_gateway_net \
  --restart-condition none \
  --mount type=volume,source=processeur-changelog-data,target=/app/data \
  mon-processeur-changelog \
  python run.py --version <VERSION> --token <VOTRE_TOKEN_GITHUB>
```
Rappel :
    Remplacez <VERSION> par le numéro de version (ex: 19, 22).
    Remplacez <VOTRE_TOKEN_GITHUB> par votre token GitHub.
    Vérifiez que le nom du réseau --network correspond bien à celui créé par votre stack.
---
## Vérifier les Résultats

Les résultats (base de données, fichiers texte) sont dans le volume Docker processeur-changelog-data
Lister les volumes :
```bash
docker volume ls
```
Inspecter le volume pour trouver son emplacement sur l'hôte (Cherchez "Mountpoint") :
```bash
docker volume inspect processeur-changelog-data
```
Explorer le contenu (avec sudo si nécessaire) :
```bash
sudo ls -l <Mountpoint_Path>
```
Vous devriez voir :

    changelog_parser.sqlite3
    changelog_v<VERSION>.txt
    prompts_summary.txt
