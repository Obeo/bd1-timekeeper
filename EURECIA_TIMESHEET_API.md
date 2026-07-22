# Eurecia — feuilles de temps

Documentation de reverse engineering établie à partir des captures HAR privées
du 21 juillet 2026, des pages `Open.do` des semaines 23 et 29 de 2026 et des
essais d’écriture vérifiés depuis BD-1. Elle décrit le comportement observé sur
le tenant `<tenant>.eurecia.com`; ce n’est pas un contrat d’API officiel et les
routes privées de l’interface peuvent changer sans préavis.

## Conclusion opérationnelle

Le client léger de BD-1 sait désormais reproduire :

- le formulaire de mot de passe du SSO Eurecia dans le cas simple sans MFA ;
- la détection du module de feuilles de temps et le choix de l’interface legacy ;
- l’ouverture d’une feuille en mode édition ;
- la lecture des segments et le calcul des totaux affichés ;
- la désactivation du mode « Standard » ;
- l’ajout, la suppression et la modification de lignes horaires ;
- la sauvegarde d’une feuille puis sa relecture pour vérifier les segments.

Le client sauvegarde uniquement les feuilles dont le statut est établi comme
`Nouvelle` ou `New`. Il ne soumet pas la feuille à validation. Il conserve les
lignes synchronisées non éditables, notamment les congés et jours fériés, et
ne remplace que les lignes horaires éditables des jours ouvrés affichés par
BD-1.

La sauvegarde utilise le formulaire legacy complet renvoyé par `Open.do`. Les
actions et champs spécifiques détaillés ci-dessous sont issus des pages HTML et
des essais réels ; ils restent privés, non contractuels et susceptibles de
changer.

## Périmètre et captures

| Capture | Entrées | Méthodes vers le tenant | Ce qu’elle montre |
| --- | ---: | --- | --- |
| `authentification-obeo.eurecia.com.har` | 67 | 64 `GET` tenant, 2 `GET` analytics externes, 1 `POST` analytics externe | Bootstrap d’une session déjà authentifiée |
| `opentimesheet-obeo.eurecia.com.har` | 14 | 14 `GET` | Navigation vers la feuille courante et lecture de la synthèse |
| `edit-timesheet-shift-one-hour-monday-obeo.eurecia.com.har` | 13 | 13 `GET` | Deux lectures avant/après un scénario de décalage |
| `edit-timesheet-delete-tuesdaysegment-add-two-new-tuesday-segments-monday-obeo.eurecia.com.har` | 31 | 31 `GET` | Cinq lectures pendant un scénario de suppression/ajout |
| `open-week23-2026.html` | page HTML | `Open.do` | Lignes en mode Standard et contrôles du formulaire legacy |
| `open-week29-2026.html` | page HTML | `Open.do` | Lignes éditables et lignes synchronisées verrouillées (`Congés payés`, jour férié) |

Les identifiants de société, d’utilisateur, de service et de feuille sont
volontairement remplacés par des placeholders dans ce document.

## Base URL et authentification

La base observée est :

```text
https://<tenant>.eurecia.com/eurecia/
```

La capture d’authentification commence sur `index.html` alors que la session
est déjà ouverte. Elle contient des appels de bootstrap comme :

```text
GET /api/v3/users/me/initData
GET /api/v2/users/me/preferences
GET /api/v3/users/me/guidedFlowParams
GET /api/v3/users/me/followedCompany
```

Elle ne contient ni formulaire de connexion, ni échange OAuth/SAML, ni appel de
création de jeton. Aucun en-tête `Authorization` ou jeton CSRF explicite n’est
visible dans les HAR. Les champs de cookies sont également absents de
l’export WebInspector ; cela ne permet pas de conclure que l’application est
accessible sans session.

L’inspection non authentifiée du tenant montre le contrat léger suivant :

```http
GET  /eurecia/login.do
GET  /eurecia/login.do?ajax=false&email=<email>
POST /eurecia/login.do
Content-Type: application/x-www-form-urlencoded

requestedURL=&requestParams=&email=<email>&password=<password>
```

