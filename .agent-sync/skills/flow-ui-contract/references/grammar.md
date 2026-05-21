<!-- @spec FR-001: Grammar frozen contract — ../../../../.specs/features/027-define-flow-screen-spec-grammar/spec.md#fr-001 -->

# Grammar — flow-ui-contract Output Contract (Frozen)

> **This file is the single source of truth for all format rules governing flow and screen specs.**
> No other file may re-state these rules. Callers reference this file; they do not copy its content.
> Changing this file is a breaking change — update `validator.py` and tests in the same commit.

---

## 1. flow.md — Frontmatter (YAML, mandatory)

```yaml
---
flow: <slug-lowercase>           # string, kebab-case, unique within project
title: <human title>             # string
status: draft                    # enum: draft | reviewed | promoted
priority: P1                     # enum: P1 | P2 | P3
mockups:                         # array of filenames WITHOUT extension
  - web_dashboard
  - mobile_onboarding_step1
surfaces:                        # array, each value ∈ {mobile, web, landing, showcase, admin}
  - mobile
  - web
source:                          # array of paths to product artefacts consulted
  - <target>/project-profile.md
  - <target>/01-exploration.md
generated_at: "2026-04-29"       # ISO-8601 date string
---
```

**Field rules:**
- `flow`: non-empty, lowercase, no spaces, kebab-case; used as filename stem.
- `status`: must be one of `draft`, `reviewed`, `promoted`. `NEEDS CLARIFICATION` count > 3 blocks `reviewed`/`promoted`.
- `priority`: must be one of `P1`, `P2`, `P3`.
- `mockups`: array of strings (filename without extension); may be empty array for flows with no current mockups (validator issues WARNING).
- `surfaces`: non-empty array; each element must be one of `{mobile, web, landing, showcase, admin}`.
- `source`: array of strings (paths); may be empty.
- `generated_at`: ISO-8601 date or datetime string.

---

## 2. flow.md — Sections (mandatory, in this exact order)

```markdown
# Flow Spec: <title>

- **Project:** <slug>
- **Flow ID:** FLOW-<NAME-UPPER>
- **Status:** draft | reviewed | promoted
- **Primary Actor:** <actor description>
- **Surfaces:** <comma-separated surface list>
- **Mockups:** <comma-separated mockup filenames without extension>
- **Source:** <comma-separated source paths>

## Input

## User Scenarios & Testing

### P1 — <title>
### P2 — <title>   (optional — include if stories at this priority exist)
### P3 — <title>   (optional)

## Acceptance Criteria

## Functional Requirements

## Key Entities

## Edge Cases

## Success Criteria
```

**Section rules:**
- Section titles must match EXACTLY (case, spacing, punctuation) — the validator uses exact string matching.
- `# Flow Spec: <title>` — H1 must start with `Flow Spec: `.
- Header bullets (`- **Project:**` etc.) must appear between the H1 and the first `##` section — order within the bullet block is not enforced.
- `## User Scenarios & Testing` — must contain at least one `### P1 — ` story.
- All 8 `##` sections are mandatory even if empty (except stories at P2/P3 level which are optional).

---

## 3. flow.md — Story Format (per story block)

Each story block under `### P<N> — <title>` must contain ALL of the following, in this order:

1. Narrative bullets:
   ```markdown
   - **As a** <actor>
   - **I want** <goal>
   - **So that** <benefit>
   ```
2. `**Priority reason:**` — one-line justification.
3. `**Independent test:**` — one-line description of how to test in isolation.
4. At least one fenced Gherkin block:
   ````markdown
   ```gherkin
   Feature: <name>
     Scenario: <name>
       Given ...
       When  ...
       Then  ...
   ```
   ````
5. At least one fenced Mermaid block:
   ````markdown
   ```mermaid
   flowchart TD
       ...
   ```
   ````

**Non-negotiable rules:**
- Gherkin block MUST use ` ```gherkin ` fence (not ` ``` `, not ` ```text `).
- Gherkin block MUST contain `Feature:` and `Scenario:` keywords.
- Pseudo-Gherkin in bullet list form is BLOCKING.
- Mermaid block MUST use ` ```mermaid ` fence.
- For flow.md: Mermaid MUST contain `flowchart TD` or `flowchart LR`.
- Language consistency: prose may be French or English, but consistent within a single file. Gherkin keywords (Feature, Scenario, Given, When, Then, And, But) remain in English always.

