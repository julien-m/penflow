"""Render qualified visual alignment observations as localized Markdown."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from urllib.parse import quote

from .visual_alignment import MAX_PRIORITIZED, Case, Evidence, MachineReport, Notice, Pair

# The report language is scoped to the invocation. Reviewer prose and machine
# diagnostics retain their original wording.
_LABELS: dict[str, tuple[str, str]] = {
    "report": ("Visual alignment report", "Rapport d’alignement visuel"),
    "scope_note": (
        "Pairing uses the supplied capture metadata and PNG dimensions. Layout, capture "
        "freshness, matching data and decisions still require review. Machine verdicts retain "
        "their original scope.",
        "L’appariement s’appuie sur les métadonnées fournies et les dimensions PNG. "
        "Le cadrage, la fraîcheur, les données et les décisions restent à vérifier. "
        "Les verdicts machine gardent leur portée d’origine.",
    ),
    "before": ("Before", "Avant"),
    "after": ("After", "Après"),
    "design": ("Design", "Maquette"),
    "runtime": ("Runtime", "Rendu"),
    "side_by_side": ("Design left · runtime right", "Maquette à gauche · rendu à droite"),
    "screen": ("screen", "écran"),
    "state": ("state", "état"),
    "variant": ("variant", "variante"),
    "viewport": ("logical viewport", "dimensions logiques"),
    "frame": ("frame", "planche"),
    "unknown": ("unknown", "inconnu"),
    "default": ("default", "par défaut"),
    "comparable": ("Comparable", "Comparable"),
    "incompatible": ("Incompatible", "Incompatible"),
    "not_observed": ("Insufficient observation", "Observation insuffisante"),
    "field_missing": ("{0} has no observed {1}.", "{0} sans valeur observée pour « {1} »."),
    "field_conflict": ("Different {0} values.", "Les valeurs diffèrent pour « {0} »."),
    "frame_missing": ("The design frame is unidentified.", "La planche de référence est inconnue."),
    "composite": (
        "A composite board or capture contains multiple states. Pair one reference and one "
        "capture per state.",
        "Une planche ou une capture composite contient plusieurs états. Associer une "
        "référence et une capture par état.",
    ),
    "image_missing": ("Image unavailable · {0}.", "Image indisponible · {0}."),
    "image_file_missing": ("Image unavailable · {0} ({1}).", "Image indisponible · {0} ({1})."),
    "image_invalid": (
        "Image incompatible · {0} · {1} · {2}. {3}",
        "Image incompatible · {0} · {1} · {2}. {3}",
    ),
    "file_unreadable": (
        "file unreadable or outside the evidence root",
        "fichier illisible ou hors du dossier des preuves",
    ),
    "invalid_png": ("invalid or incomplete PNG", "PNG invalide ou incomplet"),
    "image_dimensions": ("unexpected PNG dimensions", "dimensions PNG inattendues"),
    "pointer_unavailable": ("JSON value unavailable", "valeur JSON indisponible"),
    "image_alias": (
        "Both sides point to the same image file.",
        "Les deux côtés pointent vers le même fichier image.",
    ),
    "report_missing": ("Rendered measurements report missing.", "Rapport de mesures absent."),
    "report_unavailable": (
        "Rendered measurements unreadable or invalid · {0}.",
        "Rapport de mesures illisible ou invalide · {0}.",
    ),
    "measurement_error": (
        "The machine report records incompatible measurements.",
        "Le rapport machine signale des mesures incompatibles.",
    ),
    "measurements_missing": (
        "The machine report has no qualified rendered comparison.",
        "Le rapport machine ne contient aucune comparaison de rendu qualifiée.",
    ),
    "not_ready": (
        "Confirm the intended reference and capture matching evidence before proposing "
        "product corrections.",
        "Confirmer la référence visée et réunir des captures comparables avant de proposer "
        "une correction produit.",
    ),
    "priorities": ("Prioritized observations", "Observations prioritaires"),
    "no_priorities": (
        "No evidenced material review observation was supplied. Use the image regions and "
        "technical groups to guide the next review.",
        "Aucune observation matérielle étayée n’a été fournie. Les zones des images et les "
        "groupes techniques peuvent guider la prochaine revue.",
    ),
    "product_fix": ("Product fix", "Correction produit"),
    "recapture": ("Recapture", "Recapture"),
    "clarify_design": ("Clarify the design", "Clarifier la maquette"),
    "approved_divergence": ("Approved divergence", "Divergence approuvée"),
    "visual": ("Reviewer visual interpretation", "Interprétation visuelle du reviewer"),
    "measurement": ("Cited measurement", "Mesure citée"),
    "decision": ("Cited decision", "Décision citée"),
    "missing_observation": ("Insufficient observation", "Observation insuffisante"),
    "provisional": ("Provisional review note", "Note de revue provisoire"),
    "region": ("Image region", "Zone sur les images"),
    "expected": ("Expected", "Attendu"),
    "observed": ("Observed", "Observé"),
    "proposal": ("Proposed action", "Action proposée"),
    "verify": ("Verify", "À vérifier"),
    "evidence": ("Evidence", "Preuves"),
    "approval": ("Decision reference", "Référence de la décision"),
    "unavailable": ("Unavailable", "Indisponible"),
    "withheld": ("Observations withheld", "Observations non retenues"),
    "deferred": ("Other reviewed observations", "Autres observations étayées"),
    "product_pair_unqualified": (
        "Product recommendation requires a comparable pair.",
        "Une correction produit exige une paire comparable.",
    ),
    "product_observation_missing": (
        "Product recommendation requires a visual observation or cited measurement.",
        "Une correction produit exige une observation visuelle ou une mesure citée.",
    ),
    "approval_missing": (
        "The approved divergence needs a readable decision reference.",
        "La divergence approuvée exige une référence de décision lisible.",
    ),
    "evidence_missing": (
        "Supporting evidence is missing or unreadable.",
        "Preuve absente ou illisible.",
    ),
    "measurement_citation_missing": (
        "Provide a JSON pointer to an observed numeric value.",
        "Fournir un pointeur JSON vers une valeur numérique observée.",
    ),
    "visual_citation_missing": (
        "Visual interpretation needs readable paired images.",
        "L’interprétation visuelle exige des images appariées lisibles.",
    ),
    "after_missing": ("No after pair supplied.", "Aucun vis-à-vis après correction fourni."),
    "after_unqualified": (
        "Both pairs must be comparable.",
        "Les deux paires doivent être comparables.",
    ),
    "after_scope_conflict": (
        "Before and after differ in frame, screen, state, variant or viewport.",
        "La planche, l’écran, l’état, la variante ou les dimensions ont changé.",
    ),
    "after_split_required": (
        "Supply separate design and runtime PNGs for both rounds.",
        "Fournir des PNG séparés pour la maquette et le rendu avant et après.",
    ),
    "after_design_changed": (
        "The design reference image changed.",
        "L’image de référence de la maquette a changé.",
    ),
    "after_image_reused": (
        "Before and after reuse the same runtime image data.",
        "Les captures de rendu avant et après contiennent les mêmes données d’image.",
    ),
    "after_ready": (
        "Same declared frame, reference image and comparison scope, with distinct runtime image data. "
        "Check each follow-up observation against the baseline.",
        "Même planche déclarée, même image de référence et même périmètre. Les données d’image des rendus diffèrent. "
        "Vérifier chaque observation de suivi par rapport à l’état initial.",
    ),
    "follow_up": ("After observation", "Observation après correction"),
    "follow_up_withheld": (
        "After observation withheld",
        "Observation après correction non retenue",
    ),
    "technical": ("Technical details", "Détails techniques"),
    "machine": ("Machine verdict", "Verdict machine"),
    "check": ("check", "check"),
    "open_report": ("Open source report", "Ouvrir le rapport source"),
    "machine_scope": (
        "The diagnostic is linked by the manifest. Its format cannot establish which image or state it measured.",
        "Le diagnostic est associé par le manifeste. Son format ne permet pas d’établir quelle image ou quel état a été mesuré.",
    ),
    "geometry": ("Geometry and placement", "Géométrie et placement"),
    "styles": ("Visual properties", "Propriétés visuelles"),
    "identity": ("Identity and structure", "Identités et structure"),
    "state_coverage": ("Screen and state coverage", "Couverture des écrans et états"),
    "gaps": ("Missing or invalid measurements", "Mesures manquantes ou invalides"),
    "other": ("Other technical findings", "Autres constats techniques"),
}


class _Markdown:
    def __init__(self, locale: str) -> None:
        self.locale_index = int(locale == "fr")

    def label(self, key: str, *params: str) -> str:
        template = _LABELS[key][self.locale_index]
        return template.format(*params)

    def render(self, cases: list[Case]) -> str:
        # Present homology before advice, then retain every raw technical finding
        # below the review summary so repeated codes cannot dominate the first decision.
        lines = [f"# {self.label('report')}", "", self.label("scope_note"), ""]
        for case in cases:
            lines.extend((f"## {_text(case.title)}", "", f"### {self.label('before')}", ""))
            lines.extend(self.pair(case.before))
            if case.after is not None:
                lines.extend((f"### {self.label('after')}", ""))
                lines.extend(self.pair(case.after))
                lines.extend(f"- {self.notice(notice)}" for notice in case.after_notices)
                if not case.after_notices:
                    lines.append(self.label("after_ready"))
                lines.append("")
            lines.extend(self.observations(case))
            for phase, pair in (("before", case.before), ("after", case.after)):
                if pair is not None and pair.report is not None:
                    lines.extend(self.technical(phase, pair.report))
        return "\n".join(lines).rstrip() + "\n"

    def pair(self, pair: Pair) -> list[str]:
        lines = [f"**{self.label(pair.status)}**", ""]
        for side, metadata in (("design", pair.design), ("runtime", pair.runtime)):
            parts = [
                f"{self.label(key)} = {self.meta(metadata, key)}"
                for key in ("screen", "state", "variant", "viewport")
            ]
            if side == "design":
                parts.insert(0, f"{self.label('frame')} = {self.meta(metadata, 'frame')}")
            lines.append(f"- **{self.label(side)}** · " + " · ".join(parts))
        lines.extend(
            f"- {_link(item.path, self.label(item.note))}" for item in pair.images if not item.error
        )
        lines.extend(f"- {self.notice(notice)}" for notice in pair.notices)
        if pair.status != "comparable":
            lines.extend(("", self.label("not_ready")))
        return [*lines, ""]

    def meta(self, data: dict[str, object], key: str) -> str:
        if key == "variant" and key in data and data[key] is None:
            return self.label("default")
        value = data.get(key)
        if isinstance(value, list):
            return f"{value[0]} × {value[1]} px"
        return _text(value) if isinstance(value, str) else self.label("unknown")

    def notice(self, notice: Notice) -> str:
        # Only these arguments denote catalog keys. File names and errors remain text.
        localized = {
            "field_missing": (0, 1),
            "field_conflict": (0,),
            "image_missing": (0,),
            "image_file_missing": (0,),
            "image_invalid": (0, 1),
        }.get(notice.key, ())
        return self.label(
            notice.key,
            *(
                self.label(value) if index in localized else _text(value)
                for index, value in enumerate(notice.params)
            ),
        )

    def observations(self, case: Case) -> list[str]:
        lines = [f"### {self.label('priorities')}", ""]
        qualified = [item for item in case.observations if not item.notices]
        if not qualified:
            lines.extend((self.label("no_priorities"), ""))
        for item in qualified[:MAX_PRIORITIZED]:
            finding = item.finding
            action, basis = self.label(finding["action"]), self.label(finding["basis"])
            if case.before.status != "comparable" and finding["basis"] in ("visual", "measurement"):
                basis += f" · {self.label('provisional')}"
            lines.extend(
                (
                    f"#### {finding['priority']}. {_text(finding['title'])}",
                    "",
                    f"**{action}** · {basis}",
                    "",
                )
            )
            for key in ("region", "expected", "observed", "proposal", "verify"):
                lines.append(f"- **{self.label(key)}** · {_text(finding[key])}")
            lines.extend(self.citations(item.evidence, "evidence"))
            if item.approval is not None:
                lines.extend(self.citations([item.approval], "approval"))
            if "follow_up" in finding:
                if item.follow_up_notices:
                    reasons = " ".join(self.notice(n) for n in item.follow_up_notices)
                    lines.append(f"- **{self.label('follow_up_withheld')}** · {reasons}")
                else:
                    observed = _text(finding["follow_up"]["observed"])
                    lines.append(f"- **{self.label('follow_up')}** · {observed}")
                lines.extend(self.citations(item.follow_up, "evidence"))
            lines.append("")
        if deferred := qualified[MAX_PRIORITIZED:]:
            lines.extend((f"**{self.label('deferred')}**", ""))
            lines.extend(f"- {_text(item.finding['title'])}" for item in deferred)
            lines.append("")
        if withheld := [item for item in case.observations if item.notices]:
            lines.extend((f"**{self.label('withheld')}**", ""))
            for item in withheld:
                reasons = " ".join(self.notice(notice) for notice in item.notices)
                lines.append(f"- {_text(item.finding['title'])} · {reasons}")
                unavailable = [
                    ref for ref in (*item.evidence, item.approval) if ref is not None and ref.error
                ]
                lines.extend(self.citations(unavailable, "evidence"))
            lines.append("")
        return lines

    def citations(self, evidence: list[Evidence], key: str) -> list[str]:
        if not evidence:
            return []
        lines = [f"- **{self.label(key)}**"]
        for item in evidence:
            note = _text(item.note)
            if item.error:
                location = (
                    f"{self.label('unavailable')} · {_text(item.path)} ({self.label(item.error)})"
                )
            else:
                location = _link(item.path, item.path.rsplit("/", 1)[-1])
            if item.pointer is not None:
                location += f" · {_text(item.pointer)}"
            if item.value is not None:
                location += f" = {_text(json.dumps(item.value, ensure_ascii=False))}"
            lines.append(f"  - {note} · {location}")
        return lines

    def technical(self, phase: str, report: MachineReport) -> list[str]:
        groups: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
        for issue in report.issues:
            groups[_family(issue)][issue["code"]].append(issue)
        check = (
            f" · {self.label('check')} {_text(report.check_status)}" if report.check_status else ""
        )
        lines = [
            f"### {self.label('technical')} · {self.label(phase)}",
            "",
            f"**{self.label('machine')}** · {report.status}{check} · {len(report.issues)}",
            "",
            _link(report.source.path, self.label("open_report")),
            "",
            self.label("machine_scope"),
            "",
        ]
        for name, codes in groups.items():
            count = sum(map(len, codes.values()))
            lines.extend(("<details>", f"<summary>{self.label(name)} ({count})</summary>", ""))
            for code, issues in sorted(codes.items()):
                lines.append(f"- **{_text(code)}** ({len(issues)})")
                for issue in issues:
                    fields = (
                        issue.get("outcome"),
                        issue.get("severity"),
                        issue.get("semantic_id"),
                        issue["message"],
                    )
                    lines.append(
                        "  - "
                        + " · ".join(_text(value) for value in fields if isinstance(value, str))
                    )
            lines.extend(("", "</details>", ""))
        return lines


def _family(issue: dict[str, str]) -> str:
    code = issue["code"]
    if issue.get("outcome") in {"NOT_OBSERVED", "MEASUREMENT_ERROR"}:
        return "gaps"
    if code.startswith(("screen.", "rendered.screen.", "rendered.viewport.")):
        return "state_coverage"
    if code.startswith(("node.bbox.", "rendered.overflow.")):
        return "geometry"
    if code.startswith(("node.visual.", "rendered.image.")):
        return "styles"
    return "identity" if code.startswith("node.") else "other"


def _text(value: str) -> str:
    # Escape reviewer text so it cannot open Markdown links or raw HTML blocks.
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~&])", r"\\\1", " ".join(value.split()))


def _link(path: str, label: str) -> str:
    return f"[{_text(label)}]({quote(path, safe='/')})"


def format_review(locale: str, cases: list[Case]) -> str:
    """Return Markdown for the evaluated cases in the selected report language."""
    return _Markdown(locale).render(cases)