Le deuxième appel est un précontrôle : une réponse JSON contenant
`redirectUrl` indique que l’interface web privilégie un parcours SSO. Sur le
tenant observé, l’utilisateur authentifié déclare cependant aussi
`canConnectByPassword: true`. Le formulaire legacy direct est toutefois refusé.
Le prototype suit donc `redirectUrl`, charge le formulaire de mot de passe
Keycloak sur `plateforme-idp.eurecia.com`, conserve ses champs cachés, soumet le
mot de passe puis suit la redirection vers `eurecia/login.do`. Il utilise enfin
`GET /api/v3/users/me/initData` pour vérifier objectivement si une session a été
créée. Cette automatisation légère refuse un domaine d’identité différent, un
formulaire ambigu, une MFA ou tout écran interactif supplémentaire. Le client
conserve les cookies dans un `CookieJar` en mémoire ; il n’enregistre ni mot de
passe ni cookie sur disque.

Lorsque le flux Keycloak simple ne suffit pas, `--browser-session` permet d’importer
le header `Cookie` d’une requête `api/v3/users/me/initData` effectuée par un
navigateur déjà authentifié par SSO. La valeur est saisie dans une invite
masquée, chargée dans le même `CookieJar`, puis validée par un nouvel appel à
`initData`. Elle n’apparaît donc ni dans les arguments du processus, ni dans
l’historique du shell, ni sur disque. Cette session reste personnelle,
révocable et limitée par son expiration côté Eurecia.

Pour un test forensic uniquement, les requêtes JSON peuvent être rejouées avec
la session active du navigateur :

```bash
curl --fail --silent --show-error \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'Referer: https://<tenant>.eurecia.com/eurecia/timesheet/Open.do' \
  --cookie "$EURECIA_SESSION_COOKIE" \
  'https://<tenant>.eurecia.com/eurecia/api/v1/timeSynthesis/translations?locale=fr_FR'
```

`EURECIA_SESSION_COOKIE` est un placeholder : aucune valeur réelle ne doit être
mise dans le dépôt ou dans la documentation. Pour bd-1, une session web
copiée n’est pas une stratégie d’intégration durable ; il faut privilégier une
intégration Eurecia officielle avec des identifiants dédiés si elle est
disponible.

## Détection du type de feuille

L’appel suivant est effectué par le portail :

```http
GET /api/v1/whatconcernsme/timesheet
Accept: application/json
```

La réponse observée est de la forme :

```json
{
  "useNewTimesheet": false,
  "legacyDetails": {
    "mode": "edit",
    "actionLink": "timesheet/Open.do?...",
    "label": "2026 Semaine 30",
    "startDate": 1784527200000
  }
}
```

`useNewTimesheet: false` explique pourquoi le portail ouvre la pile legacy
`timesheet/*.do`. `actionLink` est la meilleure source pour ouvrir la feuille :
ses identifiants sont opaques et ne doivent pas être reconstruits à partir de
dates ou de chaînes devinées.

## Navigation vers la feuille

La navigation observée dans `opentimesheet` est :

```http
GET /timesheet/Browse.do?idService=<serviceId>&mdleid=3
```

Puis l’interface déclenche :

```http
GET /timesheet/Browse.do?ctrl=list&action=Edit&param=<opaqueParam>
```

Cette dernière réponse est `302` vers une URL de la forme :

```http
GET /timesheet/Open.do?mode=edit&id=<timesheetId>&idService=<serviceId>&filterUser=undefined
```

Dans les captures d’édition, l’ouverture directe est aussi observée sous la
forme :

```http
GET /timesheet/Open.do?mode=edit&id=<timesheetId>
```

Paramètres :

| Paramètre | Rôle observé | Recommandation |
| --- | --- | --- |
| `idService` | Identifiant opaque du service de feuilles de temps | Le récupérer depuis `actionLink` ou le portail |
| `mdleid` | `3` dans l’entrée de menu de la feuille | Ne pas le considérer comme un identifiant utilisateur |
| `ctrl` | `list` dans la navigation legacy | Paramètre d’interface |
| `action` | `Edit` pour demander l’édition | Paramètre d’interface |
| `param` | Identifiant opaque transmis à `Browse.do` | Ne pas le fabriquer |
| `mode` | `edit` pour ouvrir la feuille | Valeur observée |
| `id` | Identifiant opaque de la feuille | Ne pas le fabriquer |
| `filterUser` | `undefined` dans une redirection observée | Optionnel dans les captures directes |

Le motif des identifiants ressemble à des composants séparés par la chaîne
`[.]`, mais ce motif est une observation et non une règle de construction.

L’entrée `Open.do` avec le statut `0` dans le HAR d’ouverture est suivie
immédiatement par la même navigation avec le statut `200`. Il s’agit d’une
entrée abandonnée ou dupliquée du chargement, pas d’un contrat d’erreur
fonctionnel documenté.

