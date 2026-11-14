"""Compare independently captured rendered measurements through the existing tree engine.

JSON observations cross this pure boundary; no browser, renderer, or app is executed.
Measurement metadata declares a producer's method, not an authentication certificate.
"""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any

from .compare import DEFAULT_TOLERANCE, compare_trees
from .tree import flatten_nodes, normalize_actual_tree, validate_actual_tree
from .verification_geometry import normalize_native_geometry
from .verification_styles import normalize_observed_styles

# Heterogeneous C12 JSON is validated at entry before traversing domain fields.
JsonObject = dict[str, Any]
# One logical pixel covers layout rounding; font mismatch remains visible below 1px.
RENDERED_TOLERANCE = {"bbox_px": 1, "font_px": 0.5, "spacing_px": 1}
RATIO_TOLERANCE = 0.02  # Two percent tolerates rounding, not visibly stretched imagery.
KNOWN_UNITS = frozenset({"css-px", "logical-px", "physical-px"})
KNOWN_COORDINATES = frozenset({"screen-relative", "parent-relative"})


def compare_rendered(
    expected: JsonObject,
    actual: JsonObject | None,
    *,
    design_layout: JsonObject | None = None,
) -> JsonObject:
    """Compare measured geometry/styles with current source and optional native layout.

    Args:
        expected: Current source-derived expected tree, never an actual-tree template.
        actual: Externally captured C12 tree with explicit measurement metadata.
        design_layout: Optional native parent-relative children resolving fill/hug geometry.

    Returns:
        One of CONFORMING, MATERIAL_DRIFT, MEASUREMENT_ERROR, NOT_OBSERVED, plus
        scoped findings and observation coverage. Inputs are never mutated.
    """
    if actual is None or (isinstance(actual, dict) and "measurement" not in actual):
        return _report(
            [
                _issue(
                    "NOT_OBSERVED",
                    "rendered.measurement.missing",
                    None,
                    "Runtime measurement metadata was not supplied",
                )
            ],
            [],
            0,
        )
    if not isinstance(actual, dict) or not isinstance(actual.get("measurement"), dict):
        return _report(
            [
                _issue(
                    "MEASUREMENT_ERROR",
                    "rendered.measurement.invalid",
                    None,
                    "Runtime measurement metadata must be an object",
                )
            ],
            [],
            0,
        )
    expected_copy, actual_copy = deepcopy(expected), normalize_actual_tree(deepcopy(actual))
    # Reusable library definitions are audited as design inputs, not runtime screens.
    expected_copy["screens"] = [
        screen
        for screen in expected_copy.get("screens", [])
        if not screen.get("root", {}).get("component_template")
    ]
    issues = _schema_issues(expected_copy, actual_copy)
    if issues:
        return _report(issues, [], 0)
    metadata = actual_copy["measurement"]
    issues.extend(_measurement_issues(metadata))
    if actual_copy.get("source") and actual_copy.get("source") == expected_copy.get("source"):
        issues.append(
            _issue(
                "MEASUREMENT_ERROR",
                "rendered.source.design_derived",
                None,
                "Actual declares the same source document as the design-derived expected tree",
            )
        )
    if any(issue["outcome"] == "MEASUREMENT_ERROR" for issue in issues):
        return _report(issues, [], 0)
    _normalize_actual(actual_copy, metadata)
    layout_resolved = False
    if design_layout is not None:
        try:
            if design_layout.get("coordinate_space", "parent-relative") != "parent-relative":
                raise ValueError("Design layout must use parent-relative logical coordinates")
            source_sha = expected_copy.get("source_sha256")
            layout_sha = design_layout.get("source_sha256")
            if not source_sha or not layout_sha:
                issues.append(
                    _issue(
                        "NOT_OBSERVED",
                        "rendered.design_layout.unbound",
                        None,
                        "Native layout must identify the current source_sha256",
                    )
                )
            elif source_sha != layout_sha:
                raise ValueError("Native layout source_sha256 differs from the current design")
            else:
                # Normalize a private candidate: a partial invalid layout must not mutate source geometry.
                resolved = deepcopy(expected_copy)
                normalize_native_geometry(resolved, design_layout["children"])
                _validate_fixed_layout(expected_copy, resolved)
                expected_copy = resolved
                layout_resolved = True
        except (ValueError, KeyError, TypeError) as error:
            issues.append(
                _issue("MEASUREMENT_ERROR", "rendered.design_layout.invalid", None, str(error))
            )
    issues.extend(_prepare_source(expected_copy, layout_resolved))
    try:
        normalize_observed_styles(expected_copy)
        normalize_observed_styles(actual_copy)
    except ValueError as error:
        issues.append(_issue("MEASUREMENT_ERROR", "rendered.style.contradictory", None, str(error)))
        return _report(issues, [], 0)
    comparisons = []
    observed_designs = set()
    groups: dict[str, tuple[JsonObject, list[JsonObject], list[JsonObject]]] = {}
    for capture in actual_copy["screens"]:
        design, selection_issues = _select_design(expected_copy["screens"], capture)
        issues.extend(selection_issues)
        if design is None:
            continue
        design_key = design.get("pencil_id") or design["screen_id"]
        observed_designs.add(design_key)
        viewport_issues = _viewport_issues(
            design, capture, metadata, expected_copy.get("measurement", {})
        )
        issues.extend(viewport_issues)
        projected = deepcopy(capture)
        projected["screen_id"] = design["screen_id"]
        # Skip geometry only for this invalid viewport; other states retain their checks.
        projected["_geometry_unobserved"] = bool(viewport_issues)
        if design_key not in groups:
            groups[design_key] = (design, [], [])
        groups[design_key][1].append(projected)
        groups[design_key][2].extend(_project_witnesses(actual_copy, capture, design["screen_id"]))
        issues.extend(_image_issues(capture))
        issues.extend(_overflow_observations(capture))
    # State and fact coverage is evaluated once across all captures of one physical design.
    # Comparing single captures would falsely report the other observed states as missing.
    for design, captures, witnesses in groups.values():
        result = compare_trees(
            {"version": 1, "screens": [design]},
            {**actual_copy, "screens": captures, "observed_states": witnesses},
            rendered=True,
        )
        comparisons.append(result)
        issues.extend(_comparison_issues(result))
    for screen in expected_copy["screens"]:
        if (screen.get("pencil_id") or screen["screen_id"]) not in observed_designs:
            issues.append(
                _issue(
                    "NOT_OBSERVED",
                    "rendered.screen.unobserved",
                    screen["screen_id"],
                    "No runtime capture selects this design screen",
                )
            )
    return _report(issues, comparisons, len(observed_designs))


