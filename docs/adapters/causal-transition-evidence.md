# Causal Transition Evidence Adapter Contract

External adapters capture runtime facts; Penflow core validates their local artifacts. Penflow never launches a browser, simulator, test runner, or application runtime for this contract.

## Producer Sequence

1. Validate the strict flow contract and retain its raw-byte SHA-256.
2. Start one adapter run with a unique `runs[].id`, adapter name/version, and surface.
3. For each causal transition, observe the declared pre-state, the user-visible action event identified by its stable `test_id`, and the resulting post-state/destination in that same run.
4. Save one or more closed runtime-receipt JSON payloads inside the evidence directory and record each relative path, kind, run id, and SHA-256.
5. **Read** [causal-runtime-receipt.schema.json](../../penflow/schemas/causal-runtime-receipt.schema.json) and bind every payload to its run, adapter, surface, transition, observation, outcome, and capture kind.
6. Emit `causal-evidence.json`; **Read** [causal-transition-evidence.schema.json](../../penflow/schemas/causal-transition-evidence.schema.json) for its closed envelope.
7. Run:

```bash
penflow validate-causal-evidence flow-ui-contract/contract.json evidence/causal-evidence.json --json
```

## Proof Rules

- `contract.id`, `contract.version`, and `contract.sha256` identify the exact contract bytes.
- `action.visible` is always `true`; `action.id`, `test_id`, and `event` match the declared visible node/action.
- `pre_state`, `post_state`, and `destination` are explicit. `navigation` changes screen; `state` changes state on one screen; `environment` changes at least one.
- `default -> default`, an unchanged value, a missing destination, or static contract/spec documentation is not runtime proof.
- Runtime receipt paths stay inside the evidence directory, exist, match their digests, and use a `runtime-*` kind.
- A runtime label is not authority: each referenced file must be a closed `penflow-causal-runtime-receipt` v1 JSON object whose identities match the enclosing observation and declared run.
- Each causal fan-out guard has complete `variable`, `operator`, `value`, and `source` fields, including governed fan-outs; metadata-free legacy transitions remain compatible.
- Each causal outcome is observed. Incompatible fan-out outcomes cannot reuse a receipt identity, path, byte content, or SHA-256.

## Runtime Receipt Payload

```json
{
  "kind": "penflow-causal-runtime-receipt",
  "version": 1,
  "run_id": "run-proof-success",
  "transition_id": "payment_success",
  "observation_id": "observe-success",
  "outcome": "success",
  "adapter": {"name": "web-dom-adapter", "version": "1.0.0"},
  "surface": "web",
  "capture": {
    "kind": "runtime-state",
    "action": {
      "id": "submit_payment",
      "test_id": "checkout-pay",
      "event": "user clicked Pay",
      "visible": true
    },
    "pre_state": {
      "screen": "checkout",
      "state": "default",
      "value": "payment pending"
    },
    "post_state": {
      "screen": "checkout",
      "state": "success",
      "value": "payment complete"
    },
    "destination": {"screen": "checkout", "state": "success"},
    "outcome": "success"
  }
}
```

The payload is closed and its typed capture snapshot must exactly equal the enclosing observation. Unknown fields, malformed JSON/prose, identity drift, adapter/surface drift, a capture kind differing from the evidence receipt, or any action/pre-state/post-state/destination/outcome mismatch fails validation.

## Consumer Result

The command exits 0 with `status: PASS`, 1 with a deterministic `status: FAIL` issue report, and 2 for unreadable/malformed boundary inputs. Adapters may use any stack as long as they emit this contract.