Le client parcourt uniquement la première page de `Browse.do`, à laquelle il
ajoute la feuille courante annoncée par `whatconcernsme/timesheet` si elle n’y
figure pas déjà. Une semaine plus ancienne absente de ces résultats est donc
signalée comme introuvable ; le client ne devine jamais son identifiant.

## Lecture des traductions

```http
GET /api/v1/timeSynthesis/translations?locale=fr_FR
```

Réponse : objet JSON de 11 clés dans la capture. Les clés utiles à la synthèse
comprennent notamment :

```json
{
  "timeSheet.open.synthesis.workingHours.theoricTime": "Temps théorique",
  "timeSheet.open.synthesis.workingHours.countedAsWorked": "Comptées comme travaillées",
  "timeSheet.open.synthesis.workingHours.countInAnnualization": "Compté dans l’Annualisation/Modulation",
  "timeSheet.open.synthesis.workingHours.difference": "Ecart",
  "timeSheet.open.synthesis.workingHours.remaining": "Reste à faire",
  "timeSheet.open.synthesis.overtimeHours.calculatedOvertime": "Heures supplémentaires calculées",
  "timeSheet.open.synthesis.overtimeHours.validatedOvertime": "Heures supplémentaires validées (hors majorations)"
}
```

Le texte de la clé `overtimeHours.info` précise que le calcul des heures
supplémentaires se fait par semaine complète, du lundi au dimanche. Une feuille
partielle peut donc inclure des jours de la feuille précédente ou suivante.

## Lecture de la synthèse des heures

```http
GET /api/v1/timeSynthesis/workingHours \
  ?userId=<userId> \
  &startDate=2026-07-20 \
  &endDate=2026-07-26 \
  &timeOrActivity=time
```

Caractéristiques observées :

- réponse `200 application/json` ;
- requête sans body ;
- `startDate` et `endDate` au format ISO `YYYY-MM-DD` ;
- `userId` opaque, distinct de `idService` ;
- `timeOrActivity=time` dans toutes les captures ;
- l’appel est fait par `vue-resource` avec `X-Requested-With: XMLHttpRequest` ;
- le `Referer` est la page `timesheet/Open.do`.

Exemple d’appel désensibilisé :

```bash
curl --fail --silent --show-error \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --cookie "$EURECIA_SESSION_COOKIE" \
  'https://<tenant>.eurecia.com/eurecia/api/v1/timeSynthesis/workingHours?userId=<userId>&startDate=2026-07-20&endDate=2026-07-26&timeOrActivity=time'
```

### Schéma de réponse

Le JSON suit une hiérarchie de périodes : période d’annualisation, feuille
courante, semaine, puis journée.

```json
{
  "label": "Synthèse",
  "years": [
    {
      "label": "Annualisation/Modulation Total période",
      "start": [2026, 6, 1],
      "end": [2027, 5, 31],
      "theoric": "<Summary>",
      "theoricIgnoreLeaves": "<Summary>",
      "real": "<Summary>",
      "overtime": "<Summary>",
      "validatedOvertime": "<Summary>",
      "simulated": "<Summary>",
      "periods": []
    }
  ],
  "timesheetPeriod": {
    "label": "Feuille courante",
    "start": [2026, 7, 20],
    "end": [2026, 7, 26],
    "theoric": "<Summary>",
    "theoricIgnoreLeaves": "<Summary>",
    "real": "<Summary>",
    "overtime": "<Summary>",
    "validatedOvertime": "<Summary>",
    "simulated": "<Summary>",
    "periods": [
      {
        "label": "S 30",
        "start": [2026, 7, 20],
        "end": [2026, 7, 26],
        "periods": [
          {
            "label": "2026-07-20",
            "start": [2026, 7, 20],
            "end": [2026, 7, 20],
            "theoric": "<Summary>",
            "real": "<Summary>",
            "overtime": "<Summary>",
            "validatedOvertime": "<Summary>",
            "simulated": "<Summary>"
          }
        ]
      }
    ]
  },
  "annualized": true
}
```

Dans cet exemple, les mois des tableaux `start`/`end` sont indexés de 1 à 12,
contrairement à certains objets JavaScript qui utilisent des mois indexés de 0
à 11. Il faut conserver les valeurs reçues plutôt que les reconstruire.

### Objet `Summary`

Chaque collection (`theoric`, `real`, etc.) possède la structure suivante :

