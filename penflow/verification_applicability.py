"""Derive explicit design duties from reviewed workflow bytes and inherited authority."""

from typing import Any

import yaml

from .verification_authority import read_brainstorm_authority
from .verification_files import InputReader, VerificationInputError
from .verification_schema import schema_issues

DECISIONS = ("generated_docs", "native_geometry", "homologous_references", "native_export")


def workflow_decisions(text: str, *, inherited: bool) -> dict[str, Any]:
    """Read the closed current mode from actual workflow frontmatter, never from C20."""
    metadata = _workflow_metadata(text)
    modes = metadata.get("penflow_verification_policy") if isinstance(metadata, dict) else None
    mode = "brainstorm_handoff" if inherited else "livespec"
    if (
        not isinstance(modes, dict)
        or set(modes) - {"livespec", "brainstorm_handoff"}
        or mode not in modes
    ):
        raise VerificationInputError("verification.policy.workflow_mode_missing")
    if any(schema_issues(value, "verification-policy") for value in modes.values()):
        raise VerificationInputError("verification.policy.workflow_decisions_invalid")
    return dict(modes[mode])


def read_policy_source(
    reader: InputReader,
    reference: dict[str, str],
    *,
    brainstorm: bool = False,
    current: bool = False,
) -> dict[str, Any]:
    """Bind workflow, inherited procedure and exact explicit decisions to reviewed bytes."""
    source = reader.object(reader.reference(reference), "verification-policy-source")
    inherited = source["inherited_authority"]
    pointer = ".specs/penflow-brainstorm-authority.json"
    if current and reader.lexists(pointer):
        declared = reader.object(reader.read(pointer), "file")
        if declared != inherited:
            raise VerificationInputError("verification.policy.inherited_authority_omitted")
    workflow = reader.reference(source["workflow"]).decode("utf-8")
    decisions = workflow_decisions(workflow, inherited=brainstorm or inherited is not None)
    if inherited is not None:
        original = read_brainstorm_authority(reader, inherited)["contract"].get(
            "verification_policy"
        )
        if schema_issues(original, "verification-policy"):
            raise VerificationInputError("verification.policy.inherited_decisions_missing")
        for key in DECISIONS:
            if original[key] == "required":
                decisions[key] = "required"
    if source["decisions"] != decisions:
        raise VerificationInputError("verification.policy.workflow_decisions_mismatch")
    return source


def validate_plan_policy(
    reader: InputReader, snapshot: dict[str, Any], source: dict[str, Any]
) -> None:
    """Keep required duties from every active plan in the reviewed workflow union."""
    retired = set(snapshot["retired_features"])
    texts = [
        reader.reference(record["reviewed_snapshot"], archive="source").decode("utf-8")
        for record in snapshot["inputs"]["plans"]
        if record["path"].split("/")[-2] not in retired
    ]
    declared = ["penflow_verification_policy" in _workflow_metadata(text) for text in texts]
    if not any(declared):
        return
    if not all(declared):
        raise VerificationInputError("verification.policy.partial_active_plan_metadata")
    inherited = source["inherited_authority"] is not None
    policies = [workflow_decisions(text, inherited=inherited) for text in texts]
    union = {
        "version": 1,
        **{
            key: "required"
            if any(policy[key] == "required" for policy in policies)
            else "not_applicable"
            for key in DECISIONS
        },
    }
    workflow = workflow_decisions(
        reader.reference(source["workflow"]).decode("utf-8"), inherited=inherited
    )
    if workflow != union:
        raise VerificationInputError("verification.policy.active_plan_union_mismatch")


def _frontmatter_boundary(line: str) -> bool:
    value = line.strip()
    return len(value) >= 3 and set(value) == {"-"}


def _workflow_metadata(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or not _frontmatter_boundary(lines[0]):
        return {}
    end = next(
        (index for index in range(1, len(lines)) if _frontmatter_boundary(lines[index])), None
    )
    if end is None:
        raise VerificationInputError("verification.policy.workflow_metadata_invalid")
    try:
        metadata = yaml.load("\n".join(lines[1:end]), Loader=_UniqueWorkflowLoader)
    except yaml.YAMLError as error:
        raise VerificationInputError("verification.policy.workflow_metadata_invalid") from error
    if not isinstance(metadata, dict):
        raise VerificationInputError("verification.policy.workflow_metadata_invalid")
    return metadata


class _UniqueWorkflowLoader(yaml.SafeLoader):
    """Reject duplicate workflow authority keys instead of accepting last-write wins."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise VerificationInputError(
                    "verification.policy.workflow_duplicate_or_invalid_key"
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result
