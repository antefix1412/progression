# Déploiement sur Vercel

Cette application Flask est configurée pour être déployée sur Vercel.

## Configuration des variables d'environnement

Sur Vercel, ajoutez ces variables d'environnement dans les paramètres de votre projet :

1. Allez sur https://vercel.com/dashboard
2. Sélectionnez votre projet
3. Allez dans **Settings** > **Environment Variables**
4. Ajoutez les variables suivantes :

```
FFTT_PASSWORD=g2XCYk1eK3
FFTT_ID_APP=SW436
FFTT_SERIE=RSJKKEQZCLBACUX
FFTT_CLUB_NUM=03350022
FFTT_TEST_API_TOKEN=choisir-un-token-long-et-prive
FFTT_TEST_PLAYER_LICENSE=3533138
```

Important : le fichier `.env` local n'est pas charge automatiquement en production Vercel.
Les valeurs doivent etre configurees dans **Settings > Environment Variables**.

Alias acceptes par le code (si vous les utilisez deja) :

```
MOTDEPASSE (alias de FFTT_PASSWORD)
ID_APP (alias de FFTT_ID_APP)
SERIE (alias de FFTT_SERIE)
CLUB_NUM ou NUM_CLUB (alias de FFTT_CLUB_NUM)
TEST_API_TOKEN (alias de FFTT_TEST_API_TOKEN)

## Lien prod pour les donnees completes d'un joueur

L'endpoint protege est :

```
https://<votre-projet>.vercel.app/api/test-player-full?licence=3533138&token=<FFTT_TEST_API_TOKEN>
```

Remarques :

- Le token est obligatoire et doit correspondre a la variable d'environnement `FFTT_TEST_API_TOKEN`.
- Si `licence` est omis, la valeur par defaut vient de `FFTT_TEST_PLAYER_LICENSE` (ou `3533138`).
```

## Déploiement

```bash
# Installez Vercel CLI si ce n'est pas déjà fait
npm i -g vercel

# Déployez
vercel
```

Ou connectez votre dépôt GitHub à Vercel pour un déploiement automatique.

## Fichiers importants

- `vercel.json` - Configuration Vercel
- `requirements.txt` - Dépendances Python
- `app.py` - Application Flask
