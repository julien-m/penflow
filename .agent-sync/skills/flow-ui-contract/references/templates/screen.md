<!-- @spec FR-004: Screen spec template — ../../../../../.specs/features/027-define-flow-screen-spec-grammar/spec.md#fr-004 -->

<!-- TEMPLATE: Copy this file as <target>/flow-ui-contract/screens/<screen-id>.md -->
<!-- Replace all <placeholder> values. Remove all <!-- TEMPLATE: comments. -->

---
screen: <filename-without-extension>
mockup: <product_parent_subview_state.png>
flow: <flow-slug>
sourceNodeId: <pencil-node-id-or-null>
sourceFile: ui.pen
generated_at: "<YYYY-MM-DD>"
---

# Écran — <Human-readable screen title>

- **Acteur:** <e.g. "Praticienne connectée", "Visiteur anonyme">
- **Source d'entrée:** <How does the user arrive here? e.g. "Clic sur 'Réserver' depuis la page profil">
- **Sortie principale:** <What is the primary outcome of interacting with this screen?>

## Données affichées

<!-- List all data elements visible on this screen.
     Each bullet = one data element or block.
     Use sub-bullets for grouped data (e.g. a card with multiple fields). -->

- <Data element 1, e.g. "Nom et prénom de la praticienne">
- <Data element 2, e.g. "Photo de profil">
- <Data block: Disponibilités>
  - <Sub-element: date>
  - <Sub-element: créneau horaire>
- <Data element N>

## Actions

<!-- Table of all interactive elements on this screen.
     Type: button | link | input | select | toggle | swipe | tap | form
     Effet: what happens when the user interacts (navigation, API call, state change, modal open, etc.) -->

| Élément | Type | Effet |
|---------|------|-------|
| <CTA label, e.g. "Confirmer la réservation"> | button | <Effect, e.g. "POST /bookings → redirect to confirmation screen"> |
| <element 2> | <type> | <effect> |
| <element N> | <type> | <effect> |

## Validations

<!-- List validation rules applied on this screen (form fields, business rules, etc.).
     Each bullet = one validation rule. Write as a condition: "If X then Y". -->

- <Validation 1, e.g. "Le champ téléphone doit contenir 10 chiffres">
- <Validation 2, e.g. "La date de réservation doit être dans le futur">
- <Validation N>

<!-- If no validations: write "— aucune —" -->

## États UI

<!-- List all UI states this screen can be in, separated by · (middle dot U+00B7).
     States: loading · empty · error · success · disabled · partial · etc. -->

<state1> · <state2> · <state3>

<!-- Example: chargement · vide · erreur réseau · confirmé -->

## Erreurs

<!-- List all error conditions and their user-facing messages.
     Format: "Condition → Message affiché" -->

- <Error condition 1> → "<User-facing message>"
- <Error condition 2> → "<User-facing message>"

<!-- If no errors: write "— aucune —" -->

## Side effects locaux

<!-- List all local (client-side) state changes triggered by interactions on this screen.
     Do NOT list server-side effects here (those belong in the flow spec FR/AC).
     Examples: localStorage write, navigation, scroll to top, modal open/close. -->

- <Side effect 1, e.g. "Le créneau sélectionné est stocké dans sessionStorage">
- <Side effect 2, e.g. "La page retourne en haut au chargement">

<!-- If no local side effects: write "— aucun —" -->
