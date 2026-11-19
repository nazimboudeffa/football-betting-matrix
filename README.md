# Betting Matrix

Application desktop **PyQt6** d'analyse football en francais.
Elle combine un modele de Poisson et des cotes calculees par strategie, **sans
suivi de pronostics ni gestion de bankroll**.

L'application fonctionne avec des **sources de donnees gratuites** :
football-data.co.uk, OpenFootball, OpenLigaDB et TheSportsDB. Aucune base de
donnees n'est utilisee : les reponses sont gardees en cache memoire et les
reglages sont enregistres dans `data/settings.json`.

Pour une prise en main complete, consultez le
[manuel d'utilisation](doc/manuel-utilisateur.md).

Le CSV football-data.co.uk est egalement utilise pour enrichir la page
**Analyse** : xG, statistiques de match, cotes d'ouverture et de cloture,
probabilites de marche sans marge et profil de l'arbitre. Ces donnees sont
descriptives : aucun calcul de probabilite n'est ajoute au coeur de
l'application.

## Fonctionnalites

- Tableau de bord : matchs a venir, ligues suivies, sources et cache session.
- Matchs du jour, navigation par date et liste des matchs par saison.
- Analyse d'un match : choix d'une strategie et affichage de ses cotes calculees.
  Changer de ligue ou de saison selectionne automatiquement le **dernier match
  joue** et affiche son score dans l'en-tete.
- Donnees du match : xG, tirs, tirs cadres, corners, cartons, score mi-temps,
  cotes d'ouverture/cloture, probabilites de marche sans marge, handicap
  asiatique et statistiques de l'arbitre.
- Cotes calculees : chaque strategie de `user_strategies/` est un fichier autonome
  qui fournit son modele de probabilites et leur conversion en cotes.
- Comparaison cote a cote dans la page **Analyse** : « Cotes modele » (cotes
  estimees par la strategie) a gauche et « Cotes marche » a droite, avec les
  tableaux 1X2 et Over/Under 2.5 (ouverture, cloture, Pinnacle, consensus et
  meilleur prix).
- Analyse IA : envoi du prompt, de toutes les donnees de l'analyse (match, xG,
  statistiques, marche, arbitre, classement) et de la **seule strategie
  selectionnee** a une instance Ollama locale, avec choix du modele.
- Classement de la ligue affiche directement dans la page **Analyse**.
- Cache en memoire des reponses des sources, sans SQLite ni fichier de cache.

## Installation

Prerequis : **Python 3.11+**.

```bash
pip install -r requirements.txt
python main.py
```

Aucune cle API n'est necessaire pour demarrer.

## Ligues couvertes par defaut

- **La Liga (140)** : CSV football-data.co.uk + OpenFootball.
- **Premier League (39)** : CSV + OpenFootball.
- **Bundesliga (78)** : CSV + OpenFootball + OpenLigaDB.
- **Serie A (135)** : CSV + OpenFootball.
- **Ligue 1 (61)** : CSV + OpenFootball.
- **Ligue des Champions (2)** : TheSportsDB, calendrier partiel pour la saison
  en cours uniquement.

### Ligues CSV supplementaires

En plus de ces six competitions, la page **Ligues** permet d'ajouter les championnats
suivants, fournis par football-data.co.uk :

- **Championship (40)**, **Eredivisie (72)**, **Ligue 2 (62)**, **La Liga 2 (41)**,
  **Serie B (32)**, **2. Bundesliga (79)**, **Jupiler Pro League (88)**,
  **Primeira Liga (94)**.

Ces ligues fournissent resultats, cotes, xG et statistiques pour les saisons
configurees. Elles ne disposent pas de calendrier futur : elles sont donc
utiles pour l'analyse et le backtest, mais pas pour les matchs a venir.

