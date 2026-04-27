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
