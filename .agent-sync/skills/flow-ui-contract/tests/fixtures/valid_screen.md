---
screen: mobile_booking_form
mockup: mobile_booking_form.png
flow: booking
sourceNodeId: node-abc123
sourceFile: ui.pen
generated_at: "2026-04-29"
---

# Écran — Formulaire de réservation

- **Acteur:** Client connecté
- **Source d'entrée:** Clic sur "Réserver" depuis la page profil praticienne
- **Sortie principale:** Réservation créée, redirection vers écran de confirmation

## Données affichées

- Nom de la praticienne
- Photo de profil
- Créneaux disponibles (liste par date)
- Prix de la séance
- Résumé de la sélection courante

## Actions

| Élément | Type | Effet |
|---------|------|-------|
| Créneau horaire | tap | Sélectionne le créneau, met à jour le résumé |
| Bouton "Confirmer" | button | POST /bookings → redirection confirmation |
| Lien "Annuler" | link | Retour à la page profil sans création |

## Validations

- Un créneau doit être sélectionné avant de pouvoir confirmer
- Le créneau sélectionné doit toujours être disponible au moment de la soumission

## États UI

chargement · créneau-sélectionné · soumission-en-cours · erreur · succès

## Erreurs

- Créneau devenu indisponible → "Ce créneau vient d'être réservé. Veuillez en choisir un autre."
- Erreur réseau → "Une erreur est survenue. Réessayez."

## Side effects locaux

- Le créneau sélectionné est stocké en mémoire pour pré-remplir en cas de retour arrière
