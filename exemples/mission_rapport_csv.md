OBJECTIF : produire un rapport d'analyse des ventes.
CONTEXTE : les fichiers CSV sont dans le dossier ventes/ (colonnes : date, produit, quantite, prix).
S'il n'y en a pas, crée un jeu de données fictif de 200 lignes pour tester.
ÉTAPES ATTENDUES :
1. Lire et nettoyer les données (lignes vides, doublons).
2. Calculer : chiffre d'affaires total, par mois, top 5 des produits.
3. Générer un graphique (si matplotlib est disponible, sinon un tableau texte).
LIVRABLE : rapports/analyse_ventes.md (+ le script analyse.py réutilisable).
CRITÈRES DE RÉUSSITE : le script s'exécute sans erreur et les totaux sont recalculés pour vérification.
INTERDIT : modifier les fichiers CSV d'origine.