def _project_witnesses(actual: JsonObject, capture: JsonObject, design_id: str) -> list[JsonObject]:
    """Preserve matching state/fact witnesses while translating explicit screen identity."""
    keys = ("screen_id", "state", "scenario_id", "facts")
    return [
        {**witness, "screen_id": design_id}
        for witness in actual.get("observed_states", [])
        if all(witness.get(key) == capture.get(key) for key in keys)
    ]


def _validate_fixed_layout(source: JsonObject, resolved: JsonObject) -> None:
    """Refuse native bounds contradicting explicit source dimension constraints."""
    resolved_nodes = {
        node.get("pencil_id"): node
        for screen in resolved["screens"]
        for node in flatten_nodes(screen["root"])
    }
    for screen in source["screens"]:
        for node in flatten_nodes(screen["root"]):
            sizing = node.get("sizing", {})
            for axis in ("width", "height"):
                intrinsic = node.get("source_type") == "text" and (
                    node.get("text_growth") == "auto"
                    or (axis == "height" and node.get("text_growth") == "fixed-width")
                )
                if intrinsic or sizing.get(axis, "fixed") != "fixed":
                    continue
                measured = resolved_nodes[node.get("pencil_id")]["bbox"][axis]
                if abs(node["bbox"][axis] - measured) > RENDERED_TOLERANCE["bbox_px"]:
                    raise ValueError(f"Native layout contradicts fixed {axis} of {node['id']}")


def _overflow_observations(capture: JsonObject) -> list[JsonObject]:
    """Keep observed clipping/scrolling visible without guessing product intent."""
    issues = []
    for node in flatten_nodes(capture["root"]):
        observed = node.get("observed", {})
        if not isinstance(observed, dict):
            issues.append(
                _issue(
                    "MEASUREMENT_ERROR",
                    "rendered.overflow.invalid",
                    node["id"],
                    "Observed overflow fields must be an object",
                )
            )
            continue
        for axis in ("overflow_x", "overflow_y"):
            if axis in observed and not isinstance(observed[axis], bool):
                issues.append(
                    _issue(
                        "MEASUREMENT_ERROR",
                        "rendered.overflow.invalid",
                        node["id"],
                        "Observed overflow flags must be boolean",
                    )
                )
            elif observed.get(axis):
                issues.append(
                    _issue(
                        "NOT_OBSERVED",
                        "rendered.overflow.review_required",
                        node["id"],
                        f"Observed {axis}; intentional scrolling versus clipping requires review",
                    )
                )
    return issues


