# PRD — **BD-1**

**Version :** 0.1 (MVP)

---

# 1. Vision

BD-1 est un compagnon de bureau qui observe l'activité de l'utilisateur afin de produire un **rapport de pointage suggéré**.

BD-1 **n'est pas une pointeuse**.

Il ne décide pas des horaires de travail et ne cherche pas à remplacer le jugement de l'utilisateur. Il collecte des faits, les interprète et génère un rapport que l'utilisateur utilisera ensuite pour remplir son outil de déclaration d'heures.

Le logiciel est conçu pour être :

* discret ;
* fiable ;
* entièrement local ;
* extrêmement simple.

---

# 2. Objectifs

À la fin de chaque journée (ou semaine), l'utilisateur doit pouvoir répondre facilement à la question :

> **"Quels horaires ai-je probablement effectués ?"**

sans avoir à se souvenir de toutes ses heures.

---

# 3. Principes de conception

## 3.1 Les faits sont la source de vérité

BD-1 n'enregistre que des observations certaines.

Exemples :

* démarrage du PC ;
* arrêt du PC ;
* première activité utilisateur ;
* reprise après une longue inactivité ;
* début d'une période d'inactivité.

---

## 3.2 Les suggestions sont jetables

Les horaires proposés sont calculés à partir des observations.

Ils peuvent être recalculés à tout moment.

Ils ne constituent jamais la vérité.

---

## 3.3 L'utilisateur garde le contrôle

BD-1 ne demande jamais :

* "Valider cette pause ?"
* "Confirmer votre arrivée ?"

Le logiciel ne bloque jamais l'utilisateur.

Le rapport est une aide, pas un workflow.

---

# 4. Cas d'usage

Chaque matin :

* le PC démarre ;
* BD-1 démarre automatiquement.

Pendant la journée :

* BD-1 observe l'activité ;
* l'utilisateur peut ignorer totalement le logiciel.

Le vendredi :

* l'utilisateur ouvre BD-1 ;
* consulte le rapport ;
* remplit son outil RH.

---

# 5. Fonctionnalités

## 5.1 Démarrage automatique

Au démarrage de la session utilisateur :

* lancement automatique de BD-1 ;
* démarrage silencieux.

---

## 5.2 Présence dans le tray

BD-1 fonctionne principalement depuis le tray.

Aucune fenêtre n'est ouverte automatiquement.

---

## 5.3 Icône dynamique

L'icône représente l'état courant.

### Gris

Application inactive.

---

### Vert clair

PC démarré.

Aucune activité détectée.

---

### Vert foncé

Activité détectée.

Une journée semble avoir commencé.

---

### Orange

Inactivité prolongée.

Pause probable.

---

### Rouge

Fin de journée probable.

---

# 6. Menu du tray

Le menu contient :

```text
BD-1

État :
Travail probable

----------------

🟢 Je travaille

🍽 Je suis en pause

📅 Rapport du jour

📆 Rapport de la semaine

⚙ Préférences

Quitter
```

Les boutons **Je travaille** et **Je suis en pause** permettent à l'utilisateur d'ajouter un événement explicite. Ils n'interrompent jamais le fonctionnement automatique ; ils servent uniquement de signal fort pour améliorer les suggestions.

---

# 7. Observations

Les observations constituent le journal brut.

Chaque observation possède :

* identifiant
* date/heure
* type
* métadonnées optionnelles

## Types d'observations

### Système

* BOOT
* SHUTDOWN

### Activité

* FIRST_ACTIVITY
* IDLE_STARTED
* ACTIVITY_RESUMED

### Utilisateur

* USER_WORKING
* USER_BREAK

---

# 8. Machine à états

États internes :

```text
OFFLINE

↓

PC_ON

↓

ACTIVE

↓

IDLE

↓

ACTIVE

↓

OFFLINE
```

Cette machine à états sert uniquement à piloter le comportement de BD-1 et l'icône du tray. Les transitions alimentent les observations mais ne produisent pas directement des horaires.

---

# 9. Détection d'activité

BD-1 surveille :

* souris ;
* clavier.

Il maintient en mémoire :

