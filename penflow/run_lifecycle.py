# @spec FR-006 FR-007 FR-008 FR-009: Feature 074 managed-run lifecycle.
"""Public facade for crash-consistent managed-run lifecycle services."""

from .artifact_policy import Retention
from .run_cleanup_apply import apply_cleanup_plan
from .run_cleanup_plan import build_cleanup_plan
from .run_inventory import enumerate_managed_root, inventory_managed_tree
from .run_lock import LifecycleLock, capture_owner_identity, verify_owner_liveness
from .run_manifest import (
    allocate_run,
    atomic_write_json,
    load_manifest,
    reconcile_manifest_owner,
    register_manifest_entry,
    save_manifest,
    snapshot_manifest_entry,
    transition_manifest,
)
from .run_models import DurableOutput, ManagedRunManifest, ManifestPathEntry, OwnerIdentity
from .run_receipts import (
    CleanupItem,
    CleanupPlan,
    CleanupReceipt,
    LifecycleFinding,
)
from .run_models import CleanupReceiptSummary
from .run_states import (
    CleanupState,
    CleanupStatus,
    EntryKind,
    LifecycleBlockedError,
    LifecyclePhase,
    OwnerLiveness,
    ProducerState,
)

__all__ = (
    "CleanupItem",
    "CleanupPlan",
    "CleanupReceipt",
    "CleanupReceiptSummary",
    "CleanupState",
    "CleanupStatus",
    "DurableOutput",
    "EntryKind",
    "LifecycleBlockedError",
    "LifecycleFinding",
    "LifecycleLock",
    "LifecyclePhase",
    "ManagedRunManifest",
    "ManifestPathEntry",
    "OwnerIdentity",
    "OwnerLiveness",
    "ProducerState",
    "Retention",
    "allocate_run",
    "apply_cleanup_plan",
    "atomic_write_json",
    "build_cleanup_plan",
    "capture_owner_identity",
    "enumerate_managed_root",
    "inventory_managed_tree",
    "load_manifest",
    "reconcile_manifest_owner",
    "register_manifest_entry",
    "save_manifest",
    "snapshot_manifest_entry",
    "transition_manifest",
    "verify_owner_liveness",
)