def _schema_issues(expected: JsonObject, actual: JsonObject) -> list[JsonObject]:
    # Candidate revisions can share a logical screen: validate physical regions separately,
    # then let the explicit runtime selector choose one. Actual identity stays strict.
    expected_inputs = [expected]
    if isinstance(expected.get("screens"), list):
        expected_inputs = [{**expected, "screens": [screen]} for screen in expected["screens"]]
    inputs = [("expected", tree) for tree in expected_inputs] + [("actual", actual)]
    return [
        _issue(
            "MEASUREMENT_ERROR",
            "rendered." + label + ".invalid",
            issue.get("path"),
            issue["message"],
        )
        for label, tree in inputs
        for issue in validate_actual_tree(tree)
    ]


def _positive(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and abs(value) <= 1e12
        and isfinite(value)
        and value > 0
    )


def _measurement_issues(metadata: JsonObject) -> list[JsonObject]:
    checks = {
        "source": metadata.get("source") == "runtime",
        "units": isinstance(metadata.get("units"), str) and metadata["units"] in KNOWN_UNITS,
        "coordinate_space": isinstance(metadata.get("coordinate_space"), str)
        and metadata["coordinate_space"] in KNOWN_COORDINATES,
        "zoom": _positive(metadata.get("zoom")),
        "device_pixel_ratio": _positive(metadata.get("device_pixel_ratio")),
        "method": isinstance(metadata.get("method"), str) and bool(metadata["method"].strip()),
    }
    return [
        _issue(
            "MEASUREMENT_ERROR",
            "rendered.measurement." + key,
            None,
            f"Invalid or missing runtime measurement {key}",
        )
        for key, valid in checks.items()
        if not valid
    ]


def _normalize_actual(tree: JsonObject, metadata: JsonObject) -> None:
    divisor = metadata["device_pixel_ratio"] if metadata["units"] == "physical-px" else 1
    for screen in tree["screens"]:
        if isinstance(screen.get("viewport"), dict):
            screen["viewport"] = {
                key: value / divisor
                for key, value in screen["viewport"].items()
                if key in {"x", "y", "width", "height"}
            }
        _normalize_node(screen["root"], divisor, metadata["coordinate_space"], 0, 0, True)


def _normalize_node(
    node: JsonObject, divisor: float, coordinates: str, parent_x: float, parent_y: float, root: bool
) -> None:
    box = {
        key: value / divisor
        for key, value in node["bbox"].items()
        if key in {"x", "y", "width", "height"}
    }
    if coordinates == "parent-relative":
        box["x"] += parent_x
        box["y"] += parent_y
    node["bbox"] = box
    visual = node.get("visual", {})
    for key in (
        "fontSize",
        "lineHeight",
        "iconSize",
        "cornerRadius",
        "gap",
        "padding",
        "strokeWidth",
        "strokeThickness",
    ):
        if key in visual:
            visual[key] = _scale_length(visual[key], divisor)
    if isinstance(visual.get("stroke"), dict) and "thickness" in visual["stroke"]:
        visual["stroke"]["thickness"] /= divisor
    for child in node.get("children", []):
        _normalize_node(child, divisor, coordinates, box["x"], box["y"], False)


def _scale_length(value: Any, divisor: float) -> Any:
    """Scale scalar, per-edge and array length representations, preserving aliases."""
    if isinstance(value, list):
        return [item / divisor for item in value]
    if isinstance(value, dict):
        return {key: item / divisor for key, item in value.items()}
    return value / divisor