Dans la page **Ligues**, la liste du haut contient les competitions suivies ;
celle du bas affiche toutes les ligues gratuites non ajoutees. Cliquer sur
**Ajouter** place la ligue en haut de la liste suivie ; cliquer sur **Retirer**
la fait revenir en bas de la liste disponible. Aucune recherche par nom ou par
ID : la liste est exhaustive et limitee aux competitions citees ci-dessus.

## Configuration

Copiez `.env.example` vers `.env` si vous voulez personnaliser le comportement.
Ne remplacez pas un `.env` existant : ajoutez simplement les variables utiles.
Une ancienne variable `API_FOOTBALL` eventuelle est ignoree.

```env
# Cle publique de demonstration TheSportsDB (pas d'inscription)
THESPORTSDB_KEY=123

# Saisons et saison par defaut
FREE_SEASONS=2026,2025
APP_DEFAULT_SEASON=2026
```

Les saisons disponibles sont pilotees par `FREE_SEASONS`. Par defaut :
**2026** (saison 2026-2027) et **2025** (saison 2025-2026).

## Sources de donnees gratuites

| Source | Usage | Remarques |
| --- | --- | --- |
| [football-data.co.uk](https://www.football-data.co.uk/) | Resultats, cotes, xG et statistiques | 13 championnats ; cotes d'ouverture/cloture, Over/Under 2.5, handicap asiatique, tirs, corners, cartons, xG depuis 2026-27 |
| [OpenFootball](https://github.com/openfootball/football.json) | Calendriers JSON | La Liga, Premier League, Bundesliga, Serie A, Ligue 1 |
| [OpenLigaDB](https://api.openligadb.de/) | Calendrier et resultats Bundesliga | Donnees ouvertes allemandes |
| [TheSportsDB](https://www.thesportsdb.com/) | Calendrier Ligue des Champions (partiel) | Cle publique `123` fortement limitee |

### Limites connues

- La **Ligue des Champions** n'a pas de source gratuite complete. La cle
  publique TheSportsDB ne renvoie qu'une partie des matchs ; les classements
  UCL sont donc partiels, voire vides tant que des matchs ne sont pas termines.
- La cle publique TheSportsDB est partagee et peut etre temporairement limitee.
  Les erreurs sont affichees comme avertissements, sans bloquer l'application.
- Les xG ne sont publies par football-data.co.uk que depuis la **saison 2026-27** :
  l'historique est donc court. Les saisons precedentes restent analysables avec
  les buts et les autres statistiques.
- Les ligues CSV supplementaires (Championship, Eredivisie, Ligue 2, etc.)
  ne contiennent que des matchs deja joues : pas de calendrier futur, donc pas
  de matchs du jour pour ces championnats.
- Les cotes du panneau « Cotes modele » sont **estimees par le modele**
  (`1 / probabilite`, eventuellement ajuste par la strategie). Celles du panneau
  « Cotes marche » et de la section « Donnees du match » sont des cotes reelles
  issues du CSV. Il n'y a plus de saisie manuelle ni de chargement de cotes.
- Les donnees gratuites peuvent etre partielles, retardees ou absentes pour
  certaines journees. Le cache en memoire evite seulement les telechargements
  redondants pendant la session en cours.

## Scripts utiles

Importer les CSV gratuits dans le cache memoire :

```bash
python scripts/import_football_data.py
python scripts/import_football_data.py --seasons 2026,2025 --leagues 140,39,78,135,61
```

Precharger les donnees sans ouvrir l'interface :

```bash
python scripts/warmup.py
python scripts/warmup.py --seasons 2026,2025
python scripts/warmup.py --season 2025
```

Le cache des scripts est conserve en memoire pendant leur execution.

## Analyse avec l'IA (Ollama)

Dans la page **Analyse**, le bouton **Analyser avec l'IA** ouvre une fenetre avec :

- un prompt modifiable ;
- toutes les donnees de l'analyse (match, probabilites, scores, statistiques,
  metadonnees), les donnees du match (xG, statistiques, marche, arbitre) et les
  cotes calculees par la **strategie selectionnee uniquement** ;
- une liste deroulante des modeles installes, avec choix obligatoire du modele.

Le clic sur **Analyser avec l'IA** dans cette fenetre envoie le prompt et le
contexte a l'API locale d'Ollama (`/api/chat`) et affiche la reponse.

Prerequis : Ollama doit etre **lance avant l'analyse** et au moins un modele doit
etre installe :

```bash
ollama serve
ollama pull mistral
```

L'URL du serveur (`http://127.0.0.1:11434` par defaut) se regle dans la page
**Reglages** ; le dernier modele utilise est sauvegarde dans `data/settings.json`.
Si Ollama n'est pas joignable ou n'a aucun modele installe, la fenetre affiche un
message explicite et le bouton d'analyse reste desactive tant qu'aucun modele
n'est disponible dans la liste deroulante.

## Strategies de calcul des cotes

La page **Analyse** utilise une strategie selectionnable. Le coeur de l'application
ne contient aucun calcul de probabilites : il charge une strategie qui fournit
`analyze(...)` (le modele) et `evaluate(...)` (les cotes).

Quatre strategies de base sont fournies dans `user_strategies/` :

- `poisson_pur.py` : modele de Poisson, probabilites brutes converties en cotes
  `1 / probabilite`, sans marge (defaut).
- `poisson_prudent.py` : **fichier autonome** avec son propre modele de Poisson ;
  ne garde que les marches a au moins 45 % de probabilite, avec cote juste + 5 %.
- `classement_pur.py` : **fichier autonome** sans Poisson ; probabilites 1N2
  deduites de l'ecart de rang au classement reconstruit avant le match, over 2.5
  et BTTS par frequences observees, cote juste sans marge.
- `ratio_rangs.py` : **fichier autonome** sans Poisson ; le ratio des rangs
  (rang adverse / somme des rangs) pondere les probabilites domicile / exterieur
  de la ligue, avec retour progressif a la moyenne en debut de saison.

Chaque strategie est un fichier `.py` independant dans `user_strategies/`, **hors
du package `football_betting_matrix`**. Chaque module expose `NAME`, `DESCRIPTION`,
`analyze(...)` (son modele) et `evaluate(probabilities, context=None)` (ses cotes).
Aucun fichier de strategie n'importe un autre fichier de strategie.

Le bouton **Recharger** relit le dossier sans redemarrer l'application, et le choix
de la strategie est sauvegarde dans `data/settings.json`.

Le contrat complet et un exemple minimal sont decrits dans
`user_strategies/README.md`.

## Tests

```bash
python -m compileall -q football_betting_matrix user_strategies main.py scripts tests
python -m unittest discover -s tests -v
```

## Structure

```text
football_betting_matrix/
  analysis.py      Helpers generiques de cotes (parsing, marge)
  config.py        Configuration et valeurs par defaut
  store.py         Cache memoire et reglages JSON
  errors.py        Exceptions des sources de donnees
  service.py       Orchestration et operations metier
  sources.py       Sources gratuites et normalisation
  strategies.py    Chargement et validation des strategies
  ui/              Interface PyQt6
user_strategies/     Modeles et strategies utilisateur (hors du coeur)
  poisson_pur.py     Poisson sans marge (defaut)
  poisson_prudent.py Poisson avec marge +5 %
  classement_pur.py  Classement sans Poisson
  ratio_rangs.py     Ratio des rangs sans Poisson
scripts/
  import_football_data.py
  warmup.py
tests/
```

## Avertissement

Betting Matrix est un outil d'analyse statistique football.
Les probabilites affichees ne constituent pas des conseils de pari ni une
garantie de resultat. Les donnees gratuites peuvent etre partielles ou
retardees. Jouez de facon responsable et ne misez jamais plus que ce que vous
pouvez perdre.