| Champ | Type | Signification observée |
| --- | --- | --- |
| `group` | nombre ou `null` | Groupe de synthèse ; souvent `null` au total |
| `label` | chaîne ou `null` | Libellé du total |
| `nbMinutes` | nombre | Quantité en minutes |
| `nbDays` | nombre | Quantité en jours, pouvant être négative pour des déductions |
| `lines` | tableau | Détail par groupe |
| `formattedQuantity` | chaîne | Affichage `HH:MM`, y compris pour des durées supérieures à 24 h |

Les lignes de `lines` reprennent `group`, `label`, `nbMinutes`, `nbDays` et
`formattedQuantity`. Les libellés observés sont `Horaire`, `Temps travaillé`,
`Jour férié` et `Congés payés`.

Collections principales :

- `theoric` : horaire théorique ;
- `theoricIgnoreLeaves` : théorique en ignorant certains congés ;
- `real` : temps effectivement comptabilisé ;
- `overtime` : heures supplémentaires calculées ;
- `validatedOvertime` : heures supplémentaires validées ;
- `simulated` : valeur de simulation utilisée par l’annualisation/modulation.

Ce endpoint ne renvoie pas les segments bruts avec leurs heures de début et de
fin. Il renvoie des agrégats journaliers et hebdomadaires. Il ne suffit donc
pas, à lui seul, pour reconstruire une feuille segment par segment ni pour
fabriquer un payload d’écriture.

## Ce que les scénarios d’édition prouvent

Les totaux ci-dessous sont ceux du champ `timesheetPeriod.real.nbMinutes` ; le
total du mardi est celui du jour `2026-07-21`.

| Scénario | Appels `workingHours` | Total feuille | Mardi |
| --- | ---: | ---: | ---: |
| Ouverture | 1 | 2150 min | 430 min |
| Décalage d’une heure le lundi | 2 | 2150 → 2150 min | inchangé |
| Suppression/ajouts de segments | 5 | 2150 → 1935 → 1935 → 2055 → 2115 min | 430 → 215 → 215 → 335 → 395 min |

Les lectures successives montrent donc que l’état côté serveur ou côté
application évolue pendant le scénario d’ajout/suppression. Cependant :

- aucune entrée HAR ne contient la requête qui modifie l’état ;
- aucune réponse JSON de `workingHours` ne contient un identifiant de segment,
  une heure de début ou une heure de fin ;
- le scénario de décalage ne permet pas de prouver que le décalage a été
  enregistré, puisque la synthèse reste identique.

Il serait incorrect de déduire une route d’écriture, une méthode HTTP ou un
format de payload à partir de ces seules variations. Le contrat d’écriture
décrit plus bas ne vient donc pas de ces HAR : il provient des formulaires
`Open.do` complets et des essais authentifiés effectués ensuite.

## Routes à ne pas confondre avec l’écriture d’une feuille

Une inspection complémentaire des bundles JavaScript publics référencés par la
page fait apparaître des routes qui ne sont pas observées dans les HAR. Elles
doivent rester considérées comme non validées :

| Route | Interprétation probable | Pourquoi elle ne suffit pas |
| --- | --- | --- |
| `POST /api/v2/selfservice/<companyId>/createTimesheet` | Création/configuration d’une feuille côté self-service | Ne décrit pas l’édition des segments d’une feuille existante |
| `POST /api/v1/planning-team/saveEvents` | Sauvegarde d’évènements de planning | Module planning, payload et lien avec une feuille personnelle inconnus |
| `DELETE /api/v1/planning-team/deleteEvents` | Suppression d’évènements de planning | Même réserve ; non présent dans les captures |
| `PUT /api-gta/v1/timeClock/statuses` | Pointage entrée/sortie | Ne correspond pas à la saisie de segments de feuille |

Ces routes ne doivent pas être utilisées par bd-1 sans une capture ciblée et
une vérification des droits et du modèle métier.

## Contrat d’écriture legacy observé

Toutes les mutations observées soumettent le formulaire retourné par
`Open.do` vers son propre `action`, généralement en `POST`. BD-1 conserve les
champs cachés, les imputations et les autres valeurs qu’il ne modifie pas. Il
utilise l’encodage déclaré par le formulaire :

- `application/x-www-form-urlencoded` ; ou
- `multipart/form-data` avec une frontière générée pour la requête.

### Passer une journée Standard en saisie détaillée

La case « Standard » pilote plusieurs champs cachés. Pour la désactiver, BD-1
rejoue le formulaire avec notamment :

```text
standardValueSelectedRow=false
infoSelectedRow=<jour>:<date>:<row>
ctrla=timeSheetOpenForm=LoadTime
```

La réponse `Open.do` doit alors exposer les quatre sélecteurs éditables de la
ligne :

