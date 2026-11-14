"""Resolve explicit product convention profiles and audit measured design metrics.

This is a local, deterministic policy consumer. It never infers a product purpose
from prose, launches a renderer, or treats source geometry as a runtime observation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from collections.abc import Iterator

from .compare import _canonical_padding
from .schema_cache import validator_for
from .tree import MAX_ABSOLUTE_OBSERVATION, flatten_nodes

JsonObject = dict[str, Any]
_PROFILE_DATA = Path(__file__).parent / "profiles" / "design-profiles.json"
_LIMIT_KEYS = frozenset({"min", "max", "values"})
_SURFACES = frozenset({"desktop-app", "web-page", "landing", "mobile"})


def validate_profile(config: JsonObject) -> None:
    """Reject unknown fields, nonfinite limits, and contradictory rule definitions.

    Args:
        config: Caller-owned profile selection and explicit product overrides.
    Raises:
        ValueError: The selection or a constraint is invalid.
    """
    errors = sorted(validator_for("design-profile.schema.json").iter_errors(config), key=str)
    if errors:
        raise ValueError(f"profile.schema: {errors[0].message}")
    for size in config.get("typography", {}).get("font_size_scale", []):
        if not 0 < size <= MAX_ABSOLUTE_OBSERVATION or not _number(size):
            raise ValueError(
                "profile.typography.invalid: font sizes must be positive finite numbers"
            )
    for constraint in [*config.get("rules", []), *config.get("overrides", [])]:
        _validate_limits(constraint)
    ids = [rule["id"] for rule in config.get("rules", [])]
    if len(ids) != len(set(ids)):
        raise ValueError("profile.rule.duplicate: custom rule IDs must be unique")
    override_ids = [
        (item["rule"], item["node"], item.get("screen_id")) for item in config.get("overrides", [])
    ]
    if len(override_ids) != len(set(override_ids)):
        raise ValueError("profile.override.duplicate: one override per rule/node/screen")


def resolve_profile(
    config: JsonObject | None,
    *,
    contract: JsonObject | None = None,
    convention_sources: dict[str, bytes] | None = None,
) -> JsonObject | None:
    """Resolve a selection to sourced rules, without reading consumer files.

    Args:
        config: Optional design-profile.json object. Absent selection can resolve
            only from unambiguous explicit contract screen surface metadata.
        contract: Current flow contract; a generic `web` surface is insufficient.
        convention_sources: Already-confined file snapshots, keyed by source path.
            Every source explicitly requested by config must be supplied.
    Returns:
        Detached resolved profile, or None when product purpose is unobserved.
    Raises:
        ValueError: Contradictory/unsupported selection, rules, or missing sources.
    """
    selected = copy.deepcopy(config) if config is not None else _contract_selection(contract)
    if selected is None:
        return None
    validate_profile(selected)
    inferred = _contract_selection(contract)
    if (
        config is not None
        and inferred is not None
        and any(selected[key] != inferred[key] for key in ("surface", "platform"))
    ):
        raise ValueError("profile.selection.conflict: explicit contract surface disagrees")
    raw = _PROFILE_DATA.read_bytes()
    bundled = json.loads(raw)
    key = f"{selected['surface']}:{selected['platform']}"
    if key not in bundled:
        raise ValueError(f"profile.selection.unsupported: {key}")
    rules = copy.deepcopy(bundled[key])
    if selected["platform"] == "web":
        rules = copy.deepcopy(bundled["common-web"]) + rules
    combined = rules + selected.get("rules", [])
    ids = [rule["id"] for rule in combined]
    if len(ids) != len(set(ids)):
        raise ValueError("profile.rule.duplicate: use a reasoned override for a bundled rule")
    _validate_overrides(selected.get("overrides", []), set(ids))
    sources = convention_sources or {}
    missing = set(selected.get("sources", [])) - sources.keys()
    if missing:
        raise ValueError(f"profile.source.missing: {', '.join(sorted(missing))}")
    return {
        **selected,
        "rules": combined,
        "overrides": selected.get("overrides", []),
        "provenance": {
            "snapshot": "penflow/profiles/design-profiles.json",
            "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
            "sources": [
                {"path": path, "sha256": hashlib.sha256(content).hexdigest()}
                for path, content in sorted(sources.items())
            ],
            "scope": "versioned numeric convention snapshot; external source freshness unverified",
        },
    }


def typography_theme_issues(
    profile: JsonObject, theme_font_sizes: tuple[float, ...]
) -> list[JsonObject]:
    """Report theme declarations outside an already validated exact product scale.

    The profile remains authoritative; conflicts never extend its allowlist.
    Source labels explain operator-resolved policy, not Markdown interpretation.
    """
    typography = profile.get("typography")
    if typography is None:
        return []
    allowed = typography["font_size_scale"]
    return [
        {
            "severity": "error",
            "code": "profile.typography.theme_conflict",
            "path": "$.typography.font_size_scale",
            "value": value,
            "allowed_values": list(allowed),
            "source": typography["source"],
            "message": "Theme font size is outside the exact product profile scale",
        }
        for value in theme_font_sizes
        if value not in allowed
    ]


def audit_design_profile(expected: JsonObject, profile: JsonObject | None) -> JsonObject:
    """Audit measurable expected metrics under the selected product policy.

    Args:
        expected: Current source-derived UI tree; never considered runtime proof.
        profile: Resolved profile from resolve_profile, or None.
    Returns:
        Report with scoped observations and PASS, FAIL or NOT_OBSERVED. Missing
        metrics never pass; masks do not disable profile checks. No input changes.
    """
    if profile is None:
        return {
            "status": "NOT_OBSERVED",
            "issues": [],
            "observations": [],
            "limitations": ["Product surface/platform profile is not resolved."],
        }
    observations: list[JsonObject] = []
    used_overrides: set[int] = set()
    issues: list[JsonObject] = []
    for screen in expected.get("screens", []):
        for node in _nodes(screen["root"]):
            if node.get("unresolved_ref"):
                observations.append(
                    {
                        "status": "NOT_OBSERVED",
                        "code": "profile.component.unobserved",
                        "node": node["id"],
                        "screen_id": screen["screen_id"],
                        "message": "Inherited component metrics could not be resolved",
                    }
                )
            for rule in profile["rules"]:
                if not _matches(rule["selector"], node, screen["screen_id"]):
                    continue
                limits, override = _node_limits(rule, node, screen, profile, used_overrides)
                observation = _audit_metric(node, screen["screen_id"], rule, limits)
                if override is not None:
                    observation["override"] = override
                observations.append(observation)
                if observation["status"] == "FAIL":
                    issues.append(
                        {"severity": "error", "code": "profile.metric.out_of_range", **observation}
                    )
    for index, override in enumerate(profile["overrides"]):
        if index not in used_overrides:
            issues.append(
                {
                    "severity": "warning",
                    "code": "profile.override.unmatched",
                    "message": "Override does not match an audited rule/node; scope is unverified.",
                    "override": override,
                }
            )
    status = (
        "FAIL"
        if issues
        else (
            "PASS"
            if observations and all(item["status"] == "PASS" for item in observations)
            else "NOT_OBSERVED"
        )
    )
    return {
        "status": status,
        "issues": issues,
        "observations": observations,
        "profile": {key: profile[key] for key in ("surface", "platform", "provenance")},
        "limitations": [
            "Profile metrics do not establish aesthetic quality or runtime appearance."
        ],
    }


def _contract_selection(contract: JsonObject | None) -> JsonObject | None:
    screens = (contract or {}).get("screens", [])
    if not isinstance(screens, list) or any(not isinstance(screen, dict) for screen in screens):
        return None
    if any(not isinstance(screen.get("surface"), str) for screen in screens):
        return None
    surfaces = {screen["surface"] for screen in screens}
    if len(surfaces) != 1:
        return None
    surface = next(iter(surfaces))
    # Existing contracts permit open surface strings. Only these exact explicit
    # product purposes select a policy; `web` never implies a desktop cockpit.
    if surface in _SURFACES:
        return {"version": 1, "surface": surface, "platform": "web"}
    if surface in {"ios", "android"}:
        return {"version": 1, "surface": "mobile", "platform": surface}
    return None


def _validate_limits(constraint: JsonObject) -> None:
    for key in ("min", "max"):
        if key in constraint and not _number(constraint[key]):
            raise ValueError("profile.limit.invalid: limits must be finite nonnegative numbers")
    if constraint.get("min", 0) > constraint.get("max", math.inf):
        raise ValueError("profile.limit.contradictory: minimum exceeds maximum")
    values = constraint.get("values")
    if values is not None and any(
        not isinstance(value, str) and not _number(value) for value in values
    ):
        raise ValueError("profile.limit.invalid: values must be finite numbers or strings")
    if values is not None and ("min" in constraint or "max" in constraint):
        raise ValueError("profile.limit.contradictory: choose values or range, not both")


def _validate_overrides(overrides: list[JsonObject], ids: set[str]) -> None:
    scopes: dict[tuple[str, str], set[str | None]] = {}
    for override in overrides:
        if override["rule"] not in ids:
            raise ValueError(f"profile.override.unknown_rule: {override['rule']}")
        key = (override["rule"], override["node"])
        screen_id = override.get("screen_id")
        previous = scopes.setdefault(key, set())
        if previous and (screen_id is None or None in previous):
            raise ValueError("profile.override.ambiguous: overlapping scopes")
        previous.add(screen_id)


def _matches(selector: JsonObject, node: JsonObject, screen_id: str) -> bool:
    context = node.get("context", {})
    return all(
        (screen_id if key == "screen_id" else node.get(key, context.get(key))) == value
        for key, value in selector.items()
    )


def _node_limits(
    rule: JsonObject,
    node: JsonObject,
    screen: JsonObject,
    profile: JsonObject,
    used: set[int],
) -> tuple[JsonObject, JsonObject | None]:
    key = node.get("semantic_id") or node["id"]
    for index, override in enumerate(profile["overrides"]):
        if (
            override["rule"] == rule["id"]
            and override["node"] == key
            and ("screen_id" not in override or override["screen_id"] == screen["screen_id"])
        ):
            used.add(index)
            return {name: override[name] for name in _LIMIT_KEYS if name in override}, override
    return {name: rule[name] for name in _LIMIT_KEYS if name in rule}, None


def _audit_metric(
    node: JsonObject, screen_id: str, rule: JsonObject, limits: JsonObject
) -> JsonObject:
    value = _metric(node, rule["property"])
    values = value if isinstance(value, list) else [value]
    observed = bool(values) and all(
        item is not None and not (isinstance(item, str) and item.startswith("$")) for item in values
    )
    status = (
        "NOT_OBSERVED"
        if not observed
        else ("PASS" if all(_within_limits(item, limits) for item in values) else "FAIL")
    )
    return {
        "rule": rule["id"],
        "screen_id": screen_id,
        "semantic_id": node.get("semantic_id") or node["id"],
        "property": rule["property"],
        "value": value,
        "limits": limits,
        "source": rule["source"],
        "status": status,
    }


def _metric(node: JsonObject, property_name: str) -> Any:
    visual = node.get("visual", {})
    if property_name in {"paddingHorizontal", "paddingVertical"}:
        padding = _canonical_padding(visual.get("padding"))
        return (
            None
            if padding is None
            else (
                [padding[1], padding[3]]
                if property_name == "paddingHorizontal"
                else [padding[0], padding[2]]
            )
        )
    if property_name == "aspectRatio":
        bbox = node.get("bbox", {})
        width, height = bbox.get("width"), bbox.get("height")
        return width / height if _number(width) and _number(height) and height > 0 else None
    if property_name == "lineHeightRatio":
        return _line_height(node, ratio=True)
    group, key = property_name.split(".")
    value = node.get(group, {}).get(key)
    if group == "bbox" and (not _number(value) or value == 0):
        return None
    if property_name == "visual.lineHeight":
        return _line_height(node, ratio=False)
    if group == "visual" and key.startswith("font"):
        return _typography(node, key)
    return value


def _line_height(node: JsonObject, *, ratio: bool) -> float | None:
    height = _typography(node, "lineHeight")
    size = _typography(node, "fontSize")
    unit = _typography(node, "lineHeightUnit")
    if not _number(height) or not _number(size) or size <= 0:
        return None
    # A unitless Pencil value is ambiguous: never guess whether it means a
    # multiplier or logical pixels from its magnitude.
    if unit == "px":
        return height / size if ratio else float(height)
    if unit == "multiplier":
        return float(height) if ratio else height * size
    return None


def _nodes(root: JsonObject) -> Iterator[JsonObject]:
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.get("children", [])))


def _typography(node: JsonObject, key: str) -> Any:
    value = node.get("visual", {}).get(key)
    if value is not None:
        return value
    # Button labels commonly own typography. Resolve only a unique descendant
    # value: mixed labels are ambiguous and must remain explicitly unobserved.
    values = {
        child.get("visual", {}).get(key)
        for child in flatten_nodes(node)[1:]
        if child.get("role") in {"text", "heading"} and child.get("visual", {}).get(key) is not None
    }
    return next(iter(values)) if len(values) == 1 else None


def _within_limits(value: Any, limits: JsonObject) -> bool:
    if "values" in limits:
        return value in limits["values"]
    return _number(value) and limits.get("min", 0) <= value <= limits.get("max", math.inf)


def _number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )
