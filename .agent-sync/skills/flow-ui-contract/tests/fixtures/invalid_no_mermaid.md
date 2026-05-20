---
flow: booking
title: "Reserve a session"
status: draft
priority: P1
mockups:
  - mobile_booking_form
surfaces:
  - mobile
source: []
generated_at: "2026-04-29"
---

# Flow Spec: Reserve a session

- **Project:** demo
- **Flow ID:** FLOW-BOOKING
- **Status:** draft
- **Primary Actor:** Registered client
- **Surfaces:** mobile
- **Mockups:** mobile_booking_form
- **Source:** —

## Input

Client booking flow.

## User Scenarios & Testing

### P1 — Client books a session

- **As a** registered client
- **I want** to book a session
- **So that** I can meet the practitioner

**Priority reason:** Core flow.

**Independent test:** Book a session end to end.

```gherkin
Feature: Booking
  Scenario: Happy path
    Given the client is authenticated
    When the client confirms a slot
    Then a booking is created
```

<!-- Mermaid block intentionally omitted -->

## Acceptance Criteria

- **AC-001** — The form shows available slots.
- **AC-002** — A confirmation is shown.

## Functional Requirements

- **FR-001** — Fetch slots from API. (mappe AC-001)
- **FR-002** — Show confirmation. (mappe AC-002)

## Key Entities

- **Booking** — A reservation.

## Edge Cases

- Slot becomes unavailable.

## Success Criteria

- **SC-001** — 95% success rate.