* `lastActivity`.

Cette valeur est mise à jour continuellement.

Elle n'est jamais enregistrée telle quelle en base.

---

# 10. Détection des blocs

Lorsqu'une période d'inactivité dépasse un seuil configurable (16 minutes par défaut), BD-1 crée un **bloc d'inactivité observé**.

Exemple :

```text
12:08
↓

aucune activité

↓

13:37

activité
```

Ce bloc est utilisé par le moteur d'analyse.

Il ne représente pas automatiquement une pause.

---

# 11. Moteur d'analyse

Le moteur transforme les observations en une proposition de journée.

Exemple :

```text
Arrivée probable :
08:31

Travail :
08:31 → 12:08

Pause probable :
12:08 → 13:37

Travail :
13:37 → 18:04

Temps estimé :
8 h 04
```

Le moteur est déterministe : à partir d'un même jeu d'observations et des mêmes paramètres, il produit toujours le même rapport.

---

# 12. Rapport quotidien

Le rapport affiche :

* chronologie des événements observés ;
* interprétation proposée ;
* temps travaillé estimé ;
* temps de pause estimé.

Aucune action de validation ou de correction n'est proposée dans la V1.

L'utilisateur utilise ce rapport comme aide pour renseigner son système RH.

---

# 13. Rapport hebdomadaire

Le rapport hebdomadaire agrège les journées :

* heures estimées par jour ;
* total hebdomadaire ;
* éventuelles anomalies (par exemple, journée sans activité détectée ou arrêt brutal du PC).

---

# 14. Stockage

## Base de données

SQLite.

Objectifs :

* robustesse en cas d'arrêt brutal ;
* simplicité de déploiement ;
* aucune dépendance serveur.

La base est stockée dans le répertoire de données de l'utilisateur (via `platformdirs`).

---

# 15. Configuration

Fichier `settings.json`.

Contient notamment :

* seuil d'inactivité ;
* lancement automatique ;
* affichage des notifications ;
* thème de l'icône (éventuellement).

---

# 16. Notifications

BD-1 peut afficher des notifications non bloquantes, par exemple :

* démarrage réussi ;
* rapport hebdomadaire disponible.

La V1 n'affiche pas de notifications demandant une action immédiate.

---

# 17. Contraintes non fonctionnelles

* Fonctionnement hors ligne.
* Consommation mémoire faible (< 50 Mo visée).
* Démarrage rapide (< 2 s visé).
* Aucune télémétrie.
* Aucune donnée envoyée sur le réseau.
* Base de données locale uniquement.

---

# 18. Technologies pressenties

* **Langage :** Python 3
* **Icône tray :** `pystray`
* **Détection clavier/souris :** `pynput`
* **Icônes :** `Pillow`
* **Base de données :** SQLite (`sqlite3` de la bibliothèque standard)
* **Répertoires utilisateur :** `platformdirs`
* **Packaging :** `PyInstaller`

---

# 19. Hors périmètre (V1)

* Édition des horaires proposés.
* Validation des suggestions.
* Synchronisation cloud.

---

# 20. Évolutions envisagées

* Détection du verrouillage/déverrouillage de session.
* Détection de la mise en veille et de la reprise.
* Paramétrage avancé des règles de détection.
* Calendrier interactif avec édition des suggestions.
* Export Excel et PDF.
* Intégration optionnelle avec des outils de déclaration d'heures.
* Tableau de bord statistique (heures moyennes, amplitude des journées, répartition hebdomadaire).

## Remarques de conception

Je ferais toutefois deux ajustements dès la V1 :

1. **Renommer les événements manuels** : au lieu de *"Je travaille"* et *"Je suis en pause"*, les appeler **"Marquer : début de travail"** et **"Marquer : début de pause"** (ou équivalent). Cela indique clairement qu'ils ajoutent une observation forte, sans changer le fonctionnement automatique.

2. **Conserver uniquement les observations en base** : les rapports quotidiens et hebdomadaires devraient être recalculés à l'ouverture à partir des observations. Cela garde le modèle simple, robuste et permet d'améliorer l'algorithme ultérieurement sans migration des données.
