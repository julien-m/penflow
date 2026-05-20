---
screen: checkout
mockup: checkout.png
flow: checkout
sourceNodeId: checkoutScreen
sourceFile: ui.pen
generated_at: "2026-05-20"
---

# Écran — Checkout

- **Acteur:** Returning customer
- **Source d'entrée:** Customer opens the checkout route with an order in progress
- **Sortie principale:** Payment is submitted and the runtime contract can be compared

## Données affichées

- Order summary
- Selected payment method

## Actions

| Élément | Type | Effet |
|---------|------|-------|
| Pay now | button | POST /payments → confirmation |

## Validations

- A selected payment method is required before submitting payment

## États UI

default · submitting · error · success

## Erreurs

- Missing payment method → "Choose a payment method before paying."
- Payment failed → "Payment failed. Try again."

## Side effects locaux

- The submitting state is shown while the payment request is in flight
