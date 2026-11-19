# Manuel d'utilisation — Betting Matrix

Ce manuel explique **comment utiliser Betting Matrix au quotidien** : installer et lancer l'application, naviguer dans ses cinq pages, analyser un match, choisir une stratégie, lancer une analyse IA et gérer les données.

- Version de l'application : **1.0.0**
- Prérequis : **Python 3.11+**
- Aucune clé API personnelle n'est nécessaire pour démarrer.

> Pour comprendre **d'où viennent les données**, consultez [Sources de données et cartographie des informations](sources-et-donnees.md). Pour le **contrat des stratégies**, consultez le [README des stratégies utilisateur](../user_strategies/README.md). Pour un résumé technique, voir le [README du projet](../README.md).

## Sommaire

1. [Présentation](#1-présentation)
2. [Installation et lancement](#2-installation-et-lancement)
3. [Prise en main de l'interface](#3-prise-en-main-de-linterface)
4. [Page « Tableau de bord »](#4-page-tableau-de-bord)
5. [Page « Matchs »](#5-page-matchs)
6. [Page « Analyse »](#6-page-analyse)
7. [Les stratégies de calcul des cotes](#7-les-stratégies-de-calcul-des-cotes)
8. [Page « Ligues »](#8-page-ligues)
9. [Page « Réglages »](#9-page-réglages)
10. [Parcours pas à pas](#10-parcours-pas-à-pas)
11. [Configuration avancée (fichier `.env`)](#11-configuration-avancée-fichier-env)
12. [Scripts en ligne de commande](#12-scripts-en-ligne-de-commande)
13. [Limites et dépannage](#13-limites-et-dépannage)
14. [Jeu responsable](#14-jeu-responsable)

---

## 1. Présentation

Betting Matrix est une application de bureau **PyQt6** d'analyse statistique de football en français. Elle combine :

- des **résultats et des cotes réelles** issues de sources gratuites ;
- un ou plusieurs **modèles de probabilités** fournis par des fichiers de stratégie ;
- une **comparaison** entre les cotes estimées par le modèle et les cotes observées sur le marché ;
- une **analyse facultative par IA** via une instance locale Ollama.

L'application **ne suit ni les mises ni la bankroll**, ne place aucun pari et ne donne aucun conseil de mise. Les probabilités affichées sont informatives.

### Les trois notions à connaître

| Notion | Définition |
| --- | --- |
| **Stratégie** | Un fichier Python du dossier `user_strategies/` qui calcule les probabilités du match et les convertit en cotes. C'est le « moteur » de l'analyse. |
| **Cotes modèle** | Cotes **estimées** par la stratégie sélectionnée (`1 / probabilité`, éventuellement ajusté). Affichées à gauche dans la page Analyse. |
| **Cotes marché** | Cotes **réelles** lues dans le CSV de football-data.co.uk (ouverture, clôture, Pinnacle, consensus, meilleur prix). Affichées à droite. |

### Saison de référence

Les modèles reconstruisent leurs entrées à partir des **résultats de la saison précédant la date du match**. Par défaut, deux saisons gratuites sont disponibles :

- **2026** → saison 2026-2027 ;
- **2025** → saison 2025-2026.

Le choix de la saison de référence se fait dans la page **Réglages** (voir [section 9](#9-page-réglages)).

---

## 2. Installation et lancement

### 2.1 Installation

Depuis le dossier racine du projet :

```bash
pip install -r requirements.txt
python main.py
```

Dépendances : `PyQt6` (>= 6.6, < 7) et `requests` (>= 2.31, < 3).

Aucune clé API, aucun compte et aucune base de données ne sont requis. Si le dossier `data/` n'existe pas, l'application le crée automatiquement.

### 2.2 Première ouverture

Au lancement, la fenêtre s'ouvre sur le **Tableau de bord** avec une taille de 1400 × 900 px (taille minimale : 1220 × 800). La position et la taille de la fenêtre sont mémorisées entre les sessions.

La première ouverture d'une ligue ou d'une saison peut prendre quelques secondes : l'application télécharge les fichiers CSV et calendriers, puis les garde en **cache mémoire** pour le reste de la session.

### 2.3 Fichiers conservés sur le disque

| Fichier / dossier | Rôle |
| --- | --- |
| `data/settings.json` | Réglages enregistrés : saison par défaut, ligues suivies, stratégie active, URL et modèle Ollama. |
| `.env` (optionnel) | Configuration avancée : saisons disponibles, fuseau horaire, clé publique TheSportsDB, préchargement automatique. |
| `user_strategies/` | Vos fichiers de stratégie (modèles de probabilités et cotes). |

Les réponses des sources de données ne sont **jamais écrites sur le disque** : elles vivent uniquement en mémoire et disparaissent à la fermeture de l'application.

---

## 3. Prise en main de l'interface

La fenêtre se compose de trois zones :

1. **Barre latérale gauche** (largeur fixe) : le logo, la navigation entre les cinq pages, un rappel « sources gratuites » et la version.
2. **En-tête** : le titre et le sous-titre de la page active, la date du jour, ainsi qu'un indicateur d'activité (texte + barre de progression) dès qu'un chargement est en cours.
3. **Zone centrale** : le contenu de la page active.
4. **Barre d'état (bas)** : messages d'information, nombre d'entrées en cache et type de stockage des réglages.

### Les cinq pages

| Page | Usage principal |
| --- | --- |
| **Tableau de bord** | Vue d'ensemble : matchs du jour, ligues suivies, état du cache, accès rapides. |
| **Matchs** | Chercher un match par date (direct) ou par saison (liste des matchs) et l'envoyer vers l'analyse. |
| **Analyse** | Cœur du logiciel : statistiques, cotes modèle, cotes marché, classement, forme et IA. |
| **Ligues** | Ajouter ou retirer les compétitions suivies. |
| **Réglages** | Saison par défaut, serveur Ollama, gestion du cache et préchargement. |

La navigation se fait en cliquant sur le nom de la page dans la barre latérale. Plusieurs boutons (« Tout voir », « Gérer les ligues », « Analyser », etc.) changent également de page automatiquement.

---

## 4. Page « Tableau de bord »

C'est la page d'accueil. Elle se rafraîchit automatiquement toutes les 5 secondes pour les compteurs globaux.

### 4.1 Cartes de synthèse

Quatre cartes affichent :

- **Ligues suivies** : nombre de compétitions surveillées ;
- **Saison** : saison de référence du modèle ;
- **Matchs du jour** : nombre de matchs trouvés aujourd'hui dans vos ligues ;
- **Cache session** : nombre de réponses actuellement en mémoire.

### 4.2 Carte « Matchs à venir »

- Un badge indique le nombre de matchs (`0 MATCH(S)`, `6 MATCH(S)`, etc.).
- Jusqu'à **6 matchs** sont affichés avec la compétition, la journée, l'heure, les logos, les équipes et le score si le match est terminé.
- Le bouton **Analyser** ouvre directement la page **Analyse** sur ce match.
- **Tout voir** ouvre la page **Matchs** à la date du jour.
- S'il n'y a aucun match, des boutons **Voir demain**, **Voir la liste de tous les matchs** et/ou **Réessayer** sont proposés selon le cas.

### 4.3 Autres cartes

| Carte | Contenu |
| --- | --- |
| **Sources gratuites** | Rappel des sources utilisées et bouton **Gérer les ligues**. |
| **Cache session** | Nombre de réponses, taille en Ko, état (fraîches / périmées) et taux de réussite du cache ; bouton **Gérer le cache**. |
| **Analyse responsable** | Rappel que l'outil ne gère ni bankroll ni mises ; bouton **Avertissement complet**. |

---

## 5. Page « Matchs »

Cette page possède deux onglets : **Autour d'aujourd'hui** et **Liste des matchs par saison**. Le bouton **Voir la liste de tous les matchs**, présent dans les états vides du tableau de bord, ouvre directement ce second onglet.

### 5.1 Onglet « Autour d'aujourd'hui »

Barre d'outils :

- **Date** : calendrier déroulant, format `jj/mm/aaaa`. Plage autorisée : de **730 jours avant** à **120 jours après** aujourd'hui. Toute modification relance automatiquement le chargement.
- **Liste des ligues** : filtre (`Toutes les ligues` par défaut).
- **Actualiser** : force le rechargement des données (utile si les données affichées sont périmées).
- Un libellé indique le nombre de matchs, la source utilisée (`cache`, `Sources gratuites`, etc.) et l'heure de dernière mise à jour.

Le tableau contient les colonnes : **Heure**, **Competition**, **Domicile**, **Score**, **Exterieur**, **Statut** et une colonne d'action.

- Double-cliquez sur une ligne **ou** cliquez sur le bouton **Analyser** pour ouvrir la page Analyse sur ce match.
- Survolez la compétition pour voir son pays et sa journée.
- Une bannière signale les avertissements (données partielles, cache périmé, erreur réseau).

### 5.2 Onglet « Liste des matchs par saison »

Barre d'outils :

- **Ligue** : competition suivie (obligatoire pour charger la liste des matchs) ;
- **Saison** : parmi les saisons configurées ;
- **Filtrer par équipe...** : recherche libre sur le nom de l'équipe domicile, de l'équipe extérieure ou de la journée ;
- **Actualiser** : force le téléchargement des données de la saison.

Le tableau affiche **Date**, **Journée**, **Domicile**, **Score**, **Exterieur** et le bouton **Analyser**. Les matchs sont triés du plus récent au plus ancien ; un double-clic fonctionne également.

> **Important :** les championnats CSV supplémentaires (Championship, Eredivisie, Ligue 2, La Liga 2, Serie B, 2. Bundesliga, Jupiler Pro League, Primeira Liga) ne contiennent que des matchs **déjà joués**. Ils sont donc exploitables dans la liste des matchs par saison et pour l'analyse, mais pas pour les « matchs du jour ».

---

## 6. Page « Analyse »

C'est la page principale. Elle est organisée de haut en bas comme suit.

```
[ Choisir un match : Ligue | Saison | Match | Charger la saison | Analyser avec l'IA ]
[ En-tête du match : compétition, équipes, score, stade, arbitre, statut ]
[ Données du match : xG, tirs, corners, cartons, marché, arbitre ]
[ Cotes modèle (gauche)                      | Cotes marché (droite) ]
[ Classement (gauche)                        | Forme & statistiques (droite) ]
[ Avertissement ]
```

### 6.1 Choisir un match

Deux méthodes sont possibles :

**Méthode A — depuis la page Matchs (recommandée pour un match récent)**

Cliquez sur **Analyser** dans le tableau de bord ou dans la page Matchs. La page Analyse s'ouvre avec le match déjà chargé et l'analyse calculée immédiatement.

**Méthode B — depuis la page Analyse**

1. Choisissez une **Ligue** puis une **Saison**.
2. La liste **Match** se remplit automatiquement avec les matchs de cette saison.
3. Le **dernier match joué** est sélectionné automatiquement et son score apparaît dans l'en-tête.
4. Sélectionnez un autre match si vous le souhaitez : l'analyse est recalculée à chaque changement.
5. Le bouton **Charger la saison** force le téléchargement de la saison (par exemple après une mise à jour des sources).

Si aucune ligue n'est suivie, ajoutez-en une depuis la page **Ligues**.

### 6.2 En-tête du match

L'en-tête affiche :

- le nom de la compétition, la journée, la date/heure du coup d'envoi et la source ;
- les logos et noms des deux équipes ;
- le score au format `1 - 0` (en vert) si le match est terminé, sinon `vs` ;
- le stade, la ville et l'arbitre lorsqu'ils sont connus ;
- un badge de statut (à venir, terminé, etc.).

### 6.3 Données du match

Ce panneau présente les informations descriptives du CSV, sur deux colonnes **Domicile / Exterieur** :

| Donnée | Remarque |
| --- | --- |
| xG | Publiés par football-data.co.uk **depuis la saison 2026-2027 uniquement**. Un avertissement s'affiche pour les saisons plus anciennes. |
| Score mi-temps | Lorsque la source le fournit. |
| Tirs, tirs cadrés, corners | Statistiques de match. |
| Cartons jaunes, cartons rouges | Statistiques de match. |

En dessous :

- **Marche :** cote de clôture 1/N/2, cote d'ouverture entre parenthèses, probabilité sans marge et handicap asiatique (`AH`). La référence utilisée est indiquée (Pinnacle, clôture ou consensus).
- **Arbitre :** nom, nombre de matchs et moyennes de cartons jaunes/rouges et de fautes par match, calculées sur son historique.
- Une bannière d'avertissement si les xG ne sont pas disponibles.

> Ces données sont **descriptives** : elles ne sont pas ajoutées au calcul de probabilités du cœur de l'application. Elles font en revanche partie du contexte transmis à l'IA.

### 6.4 Panneau « Cotes modèle » (gauche)

- **Strategie** : liste déroulante des stratégies détectées dans `user_strategies/`.
- **Recharger** : relit le dossier sans redémarrer l'application (pratique après avoir ajouté ou modifié un fichier de stratégie).
- Une ligne d'aide affiche la description de la stratégie active, ainsi que le nombre de stratégies ignorées en cas d'erreur.
- Un badge indique le nombre de cotes calculées.

Le tableau contient cinq colonnes :

| Colonne | Signification |
| --- | --- |
| **Marche** | Marché évalué (1, N, 2, Over 2.5, BTTS, etc., selon la stratégie). |
| **Cote calculée** | Cote estimée par la stratégie. |
| **Proba** | Probabilité estimée. |
| **Cote juste** | Cote de référence `1 / probabilité`, sans marge, lorsque la stratégie la fournit. |
| **Signal** | Commentaire libre de la stratégie (les lignes mises en évidence sont colorées). |

Une bannière rappelle que ces cotes sont **estimées par le modèle** et ne sont pas des cotes de bookmaker. Si une stratégie génère une erreur, le message est affiché ici sans bloquer l'application. Le choix de la stratégie est enregistré dans `data/settings.json`.

### 6.5 Panneau « Cotes marché » (droite)

Deux tableaux côte à côte avec les cotes **réelles** du CSV :

- **1X2** : colonnes `Source | 1 | N | 2`, avec les lignes **Ouverture**, **Clôture**, **Pinnacle**, **Consensus** et **Meilleur prix** selon les données disponibles ;
- **Over/Under** : colonnes `Source | Over 2.5 | Under 2.5`, avec les mêmes origines.

Un résumé indique la **référence**, les probabilités sans marge (1 / N / 2), la **marge** et le **mouvement Ouverture → Clôture** en pourcentage.

Si le CSV ne contient aucune cote pour ce match, un avertissement le signale.

### 6.6 Classement

Le classement de la ligue et de la saison choisies est calculé localement à partir des matchs **terminés**.

- Colonnes : `#`, **Équipe**, **Groupe**, **MJ**, **V**, **N**, **D**, **BP**, **BC**, **Diff**, **Pts**, **Forme**, **Statut**.
- Si la compétition comporte plusieurs groupes (cas de la Ligue des Champions), une liste déroulante **Groupe** apparaît avec l'option « Tous les groupes ».
- Le bouton **Actualiser** relance le chargement.
- La colonne **Forme** affiche les résultats des 5 derniers matchs ; la colonne **Statut** est colorée selon la zone (relégation, Ligue des Champions, Europa League, etc.).
- Pour la Ligue des Champions, le classement peut être partiel, voire vide, car la clé publique TheSportsDB ne fournit qu'une partie des matchs.

### 6.7 Forme & statistiques

Ce panneau compare les deux équipes sur la saison de référence, avec des colonnes **Domicile / Exterieur** :

- rangs au classement avant le match (dans les en-têtes) ;
- matchs joués, buts marqués, buts encaissés ;
- répartition domicile / extérieur ;
- forces offensive et défensive ;
- forme sur les 5 derniers matchs.

Si une équipe est absente de la saison de référence, ses forces sont neutres et un avertissement s'affiche.

### 6.8 Analyse avec l'IA (Ollama)

Le bouton **Analyser avec l'IA** (en haut de la page) est actif dès qu'un match est chargé et analysé.

#### Préparation (une seule fois)

1. Installez et lancez Ollama :

   ```bash
   ollama serve
   ollama pull mistral
   ```

2. Vérifiez l'URL du serveur dans la page **Réglages** : `http://127.0.0.1:11434` par défaut.

#### Utilisation

1. Cliquez sur **Analyser avec l'IA**. L'application joint automatiquement le classement de la ligue et de la saison du match.
2. La fenêtre s'ouvre avec trois onglets :
   - **Prompt** : texte modifiable, prérempli avec le prompt par défaut ;
   - **Donnees** : contexte en lecture seule (match, probabilités, statistiques, xG, marché, arbitre, classement et **seulement la stratégie sélectionnée**) ;
   - **Reponse** : contiendra le texte généré.
3. Dans la carte **Modele Ollama**, choisissez un modèle dans la liste déroulante. Le bouton **Actualiser les modeles** relance la détection.
4. Cliquez sur **Analyser avec l'IA**. La réponse s'affiche dans l'onglet **Reponse**.

Le dernier modèle utilisé est enregistré dans `data/settings.json`. Si Ollama n'est pas démarré ou si aucun modèle n'est installé, un message explicite s'affiche et le bouton d'analyse reste désactivé. L'IA ne modifie jamais les calculs de l'application : elle ne produit qu'un texte d'analyse envoyé après votre clic.

---

## 7. Les stratégies de calcul des cotes

Les stratégies sont des fichiers `.py` **indépendants** placés dans `user_strategies/`, en dehors du package `football_betting_matrix`. Chacun fournit son propre modèle (`analyze()`) et sa propre conversion en cotes (`evaluate()`).

Quatre stratégies sont fournies :

| Fichier | Principe |
| --- | --- |
| `poisson_pur.py` | Modèle de Poisson ; probabilités brutes converties en `1 / probabilité`, sans marge. **Stratégie par défaut**. |
| `poisson_prudent.py` | Modèle de Poisson autonome ; ne garde que les marchés à au moins 45 % de probabilité, avec une cote juste majorée de 5 %. |
| `classement_pur.py` | Sans Poisson : probabilités 1N2 déduites de l'écart de rang au classement reconstruit avant le match ; Over 2.5 et BTTS par fréquences observées, cote juste. |
| `ratio_rangs.py` | Sans Poisson : le ratio « rang adverse / somme des rangs » pondère les probabilités domicile / extérieur de la ligue, avec retour progressif à la moyenne en début de saison. |

### Changer de stratégie

Dans le panneau **Cotes modèle** de la page Analyse :

1. Choisissez une stratégie dans la liste **Strategie** ;
2. Les cotes sont recalculées immédiatement ;
3. Le choix est sauvegardé automatiquement.

Après avoir ajouté ou modifié un fichier dans `user_strategies/`, cliquez sur **Recharger** : le dossier est relu sans redémarrage.

Un fichier invalide (erreur de syntaxe, `NAME` ou `evaluate()` absent) est ignoré : l'application continue de fonctionner et indique le nombre de stratégies ignorées sous la liste.

### Créer sa propre stratégie

Copiez un des fichiers existants dans `user_strategies/`, donnez-lui un nom unique et exposez :

```python
NAME = "Ma strategie"
DESCRIPTION = "Ce que fait ma strategie"

def analyze(fixtures, home_id, away_id, home_name, away_name, before_date=None):
    """Retourne les probabilites du match (optionnel)."""
    ...

def evaluate(probabilities, context=None):
    """Retourne une liste de cotes : label, prob, odd (+ fair_odd, signal, highlight)."""
    ...
```

`evaluate()` est obligatoire, `analyze()` est facultatif. Le contrat complet et un exemple minimal sont décrits dans [`user_strategies/README.md`](../user_strategies/README.md).

---

## 8. Page « Ligues »

Cette page gère la liste des compétitions suivies, utilisée par les pages Matchs, Analyse et le tableau de bord.

### Compétitions suivies (en haut)

- Tableau : **Competition**, **Pays**, **ID**, **Source**, action.
- La mention `Gratuite • defaut` indique une des six ligues initiales.
- **Retirer** demande confirmation puis renvoie la ligue dans la liste du bas. Les matchs et classements de cette ligue ne sont plus affichés.
- **Restaurer les 6 ligues par defaut** remplace la liste actuelle par : La Liga (140), Premier League (39), Bundesliga (78), Serie A (135), Ligue 1 (61) et Ligue des Champions (2).

### Ligues disponibles (en bas)

- Tableau : **Competition**, **Pays**, **ID**, action.
- **Ajouter** place la ligue en haut de la liste suivie.
- Huit ligues CSV supplémentaires sont disponibles : Championship (40), Eredivisie (72), Ligue 2 (62), La Liga 2 (41), Serie B (32), 2. Bundesliga (79), Jupiler Pro League (88) et Primeira Liga (94).
- La liste est **exhaustive** : il n'y a pas de recherche par nom ou par ID.
- Si tout est suivi, un message l'indique.

Toute modification est immédiatement répercutée sur les autres pages et enregistrée dans `data/settings.json`.

---

## 9. Page « Réglages »

### 9.1 Préférences

| Réglage | Effet |
| --- | --- |
| **Saison de reference** | Saison utilisée par défaut pour les analyses et les classements. |
| **Serveur Ollama** | URL de l'API locale, `http://127.0.0.1:11434` par défaut. |

Cliquez sur **Enregistrer les preferences** pour appliquer. Les valeurs sont conservées dans `data/settings.json`.

### 9.2 Sources de données

Rappel des sources utilisées et de la limite connue : la Ligue des Champions ne dispose que d'un calendrier partiel via la clé publique TheSportsDB.

### 9.3 Cache session

Le cache conserve en mémoire les réponses des sources pendant la session. Durées de vie :

- **6 à 12 h** pour la saison en cours ;
- **30 jours** pour les saisons passées.

Informations affichées : nombre d'entrées, taille, taux de réussite, état (frais / périmé) et tableau détaillé (contenu, endpoint, âge, expiration, taille, état).

Actions :

- **Rafraichir les statistiques** : met à jour l'affichage ;
- **Vider le cache** (confirmation) : supprime toutes les réponses ; les prochains chargements devront télécharger à nouveau les données ;
- **Precharger les donnees** : charge à l'avance les matchs d'aujourd'hui et de demain, puis les classements et les saisons des ligues suivies. Une confirmation indique le nombre approximatif d'étapes ; une barre de progression affiche l'avancement.

> Le cache est **vidé à chaque redémarrage** de l'application. Le préchargement sert donc à accélérer la session en cours, pas à conserver des données entre deux lancements.

### 9.4 À propos

Affiche la version, un lien vers OpenFootball, l'avertissement complet, ainsi que deux boutons :

- **Ouvrir le dossier des reglages** : ouvre `data/` dans l'explorateur de fichiers ;
- **Avertissement jeu responsable** : affiche l'avertissement complet.

---

## 10. Parcours pas à pas

### Scénario A — Analyser le dernier match d'une ligue

1. Ouvrez la page **Analyse**.
2. Choisissez la **Ligue** (ex. Premier League) et la **Saison** (ex. 2026).
3. Le dernier match joué est sélectionné automatiquement ; son score apparaît dans l'en-tête.
4. Vérifiez les **Données du match** (xG, statistiques, cotes de clôture).
5. Choisissez une **Strategie** dans le panneau « Cotes modèle ».
6. Comparez les **Cotes modèle** (gauche) aux **Cotes marché** (droite).
7. Consultez le **Classement** et la **Forme & statistiques** pour le contexte.

### Scénario B — Partir d'un match à venir

1. Allez dans **Matchs** → onglet **Autour d'aujourd'hui**.
2. Choisissez la date et filtrez si besoin par ligue.
3. Cliquez sur **Analyser** sur la ligne du match.
4. La page **Analyse** s'ouvre avec ce match ; attendez le calcul du modèle.
5. Lancez l'**analyse IA** si vous le souhaitez (voir [section 6.8](#68-analyse-avec-lia-ollama)).

### Scénario C — Explorer une saison passée

1. Allez dans **Matchs** → onglet **Liste des matchs par saison**.
2. Choisissez la ligue et la saison (ex. 2025).
3. Filtrez par équipe si nécessaire.
4. Double-cliquez sur un match pour l'analyser.
5. Notez que les xG ne sont pas disponibles avant 2026-2027 ; un avertissement l'indique dans la page Analyse.

---

## 11. Configuration avancée (fichier `.env`)

Copiez `.env.example` vers `.env` si vous souhaitez personnaliser le comportement, puis redémarrez l'application. Ne remplacez pas un `.env` existant : ajoutez simplement les variables utiles. Les variables déjà présentes dans l'environnement système sont prioritaires.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `THESPORTSDB_KEY` | `123` | Clé publique de démonstration pour le calendrier partiel de Ligue des Champions. |
| `THESPORTSDB_MIN_INTERVAL_MS` | `2000` | Délai minimal entre deux appels TheSportsDB. |
| `APP_TIMEZONE` | `Europe/Paris` | Fuseau utilisé pour l'affichage des dates et heures. |
| `FREE_SEASONS` | `2026,2025` | Saisons disponibles dans l'application. |
| `APP_DEFAULT_SEASON` | `2026` | Saison par défaut (doit appartenir à `FREE_SEASONS`). |
| `AUTO_WARMUP` | `false` | Précharge les données au démarrage. |

Une ancienne variable `API_FOOTBALL`, si elle existe, est ignorée : aucun compte payant n'est pris en charge.

---

## 12. Scripts en ligne de commande

Deux scripts permettent de préparer les données hors de l'interface. Leur cache reste en mémoire pendant leur exécution.

```bash
# Importer les CSV gratuits dans le cache
python scripts/import_football_data.py
python scripts/import_football_data.py --seasons 2026,2025 --leagues 140,39,78,135,61

# Précharger les données sans ouvrir l'interface
python scripts/warmup.py
python scripts/warmup.py --seasons 2026,2025
python scripts/warmup.py --season 2025
```

Pour vérifier l'installation :

```bash
python -m compileall -q football_betting_matrix user_strategies main.py scripts tests
python -m unittest discover -s tests -v
```

---

## 13. Limites et dépannage

### Limites connues

| Limite | Explication |
| --- | --- |
| **xG courts** | football-data.co.uk ne publie les xG que depuis 2026-2027. Les saisons précédentes restent analysables avec les buts et autres statistiques. |
| **Ligue des Champions partielle** | La clé publique TheSportsDB ne renvoie qu'une partie des matchs ; le classement peut être incomplet ou vide. |
| **Ligues CSV supplémentaires** | Elles ne contiennent que des matchs joués : pas de calendrier futur, donc pas de « matchs du jour ». |
| **Données gratuites** | Certaines journées peuvent être partielles, retardées ou absentes. Les avertissements sont affichés dans l'interface sans bloquer l'application. |
| **Cotes modèle ≠ cotes marché** | Les premières sont estimées par la stratégie, les secondes viennent du CSV. Ne pas les confondre. |

### Problèmes fréquents

| Symptôme | Solution |
| --- | --- |
| « Aucune ligue suivie » | Ajoutez une compétition dans la page **Ligues**, ou cliquez sur **Restaurer les 6 ligues par defaut**. |
| « Aucun match aujourd'hui » | Essayez une autre date, le lendemain ou l'onglet **Liste des matchs par saison**. Certaines ligues n'ont pas de calendrier futur. |
| Données périmées | Cliquez sur **Actualiser** (pages Matchs / Analyse) ou **Vider le cache** (Réglages). |
| Aucune stratégie dans la liste | Vérifiez que `user_strategies/` contient au moins un fichier `.py` valide, puis cliquez sur **Recharger**. Le détail des erreurs est indiqué sous la liste. |
| Bouton IA désactivé | Lancez `ollama serve`, installez un modèle avec `ollama pull <modele>`, puis cliquez sur **Actualiser les modeles**. Vérifiez l'URL dans **Réglages**. |
| Analyse IA sans réponse | Vérifiez qu'Ollama tourne toujours, que le modèle est installé et que le prompt n'est pas vide. |
| Classement vide pour la Ligue des Champions | Limite de la source gratuite TheSportsDB : ce n'est pas un bug de l'application. |
| L'application ne démarre pas | Vérifiez la version de Python (3.11+) et que `pip install -r requirements.txt` a bien été exécuté. |

---

## 14. Jeu responsable

Betting Matrix est un **outil d'analyse statistique**. Les probabilités et cotes affichées ne constituent pas des conseils de pari ni une garantie de résultat. Les données gratuites peuvent être partielles ou retardées.

Utilisez ces analyses de façon responsable et ne misez jamais plus que ce que vous pouvez perdre.

---

### Ressources complémentaires

- [README du projet](../README.md) — fonctionnalités, installation et structure.
- [Sources de données et cartographie des informations](sources-et-donnees.md) — origine et calcul de chaque information.
- [README des stratégies utilisateur](../user_strategies/README.md) — contrat détaillé et création d'un modèle personnalisé.
