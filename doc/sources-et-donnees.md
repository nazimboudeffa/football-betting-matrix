# Sources de données et cartographie des informations

Ce document décrit **ce dont Betting Matrix a besoin**, **d’où vient chaque information** et **ce qui est calculé localement**. Il complète le README, qui résume les fonctionnalités et la configuration.

L’application utilise uniquement des sources gratuites et publiques : football-data.co.uk, OpenFootball, OpenLigaDB et TheSportsDB. Aucune base de données n’est utilisée : les réponses sont conservées en cache mémoire pendant la session et les réglages sont enregistrés dans `data/settings.json`.

## 1. Sources externes utilisées

| Source | Données fournies | Utilisation dans l’application |
| --- | --- | --- |
| **football-data.co.uk** (CSV) | Résultats (`FTHG`, `FTAG`), score à la mi-temps (`HTHG`, `HTAG`), arbitre (`Referee`) | Modèles, classement, profil arbitre, affichage du score |
| | **Cotes réelles** : 1X2 ouverture (`B365H/D/A`), clôture (`B365CH/D/A`), Pinnacle (`PCH/D/A`), consensus (`AvgCH/D/A`), meilleur prix (`MaxCH/D/A`) | Panneau « Cotes marché », résumé `market`, comparaison avec les « Cotes modèle » |
| | Over/Under 2.5 : ouverture, clôture, Pinnacle, meilleur prix | Panneau « Cotes marché », `analysis.market_summary` |
| | Handicap asiatique : ligne et cotes (`AHCh`/`AHh`, `B365CAHH`/`B365CAHA`, `B365AHH`/`B365AHA`) | `market.asian` |
| | **xG** (`HxG`, `AxG`) — disponibles uniquement depuis la saison 2026-27 | Données du match, contexte envoyé à l’IA |
| | Statistiques : tirs, tirs cadrés, corners, fautes, cartons jaunes et rouges | Données du match, profil arbitre, contexte IA |
| **OpenFootball** (`football.json`) | Calendriers JSON : date, équipes, journée et score pour La Liga, Premier League, Bundesliga, Serie A et Ligue 1 | Matchs à venir, chargement de la saison, fusion des résultats |
| **OpenLigaDB** | Calendrier et résultats de Bundesliga, logos d’équipes (`teamIconUrl`) | Matchs à venir, résultats, logos |
| **TheSportsDB** (clé publique `123`) | Calendrier partiel de Ligue des Champions, résultats, badges équipes/ligue, stade et ville (`strVenue`, `strLocation`) | Matchs de Ligue des Champions, logos, stade |

Les constantes de base et les normaliseurs correspondants se trouvent dans `football_betting_matrix/sources.py` : `CSV_BASE`, `OPENFOOTBALL_BASE`, `OPENLIGA_BASE`, `TSDB_BASE`, `parse_football_data_csv`, `normalize_openfootball_match`, `normalize_openliga_match` et `normalize_tsdb_event`. Les libellés affichés dans l’interface sont définis par `SOURCE_LABELS`.

### Couverture par source

- **13 championnats CSV** : La Liga (140), Premier League (39), Bundesliga (78), Serie A (135), Ligue 1 (61), Championship (40), Eredivisie (72), Ligue 2 (62), La Liga 2 (41), Serie B (32), 2. Bundesliga (79), Jupiler Pro League (88), Primeira Liga (94).
- **Calendrier futur** : seulement les cinq ligues majeures via OpenFootball/OpenLigaDB, plus la Ligue des Champions partielle via TheSportsDB.
- **Statistiques, xG, cotes et arbitre** : uniquement dans les fichiers CSV.

## 2. Données calculées localement

Ces informations ne proviennent pas d’une API : elles sont dérivées des données ci-dessus.

