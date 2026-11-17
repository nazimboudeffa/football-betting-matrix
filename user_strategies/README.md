#Strategies de calcul des cotes utilisateur

Ce dossier est **hors du coeur du logiciel** : le package `football_betting_matrix`
ne contient que le chargeur et les cotes justes de base. Ajoutez ici vos propres
fichiers `.py` pour changer la facon dont les cotes sont calculees dans la page
**Analyse → Cotes calculees**.

Les strategies sont detectees au demarrage, ou apres un clic sur **Recharger**
dans la page Analyse. Aucun redemarrage n'est necessaire.

## Contrat d'une strategie

Un fichier `ma_strategie.py` doit exposer :

```python
NAME = "Mon approche"                    # nom affiche dans la liste deroulante
DESCRIPTION = "Ce que fait la strategie" # texte d'aide sous la liste

def evaluate(probabilities, context=None):
    """Renvoie une liste de cotes (une par marche)."""
    ...
```

Arguments :

- `probabilities` : `{"home": 0.51, "draw": 0.26, ...}` (probabilites du modele).
- `context` : dictionnaire reserve aux futures options (non utilise pour l'instant).

Chaque ligne renvoyee doit contenir au moins `label`, `prob` et `odd` (la cote
calculee, en decimal europeen). Les champs optionnels sont :

- `fair_odd` : cote juste de reference (`1 / prob`), affichee dans sa colonne ;
- `signal` : texte libre affiche dans la colonne « Signal » ;
- `highlight` : `True` pour mettre la ligne en evidence.

Les lignes invalides sont ignorees automatiquement.

Pour partir des cotes justes du modele sans les recalculer :

```python
from football_betting_matrix.strategies import base_rows

def evaluate(probabilities, context=None):
    rows = base_rows(probabilities)
    for row in rows:
        row["signal"] = "Reference"
    return rows
```

Un module invalide (erreur de syntaxe, `NAME` ou `evaluate()` manquant) est ignore :
il n'empeche pas le demarrage de l'application. Le nombre d'erreurs est indique sous
la liste des strategies.

## Exemples fournis

- `classic_edge.py` : cote juste `1 / probabilite`, sans marge (strategie par defaut).
- `strict_value.py` : marches a au moins 45 % de probabilite, cote juste + 5 % de
  marge, triees par cote decroissante.
