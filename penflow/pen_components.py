"""Expand bounded local native .pen component instances for read-only diagnostics.

Native semantics follow https://docs.pen.dev/for-developers/the-pen-format:
property overrides replace properties; a descendant override containing ``type``
replaces that whole node. Imported component files are never opened here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

JsonObject = dict[str, Any]
# Safety bounds cap adversarial expansion, rather than prescribing product size.
DEFAULT_MAX_NODES = 100_000
DEFAULT_MAX_DEPTH = 128


def resolve_pen_components(
    pen: JsonObject,
    *,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> tuple[JsonObject, list[JsonObject]]:
    """Resolve local refs into a detached diagnostic document and scoped issues.

    Args:
        pen: Current parsed document. Its bytes and object graph remain untouched.
        max_nodes: Maximum expansion visits, including recursively reused nodes.
            Remaining explicit source branches become nonrecursive placeholders.
        max_depth: Maximum source/expanded nesting and reference-chain depth.
    Returns:
        Resolved document and findings. Invalid reference branches retain their
        explicit properties and ``unresolved_ref``; other branches still resolve.
        Inherited IDs use native instance/descendant paths. Semantic contexts are
        preserved verbatim, never invented or deduplicated.
    Raises:
        ValueError: Input is not a document or safety bounds are invalid.
    """
    if not isinstance(pen, dict) or not isinstance(pen.get("children"), list):
        raise ValueError("component.document.invalid: children must be an array")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (max_nodes, max_depth)
    ):
        raise ValueError("component.limit.invalid: bounds must be positive integers")
    state = _Resolution(max_nodes=max_nodes, max_depth=max_depth)
    state.index_document(pen["children"])
    document = {key: deepcopy(value) for key, value in pen.items() if key != "children"}
    document["children"] = [
        state.expand(node) for node in pen["children"] if isinstance(node, dict)
    ]
    return document, state.issues


@dataclass
class _Resolution:
    max_nodes: int
    max_depth: int
    index: dict[str, JsonObject] = field(default_factory=dict)
    duplicates: set[str] = field(default_factory=set)
    issues: list[JsonObject] = field(default_factory=list)
    emitted: int = 0

    def issue(self, code: str, node: JsonObject, message: str, *, external: bool = False) -> None:
        self.issues.append(
            {
                "severity": "info" if external else "error",
                "code": code,
                "node_id": node.get("id"),
                "ref": node.get("ref"),
                "message": message,
                "outcome": "NOT_OBSERVED" if external else "MEASUREMENT_ERROR",
            }
        )

    def index_document(self, children: list[Any]) -> None:
        pending = [(child, 0) for child in reversed(children)]
        visited = 0
        while pending:
            node, depth = pending.pop()
            if not isinstance(node, dict):
                continue
            visited += 1
            if depth > self.max_depth or visited > self.max_nodes:
                self.issue("component.source.limit", node, "Source indexing safety bound exceeded")
                return
            identity = node.get("id")
            if isinstance(identity, str):
                if identity in self.index:
                    self.duplicates.add(identity)
                    self.issue("component.id.duplicate", node, "Duplicate source ID is ambiguous")
                else:
                    self.index[identity] = node
            children = node.get("children", [])
            if isinstance(children, list):
                pending.extend((child, depth + 1) for child in reversed(children))

    def expand(
        self,
        node: JsonObject,
        prefix: str = "",
        stack: tuple[str, ...] = (),
        depth: int = 0,
        *,
        root_id: str | None = None,
        inherited: bool = False,
    ) -> JsonObject:
        identity = root_id if root_id is not None else str(node.get("id", ""))
        physical_id = f"{prefix}/{identity}" if prefix else identity
        if depth > self.max_depth or self.emitted >= self.max_nodes:
            self.issue(
                "component.expansion.limit", node, "Component expansion safety bound exceeded"
            )
            return self.unresolved(node, physical_id, "expansion-limit")
        self.emitted += 1
        if node.get("type") == "ref":
            return self.expand_ref(node, physical_id, prefix, stack, depth)
        result = {key: deepcopy(value) for key, value in node.items() if key != "children"}
        result["id"] = physical_id
        if inherited:
            result.pop("reusable", None)
        child_prefix = physical_id if inherited else prefix
        if "children" in node:
            result["children"] = self.children(node["children"], child_prefix, stack, depth)
        return result

    def children(
        self, children: Any, prefix: str, stack: tuple[str, ...], depth: int
    ) -> list[JsonObject]:
        if not isinstance(children, list):
            self.issue("component.children.invalid", {}, "Component children must be an array")
            return []
        return [
            self.expand(child, prefix, stack, depth + 1)
            for child in children
            if isinstance(child, dict)
        ]

    def expand_ref(
        self, node: JsonObject, physical_id: str, prefix: str, stack: tuple[str, ...], depth: int
    ) -> JsonObject:
        reference = node.get("ref")
        if not isinstance(reference, str) or reference not in self.index:
            external = isinstance(reference, str) and ":" in reference
            self.issue(
                "component.ref.external_not_observed" if external else "component.ref.missing",
                node,
                "Only existing local reusable components can be resolved",
                external=external,
            )
            return self.unresolved(node, physical_id, "external" if external else "missing")
        if (
            reference in self.duplicates
            or reference in stack
            or self.index[reference].get("reusable") is not True
        ):
            reason = (
                "duplicate"
                if reference in self.duplicates
                else "cycle"
                if reference in stack
                else "not_reusable"
            )
            self.issue(
                f"component.ref.{reason}",
                node,
                "Local component reference cannot resolve unambiguously",
            )
            return self.unresolved(node, physical_id, reason)
        # Resolve the template first; instance properties and descendant overrides
        # then take precedence without changing the caller's source document.
        result = self.expand(
            self.index[reference],
            prefix,
            (*stack, reference),
            depth + 1,
            root_id=physical_id.removeprefix(f"{prefix}/") if prefix else physical_id,
            inherited=True,
        )
        result.pop("reusable", None)
        for key, value in node.items():
            if key not in {"id", "type", "ref", "children", "descendants"}:
                result[key] = deepcopy(value)
        if "children" in node:
            result["children"] = self.children(
                node["children"], physical_id, (*stack, reference), depth
            )
        self.apply_overrides(
            result, node.get("descendants", {}), physical_id, (*stack, reference), depth
        )
        return result

    def apply_overrides(
        self, root: JsonObject, overrides: Any, instance_id: str, stack: tuple[str, ...], depth: int
    ) -> None:
        if not isinstance(overrides, dict):
            self.issue(
                "component.overrides.invalid", root, "Descendant overrides must be an object"
            )
            root["unresolved_ref"] = "invalid-overrides"
            return
        # Parent replacements precede deeper paths so a replacement's actual
        # descendants, rather than discarded template descendants, are updated.
        for path, patch in sorted(overrides.items(), key=lambda item: str(item[0]).count("/")):
            if not isinstance(path, str) or not isinstance(patch, dict):
                self.issue(
                    "component.override.invalid", root, "Override path and properties are invalid"
                )
                root["unresolved_ref"] = "invalid-override"
                continue
            target_id = f"{instance_id}/{path}"
            location = self.find_child(root, target_id)
            if location is None:
                self.issue(
                    "component.override.unmatched", root, f"Descendant path was not found: {path}"
                )
                root["unresolved_ref"] = "unmatched-override"
                continue
            parent, index = location
            target = parent["children"][index]
            target_prefix = target_id.rsplit("/", 1)[0]
            if "type" in patch:
                if not isinstance(patch.get("id"), str):
                    self.issue(
                        "component.override.replacement_invalid",
                        root,
                        "Replacement requires its own ID",
                    )
                    target["unresolved_ref"] = "invalid-replacement"
                    continue
                parent["children"][index] = self.expand(patch, target_prefix, stack, depth + 1)
            else:
                if "id" in patch:
                    self.issue(
                        "component.override.identity_unsupported",
                        root,
                        "Changing identity requires a typed replacement",
                    )
                    target["unresolved_ref"] = "identity-override"
                    continue
                for key, value in patch.items():
                    if key != "children":
                        target[key] = deepcopy(value)
                if "children" in patch:
                    target["children"] = self.children(
                        patch["children"], target_prefix, stack, depth
                    )

    @staticmethod
    def find_child(root: JsonObject, identity: str) -> tuple[JsonObject, int] | None:
        pending = [root]
        while pending:
            parent = pending.pop()
            for index, child in enumerate(parent.get("children", [])):
                if child.get("id") == identity:
                    return parent, index
                pending.append(child)
        return None

    @staticmethod
    def unresolved(node: JsonObject, identity: str, reason: str) -> JsonObject:
        # Keep explicit metrics useful to independent checks while refusing to
        # fabricate inherited geometry or an unbounded unresolved subtree.
        result = {
            key: deepcopy(value)
            for key, value in node.items()
            if key not in {"children", "descendants"}
        }
        result.update(id=identity, unresolved_ref=reason)
        return result