def _prepare_source(tree: JsonObject, layout_resolved: bool) -> list[JsonObject]:
    issues = []
    for screen in tree["screens"]:
        pending = [(screen["root"], 0.0, 0.0, False, True)]
        while pending:
            node, parent_x, parent_y, flow, is_root = pending.pop()
            if node.get("unresolved_ref"):
                issues.append(
                    _issue(
                        "NOT_OBSERVED",
                        "rendered.component.unobserved",
                        node["id"],
                        "Inherited component geometry and styles are unresolved",
                    )
                )
            issues.extend(_resolve_line_height(node))
            if node.get("source_type") == "frame":
                node.setdefault("visual", {}).setdefault("layout", "horizontal")
            context = node.setdefault("context", {})
            has_override = isinstance(context.get("override_reason"), str) and bool(
                context["override_reason"].strip()
            )
            if (
                context.get("mask") or context.get("mask_text") or context.get("tolerance")
            ) and not has_override:
                issues.append(
                    _issue(
                        "MEASUREMENT_ERROR",
                        "rendered.override.unjustified",
                        node["id"],
                        "Masks and tolerance overrides require override_reason",
                    )
                )
            custom_tolerance = context.get("tolerance", {}) if has_override else {}
            baseline = DEFAULT_TOLERANCE | RENDERED_TOLERANCE
            oversized = [
                key
                for key, value in custom_tolerance.items()
                if key != "color" and value > baseline[key]
            ]
            if oversized:
                issues.append(
                    _issue(
                        "MEASUREMENT_ERROR",
                        "rendered.tolerance.enlarged",
                        node["id"],
                        "Rendered tolerance cannot exceed measured baseline: "
                        + ", ".join(oversized),
                    )
                )
                custom_tolerance = {}
            elif custom_tolerance:
                issues.append(
                    _issue(
                        "CONFORMING",
                        "rendered.tolerance.applied",
                        node["id"],
                        "Bounded tolerance "
                        + str(custom_tolerance)
                        + "; reason: "
                        + context["override_reason"],
                    )
                )
            if has_override and (context.get("mask") or context.get("mask_text")):
                issues.append(
                    _issue(
                        "NOT_OBSERVED",
                        "rendered.mask.unobserved",
                        node["id"],
                        "Masked runtime scope remains unverified; reason: "
                        + context["override_reason"],
                    )
                )
            context["tolerance"] = RENDERED_TOLERANCE | custom_tolerance
            box = node["bbox"]
            if not layout_resolved:
                box["x"] = 0 if is_root else parent_x + box["x"]
                box["y"] = 0 if is_root else parent_y + box["y"]
                sizing = dict(node.get("sizing", {}))
                # Native auto text ignores authored dimensions in its growth axes.
                growth = node.get("text_growth")
                if node.get("source_type") == "text" and growth in {"auto", "fixed-width"}:
                    sizing["height"] = "hug"
                    if growth == "auto":
                        sizing["width"] = "hug"
                unobserved = [
                    axis for axis in ("width", "height") if sizing.get(axis, "fixed") != "fixed"
                ]
                if flow:
                    unobserved.extend(("x", "y"))
                node["_unobserved_axes"] = unobserved
                if unobserved:
                    issues.append(
                        _issue(
                            "NOT_OBSERVED",
                            "rendered.design_geometry.unobserved",
                            node["id"],
                            "Native layout is needed for " + ", ".join(unobserved),
                        )
                    )
            native_layout = "horizontal" if node.get("source_type") == "frame" else None
            child_flow = flow or node.get("visual", {}).get("layout", native_layout) in {
                "vertical",
                "horizontal",
            }
            pending.extend(
                (child, box["x"], box["y"], child_flow, False) for child in node.get("children", [])
            )
    return issues


def _resolve_line_height(node: JsonObject) -> list[JsonObject]:
    visual = node.get("visual", {})
    unit = visual.pop("lineHeightUnit", None)
    if "lineHeight" not in visual:
        return []
    if unit == "px":
        return []
    if unit == "multiplier" and _positive(visual.get("fontSize")):
        visual["lineHeight"] *= visual["fontSize"]
        return []
    # Native format versions differ. Missing units must not turn a multiplier into pixels.
    visual.pop("lineHeight")
    return [
        _issue(
            "NOT_OBSERVED",
            "rendered.line_height.unit_unobserved",
            node["id"],
            "Design line height requires lineHeightUnit px or multiplier with fontSize",
        )
    ]


def _select_design(
    screens: list[JsonObject], capture: JsonObject
) -> tuple[JsonObject | None, list[JsonObject]]:
    selected_id = capture.get("design_screen_id")
    candidates = [
        screen
        for screen in screens
        if (
            screen.get("pencil_id") == selected_id
            if selected_id is not None
            else screen["screen_id"] == capture["screen_id"]
        )
    ]
    if capture.get("variant") is not None:
        candidates = [
            screen for screen in candidates if screen.get("variant") == capture["variant"]
        ]
    if len(candidates) != 1:
        return None, [
            _issue(
                "MEASUREMENT_ERROR",
                "rendered.screen.ambiguous",
                capture["screen_id"],
                "Capture must select exactly one design screen/revision/variant",
            )
        ]
    return candidates[0], []