```text
startHour_Hours_N
startHour_Minutes_N
endHour_Hours_N
endHour_Minutes_N
```

### Ajouter et supprimer des lignes

Le menu « Nouveau » et l’action de suppression utilisent les valeurs suivantes
dans le champ `ctrla` :

```text
times=Copy=row_N
times=Delete=row_N
```

BD-1 reparcourt le HTML après chaque action et vérifie que le nombre de lignes
éditables a changé exactement de un. Les numéros de lignes sont toujours relus
depuis la réponse ; ils ne sont pas déduits localement.

Une ligne sans les quatre sélecteurs horaires et dont le marqueur `standard_N`
est faux est considérée comme synchronisée et verrouillée. C’est notamment le
cas des lignes « Congés payés » et « Jour férié ». Ces lignes ne sont jamais
modifiées ni supprimées. Si BD-1 possède du travail pour le même jour, il crée
une ligne éditable supplémentaire à côté de la ligne synchronisée.

### Enregistrer sans soumettre

Les horaires sont envoyés dans les quatre sélecteurs de chaque ligne, avec les
marqueurs `generatedItem_N` et `duplicatedItem_N` remis à `false`. La sauvegarde
observée utilise :

```text
validate=2
btnApply=clicked
```

Le DOM Eurecia ne respecte pas toujours l’unicité des identifiants : plusieurs
boutons de workflow peuvent porter `id="btnApply"`, par exemple « Soumettre à
validation » et « Transférer la validation ». BD-1 sélectionne un contrôle
explicitement libellé « Enregistrer » lorsqu’il existe sans ambiguïté. Sinon,
la présence de l’unique champ `validate` permet de rejouer le contrat observé
ci-dessus avec un champ dynamique `btnApply=clicked`. Les boutons de soumission
ou de transfert ne sont jamais déclenchés.

Après le `POST`, BD-1 rouvre la feuille et compare tous les segments des jours
ciblés. Une erreur pendant cette relecture ne constitue pas un rollback : la
sauvegarde peut déjà avoir réussi. Le journal distingue donc la sauvegarde de
la vérification, et une nouvelle exécution réconcilie à nouveau le nombre de
lignes avant d’écrire.

### Points qui restent non documentés

Les éléments suivants ne sont ni automatisés ni considérés comme établis :

- soumission de la feuille à un responsable ;
- transfert ou validation par un responsable ;
- MFA et écrans SSO interactifs supplémentaires ;
- nouvelle interface lorsque `useNewTimesheet` vaut `true` ;
- API d’intégration officielle et stabilité contractuelle des formulaires
  legacy.

## Prototype HTTP léger dans bd-1

Le module `src/bd1/eurecia.py` utilise uniquement la bibliothèque standard
Python (`urllib`, `http.cookiejar` et `html.parser`). Son enchaînement est :

1. ouvrir `login.do`, exécuter le précontrôle de l’e-mail puis soumettre le
   formulaire de connexion ;
2. vérifier la session avec `api/v3/users/me/initData` ;
3. retrouver dynamiquement le lien « Mes feuilles de temps » dans
   `userLeftMenu` ;
4. parser la première page `timesheet/Browse.do` et conserver les liens
   d’édition opaques ;
5. ouvrir `timesheet/Open.do` et associer les champs horaires aux dates de la
   semaine à partir du HTML rendu par le serveur ;
6. pour une écriture explicite, désactiver « Standard » avec
   `ctrla=timeSheetOpenForm=LoadTime`, puis ajuster le nombre de lignes avec
   `ctrla=times=Copy=row_N` et `ctrla=times=Delete=row_N` ;
7. conserver tous les champs du formulaire, remplacer les sélecteurs d'heures,
   envoyer `validate=2` et le champ dynamique `btnApply=clicked`, sans se fier
   à l’unicité de l’identifiant HTML `btnApply` ;
8. rouvrir la feuille et vérifier que chaque segment correspond à la cible.

Commandes pour la semaine ISO 23 de 2026, soit du 1er au 7 juin :

```bash
export BD1_EURECIA_BASE_URL='https://<tenant>.eurecia.com/eurecia/'
export BD1_EURECIA_EMAIL='<email>'

bd1-eurecia list
bd1-eurecia show --year 2026 --week 23
bd1-eurecia set-standard-week --year 2026 --week 23
bd1-eurecia set-standard-week --year 2026 --week 23 --apply
```

Les options globales doivent précéder la sous-commande. Par exemple, pour
capturer une page privée sans l’écrire :

