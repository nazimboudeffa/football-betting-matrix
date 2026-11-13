# Betting Matrix

Application desktop **PyQt6** d'analyse football et de suivi de pronostics, en francais.
Elle combine un modele de Poisson, des cotes, des value bets et un historique de
pronostics — **sans gestion de bankroll ni montants en euros**.

L'application fonctionne uniquement avec des **sources gratuites sans cle API
personnelle** : football-data.co.uk, OpenFootball, OpenLigaDB et TheSportsDB.

## Fonctionnalites

- Tableau de bord : pronostics suivis, matchs a venir, sources et cache.
- Matchs du jour, navigation par date et archive des saisons.
- Analyse d'un match : probabilites 1X2, Over/Under 2.5, BTTS, scores exacts.
- Value bets : edge, EV, cote minimale et niveau de confiance.
- Pronostics purs : selection, probabilite du modele, cote au moment du pronostic,
  resultat, taux de reussite. Aucun montant, aucune mise.
- Classements calcules a partir des resultats disponibles.
- Cache SQLite persistant : l'application reste utilisable meme sans reseau.

## Installation

Prerequis : **Python 3.11+**.

```bash
pip install -r requirements.txt
python main.py
```

Aucune cle API n'est necessaire pour demarrer.

## Ligues couvertes par defaut

- **La Liga (140)** : CSV football-data.co.uk + OpenFootball.
- **Bundesliga (78)** : CSV + OpenFootball + OpenLigaDB.
- **Serie A (135)** : CSV + OpenFootball.
- **Ligue 1 (61)** : CSV + OpenFootball.
- **Ligue des Champions (2)** : TheSportsDB, calendrier partiel pour la saison
  en cours uniquement.

Les ligues sont modifiables dans la page **Ligues**. La recherche et l'ajout
sont limites a ces cinq competitions gratuites.

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
| [football-data.co.uk](https://www.football-data.co.uk/) | Resultats et cotes CSV | La Liga, Bundesliga, Serie A, Ligue 1 ; cotes 1X2, Over/Under 2.5 |
| [OpenFootball](https://github.com/openfootball/football.json) | Calendriers JSON | La Liga, Bundesliga, Serie A, Ligue 1 |
| [OpenLigaDB](https://api.openligadb.de/) | Calendrier et resultats Bundesliga | Donnees ouvertes allemandes |
| [TheSportsDB](https://www.thesportsdb.com/) | Calendrier Ligue des Champions (partiel) | Cle publique `123` fortement limitee |

### Limites connues

- La **Ligue des Champions** n'a pas de source gratuite complete. La cle
  publique TheSportsDB ne renvoie qu'une partie des matchs ; les classements
  UCL sont donc partiels, voire vides tant que des matchs ne sont pas termines.
- La cle publique TheSportsDB est partagee et peut etre temporairement limitee.
  Les erreurs sont affichees comme avertissements, sans bloquer l'application.
- Les matchs a venir des sources gratuites n'ont generalement **pas de cotes**.
  Saisissez vos cotes manuellement dans la page Analyse.
- Les donnees gratuites peuvent etre partielles, retardees ou absentes pour
  certaines journees. Le cache local permet de consulter les dernieres donnees
  telechargees.

## Scripts utiles

Importer les CSV gratuits dans le cache local :

```bash
python scripts/import_football_data.py
python scripts/import_football_data.py --seasons 2026,2025 --leagues 140,78,135,61
```

Precharger les donnees sans ouvrir l'interface :

```bash
python scripts/warmup.py
python scripts/warmup.py --seasons 2026,2025
python scripts/warmup.py --season 2025
```

Les scripts sont interruptibles : les reponses deja recues restent en cache.

## Tests

```bash
python -m compileall -q betting_matrix main.py scripts tests
python -m unittest discover -s tests -v
```

## Structure

```text
betting_matrix/
  analysis.py      Modele Poisson, cotes, value bets
  config.py        Configuration et valeurs par defaut
  db.py            SQLite : cache, reglages, pronostics
  errors.py        Exceptions des sources de donnees
  service.py       Orchestration et operations metier
  sources.py       Sources gratuites et normalisation
  ui/              Interface PyQt6
scripts/
  import_football_data.py
  warmup.py
tests/
```

## Avertissement

Betting Matrix est un outil d'analyse statistique et de suivi de pronostics.
Les probabilites affichees ne constituent pas des conseils de pari ni une
garantie de resultat. Les donnees gratuites peuvent etre partielles ou
retardees. Jouez de facon responsable et ne misez jamais plus que ce que vous
pouvez perdre.