def _viewport_issues(
    design: JsonObject, capture: JsonObject, metadata: JsonObject, design_metadata: JsonObject
) -> list[JsonObject]:
    issues = []
    root_box = capture["root"]["bbox"]
    if root_box["x"] != 0 or root_box["y"] != 0:
        issues.append(
            _issue(
                "MEASUREMENT_ERROR",
                "rendered.viewport.origin",
                capture["screen_id"],
                "Screen-relative measurements must subtract the observed screen origin",
            )
        )
    for axis in ("width", "height"):
        expected = design.get("viewport", {}).get(axis)
        observed = capture.get("viewport", {}).get(axis)
        outcome = "NOT_OBSERVED" if expected is None or observed is None else "MEASUREMENT_ERROR"
        if not _positive(expected) or not _positive(observed) or abs(expected - observed) > 1:
            issues.append(
                _issue(
                    outcome,
                    "rendered.viewport." + axis,
                    capture["screen_id"],
                    f"Design/runtime viewport {axis} must match in logical pixels",
                )
            )
    if metadata["zoom"] != design_metadata.get("zoom", 1):
        issues.append(
            _issue(
                "MEASUREMENT_ERROR",
                "rendered.viewport.zoom",
                capture["screen_id"],
                "Design and runtime logical zoom must match",
            )
        )
    return issues


def _comparison_issues(result: JsonObject) -> list[JsonObject]:
    return [
        _issue(
            "NOT_OBSERVED"
            if issue["code"].endswith(".missing") and issue["code"].startswith("node.visual")
            else "MATERIAL_DRIFT",
            issue["code"],
            issue.get("semantic_id"),
            issue["message"],
        )
        for issue in result["issues"]
    ]


def _image_issues(capture: JsonObject) -> list[JsonObject]:
    issues = []
    for node in flatten_nodes(capture["root"]):
        if node.get("role") != "image":
            continue
        image = node.get("image", {})
        if not isinstance(image, dict):
            issues.append(
                _issue(
                    "MEASUREMENT_ERROR",
                    "rendered.image.invalid",
                    node["id"],
                    "Image measurement must be an object",
                )
            )
            continue
        width, height = image.get("natural_width"), image.get("natural_height")
        fit = image.get("object_fit")
        if (
            not _positive(width)
            or not _positive(height)
            or not isinstance(fit, str)
            or fit not in {"fill", "contain", "cover", "none", "scale-down"}
        ):
            issues.append(
                _issue(
                    "NOT_OBSERVED",
                    "rendered.image.intrinsic_unobserved",
                    node["id"],
                    "Image intrinsic dimensions and object fit were not observed",
                )
            )
            continue
        width, height = float(image["natural_width"]), float(image["natural_height"])
        declared_fit = node.get("visual", {}).get("objectFit")
        if declared_fit is not None and declared_fit != fit:
            issues.append(
                _issue(
                    "MEASUREMENT_ERROR",
                    "rendered.image.contradictory",
                    node["id"],
                    "Image object-fit observations disagree",
                )
            )
        box = node["bbox"]
        if (
            fit == "fill"
            and box["height"] > 0
            and abs((box["width"] / box["height"]) / (width / height) - 1) > RATIO_TOLERANCE
        ):
            issues.append(
                _issue(
                    "MATERIAL_DRIFT",
                    "rendered.image.distorted",
                    node["id"],
                    "Rendered fill stretches the intrinsic image proportions",
                )
            )
    return issues


def _issue(outcome: str, code: str, identity: str | None, message: str) -> JsonObject:
    return {
        "outcome": outcome,
        "severity": "error" if outcome in {"MEASUREMENT_ERROR", "MATERIAL_DRIFT"} else "info",
        "code": code,
        "semantic_id": identity,
        "message": message,
    }


def _report(issues: list[JsonObject], comparisons: list[JsonObject], screens: int) -> JsonObject:
    outcomes = {issue["outcome"] for issue in issues}
    status = next(
        (
            status
            for status in ("MEASUREMENT_ERROR", "MATERIAL_DRIFT", "NOT_OBSERVED")
            if status in outcomes
        ),
        "CONFORMING",
    )
    return {
        "status": status,
        "issues": issues,
        "comparisons": comparisons,
        "coverage": {"observed_design_screens": screens},
        "limitations": [
            "Producer metadata describes capture; it does not authenticate execution, freshness or build identity."
        ],
    }