---

## 4. flow.md — ID Formats

| ID type | Format | Regex | Example |
|---|---|---|---|
| Flow ID | `FLOW-<NAME-UPPER>` | `^FLOW-[A-Z][A-Z0-9-]*$` | `FLOW-BOOKING` |
| AC ID | `AC-NNN` | `^AC-\d{3}$` | `AC-001` |
| FR ID | `FR-NNN` | `^FR-\d{3}$` | `FR-001` |
| SC ID | `SC-NNN` | `^SC-\d{3}$` | `SC-001` |

**Sequentiality rule:** AC, FR, SC IDs must be sequential starting at 001, no gaps (AC-001, AC-002, AC-003 — not AC-001, AC-003).

**AC↔FR mapping rule:**
- Every AC must be cited by at least one FR (search the text of each FR for the token `AC-NNN`).
- No FR may cite an AC that does not exist in the `## Acceptance Criteria` section.

---

## 5. screen.md — Frontmatter (YAML, mandatory)

```yaml
---
screen: <filename-without-extension>   # string, matches the mockup filename stem
mockup: <filename-with-extension>      # string, e.g. "web_dashboard_sidebar.png"
flow: <flow-slug>                      # string, must match a flow slug in the project
sourceNodeId: <pencil-node-id>         # string or null
sourceFile: ui.pen                     # string (typically "ui.pen")
generated_at: "2026-04-29"            # ISO-8601 date string
---
```

---

## 6. screen.md — Sections (mandatory, in this exact order)

```markdown
# Écran — <title>

- **Acteur:** <actor>
- **Source d'entrée:** <how the user arrives at this screen>
- **Sortie principale:** <primary outcome>

## Données affichées

## Actions

| Élément | Type | Effet |
|---------|------|-------|
| ...     | ...  | ...   |

## Validations

## États UI

<state1> · <state2> · <state3>

## Erreurs

## Side effects locaux
```

**Section rules:**
- `# Écran — ` is the canonical H1 prefix. English alternative `# Screen — ` is accepted by the validator.
- `## Actions` must contain a markdown table with columns `Élément | Type | Effet` (or English equivalents `Element | Type | Effect`).
- `## États UI` must use `·` (middle dot) as separator between states.
- All 6 `##` sections are mandatory even if content is minimal (e.g., `— none —`).

---

## 7. NEEDS CLARIFICATION Policy

- Marker: `[NEEDS CLARIFICATION]` (exact string, case-sensitive).
- Allowed in any section as a placeholder for unresolved business questions.
- Count ≤ 3 per flow file: no warning.
- Count > 3: validator issues `[WARNING]` — blocks `reviewed`/`promoted` status but not `draft`.
- Screen files: no NEEDS CLARIFICATION limit (validator counts them as INFO only).

---

## 8. Fresh/Stale Status

Status mode reads `<target>/mockups/manifest.json` and reports each export as:
- `fresh`: `specStatus` and `specGeneratedAt` exist, and `sourceGeneratedAt <= specGeneratedAt`.
- `stale`: `specStatus` and `specGeneratedAt` exist, but `sourceGeneratedAt > specGeneratedAt`.
- `unspecified`: `specStatus` or `specGeneratedAt` is missing.

Status command:

```bash
python3 .agent-sync/skills/flow-ui-contract/validator.py --status --target <target>
```

Status output:

```text
STATUS_RESULT: PASS | FAIL
TARGET: <target>
SCREENS:
  - <mockup-stem> | fresh | flow=<flow-slug> | spec=<screen-slug>
SUMMARY:
  fresh: <N>
  stale: <N>
  unspecified: <N>
```

Missing or invalid `manifest.json` returns `STATUS_RESULT: FAIL` and exit code `1`.

---

## 9. Validator Output Format

```
VALIDATION_RESULT: PASS | FAIL
FILE: <path>
ERRORS:
  - [BLOCKING] <message> (line N)
  - [WARNING] <message>
INFO:
  - <stat>
```

- `VALIDATION_RESULT: PASS` → exit code 0.
- `VALIDATION_RESULT: FAIL` → exit code 1 (at least one BLOCKING error).
- WARNING-only results still exit 0 (warnings are surfaced but do not block `draft` writes).

---

*Grammar version: 1.1 — Frozen 2026-05-20. Any change is a breaking change requiring validator + test updates.*