| Information | Calcul | Code |
| --- | --- | --- |
| Identifiants de match et d’équipe | Hachage stable à partir de la ligue, de la saison, de la date et des noms canoniques d’équipes | `stable_fixture_id`, `stable_team_id` |
| Journée d’un match CSV | Comptage des matchs par équipe, puis libellé `Journee N` | `parse_football_data_csv` |
| Classement affiché | Table simple calculée sur les matchs **terminés** : victoires, nuls, défaites, buts pour/contre, forme | `compute_standings_from_fixtures` |
| Profil arbitre | Moyennes de cartons jaunes/rouges et de fautes sur les matchs déjà joués par le même arbitre | `service.py` : `_referee_profile` |
| Probabilités sans marge et mouvement des cotes | Cotes CSV converties en probabilités avec retrait de la marge ; référence Pinnacle, puis clôture, puis consensus ; variation ouverture → clôture | `analysis.py` : `market_summary` |
| « Cotes modèle » | Probabilités calculées par la stratégie sélectionnée, puis conversion `1 / probabilité` | `user_strategies/` |
| Contexte IA | Assemblage local du match, du modèle, des xG/statistiques, du marché, de l’arbitre, du classement et de la seule stratégie sélectionnée | `ai.py` : `build_context` |
| Réglages et cache | Saisons, ligues suivies, stratégie, URL et modèle Ollama ; réponses mises en cache en mémoire | `data/settings.json`, `.env`, `MemoryCache` |

Les stratégies présentes dans `user_strategies/` reconstruisent toutes leurs entrées à partir des **résultats de la saison précédant la date du match** :

- **Poisson Pur / Poisson Prudent** : buts marqués et encaissés par équipe, à domicile et à l’extérieur ;
- **Classement Pur / Ratio de Rangs** : classement reconstruit à partir des résultats, fréquences 1N2, Over 2.5 et BTTS de la ligue.

Ollama n’est pas une source de données : il reçoit le contexte assemblé localement et génère uniquement le texte de l’analyse, après clic sur « Analyser ».

## 3. Fusion des sources

`merge_fixtures` et `_merge_pair` (`sources.py`) fusionnent les versions d’un même match :

1. la version **terminée** est préférée à la version à venir ;
2. la version avec des **cotes** est préférée à celle sans cotes ;
3. les champs manquants sont complétés depuis l’autre source : logos, identifiants, arbitre, stade, xG, statistiques et marché ;
4. l’interface affiche une source combinée, par exemple `football-data.co.uk + OpenFootball`.

Le cache mémoire évite les téléchargements redondants pendant la session ; il conserve aussi des données périmées en cas d’indisponibilité réseau.

## 4. Limites actuelles

- Les **xG** ne sont publiés par football-data.co.uk que depuis 2026-27 : l’historique est court.
- La **Ligue des Champions** n’a pas de source gratuite complète : la clé publique TheSportsDB ne renvoie qu’une partie des matchs, donc le classement peut être partiel ou vide.
- Les championnats CSV supplémentaires ne contiennent que des matchs déjà joués : pas de calendrier futur.
- Les cotes du panneau « Cotes marché » viennent du CSV ; celles du panneau « Cotes modèle » sont estimées par la stratégie.
- Les sources gratuites peuvent être partielles, retardées ou absentes pour certaines journées.

## 5. Sources évaluées mais non intégrées

Les trois sources suivantes ont été examinées ; aucune n’est présente dans le dépôt.

| Source | Apport potentiel | Limite pour le projet |
| --- | --- | --- |
| [hudl/open-data](https://github.com/hudl/open-data) (StatsBomb Open Data) | Données d’événements détaillées, xG par tir, compositions, StatsBomb 360 ; xG historiques sur certaines saisons 2004-2024 | Pas de cotes, pas de saison courante, compétitions sélectionnées, fichiers volumineux, attribution StatsBomb obligatoire |
| [OpenFootAPI](https://openfootapi.com/) | 120 compétitions, IDs déterministes, classements domicile/extérieur, H2H, Elo, lineups, xG et outils MCP | Clé obligatoire ; fonctionnalités avancées à 14 $/mois ; « fair odds » dérivées d’un modèle, pas de cotes bookmaker réelles |
| [5DollarFootballAPI](https://5dollarfootballapi.com/) | Vraies cotes bookmakers : 1X2, handicap asiatique, goal line, corners, cartes, BTTS, ouverture/clôture/in-play ; historique des mouvements | Clé obligatoire ; plan gratuit limité aux cinq grands championnats et à Bet365 ; pas de xG ; attribution requise sur les plans gratuits pour un produit public |

Si l’une de ces sources est ajoutée, le modèle actuel conseille de :

1. la rendre optionnelle derrière une clé de configuration ;
2. conserver le CSV comme source de référence pour les cotes et comme solution de repli ;
3. fusionner les nouvelles données dans `market`, `stats` ou le contexte IA sans écraser les valeurs existantes ;
4. respecter les limites de débit avec le cache mémoire et le gestionnaire d’erreurs existants.