```bash
bd1-eurecia \
  --base-url 'https://<tenant>.eurecia.com/eurecia/' \
  capture-html \
  --year 2026 \
  --week 29 \
  --output /chemin/prive/open-week29-2026.html
```

Le fichier est créé en mode `0600` et n’est jamais écrasé.

Équivalent pour un tenant imposant le SSO, après copie du header `Cookie`
depuis la requête authentifiée `api/v3/users/me/initData` du navigateur :

```bash
bd1-eurecia --browser-session list
bd1-eurecia --browser-session show --year 2026 --week 23
bd1-eurecia --browser-session set-standard-week --year 2026 --week 23
bd1-eurecia --browser-session set-standard-week --year 2026 --week 23 --apply
```

Sans `--apply`, `set-standard-week` n’écrit rien. Avec `--apply`, la commande vise
uniquement du lundi au vendredi, avec `09:00-12:00` et `14:00-18:00`, soit
35 heures. Le prototype sauvegarde mais ne soumet pas la feuille.

Les refus sont volontaires : statut non établi comme `Nouvelle`, formulaire sans
`POST`, lignes non associables sans ambiguïté à une date, ou résultat sauvegardé
différent de la cible. Le client sait suivre le formulaire SSO Eurecia observé,
mais refuse les étapes interactives supplémentaires comme le MFA.

Le rapport hebdomadaire de BD-1 et le CLI principal utilisent la même conversion
des données. Ils remplacent les lignes éditables de chaque jour ouvré affiché
par les segments de travail BD-1 :

```bash
bd1 --push-eurecia 29
bd1 --push-eurecia 29 --year 2026
```

Le CLI affiche d’abord le récapitulatif et exige une confirmation explicite. La
fenêtre graphique affiche un journal non modifiable mais copiable, avec le
résultat final en vert ou en rouge. Dans les deux cas, le plafond hebdomadaire
est appliqué s’il est actif.

Seuls les blocs de travail deviennent des segments Eurecia ; les pauses sont
les intervalles entre ces segments. Les heures sont celles affichées par BD-1,
à la minute (`HH:MM`). Les jours doivent appartenir à la semaine ISO demandée,
être uniques, et leurs segments triés ne doivent pas se chevaucher.

Une journée affichée sans segment est vidée avec une ligne
`00:00`–`00:00`, sauf si elle ne contient que des lignes verrouillées : celles-ci
sont conservées sans créer de ligne vide. Les week-ends et jours fériés non
affichés restent inchangés. Un congé synchronisé situé sur un jour ouvré reste
également inchangé ; une éventuelle plage de travail BD-1 est ajoutée sur une
ligne distincte. La feuille est sauvegardée, jamais soumise.

L’URL du tenant et l’e-mail sont enregistrés dans `settings.json`. Avec le
consentement explicite de l’utilisateur, le mot de passe peut être enregistré
dans le trousseau sécurisé du système, séparément pour chaque tenant et adresse
e-mail. Sinon, il reste uniquement en mémoire. La fenêtre de rapport conserve
sa session et se réauthentifie si `initData` indique qu’elle a expiré. Le CLI
ouvre une nouvelle session à chaque exécution et réutilise le secret du
trousseau lorsqu’il existe.

Lors de l’export depuis un rapport BD-1, une journée dont au moins une
observation réseau brute est classée comme distante reçoit le commentaire
`Télétravail/Remote` sur sa première ligne éditable. Les commentaires existants
sont conservés et le marqueur est retiré seul si un export ultérieur classe la
journée au bureau. Sans observation réseau exploitable, aucun commentaire de
localisation n’est ajouté.

## Recommandation d’intégration bd-1

L’écriture et sa vérification ont fonctionné sur le tenant observé, mais elles
reposent toujours sur une interface web privée. Pour une intégration fiable :

- demander à Eurecia le contrat d’API d’intégration et le mécanisme
  d’authentification prévu pour une application tierce ;
- utiliser si possible un compte/service ou un jeton dédié ;
- conserver les identifiants opaques renvoyés par Eurecia et ne pas les déduire ;
- après chaque écriture, relire les segments ciblés avant de considérer la
  sauvegarde comme vérifiée ;
- signaler séparément l’échec de sauvegarde et l’échec de vérification, car il
  n’existe pas de rollback observé ;
- conserver une procédure de saisie manuelle lorsque le HTML privé change ;
- ne pas automatiser la soumission tant que son contrat et ses conséquences ne
  sont pas établis.
