# Integrated pen.dev editor observations

Live operator tests on 2026-11-14 used the integrated pen-dev plugin, whose installed skill was version 0.1.3, in one separate, pinned Codex test chat. Two disposable documents A and B were used; Atlas designs were not modified by these tests. The coordinator explicitly switched between the test chat and its own chat through the native navigation tool. No screenshot or physical view was used to certify focus; navigation results and user reports establish that context.

## Results

| Condition | Actual result |
| --- | --- |
| Request A before first displaying its chat | `open_editor` returned `Opened`; the first state request timed out, and the one documented retry reported no open editor. No successful connection was claimed. |
| Display the test chat | A became readable. An earlier creation call had timed out but its nodes were subsequently found and persisted; it was not replayed blindly. |
| Connected A, chat hidden, displays asleep | A text change and independent plugin readback succeeded. Disk metadata/digest had not changed after approximately 48 seconds, so immediate persistence was not established. A later phase found the file changed and the text still present. |
| Request B while the chat is hidden | `Opened` was returned, but the state still identified A; the targeted B read timed out. A remained readable. |
| Display the test chat with A and B views requested | B became readable and was edited. Targeted reads of A then B succeeded without reopening either file. An additional pair of reads succeeded with all displays asleep. |
| Final controlled run: chat hidden and displays asleep | One change to A, independent reads of A and B, and changed A disk digest/mtime succeeded. B retained its distinct text. No editor was opened or reopened. |

The final run occurred at approximately 04:53 UTC. The coordinator requested display sleep with `pmset displaysleepnow` (exit 0). Six CoreGraphics samples around the mutation and reads reported all four online displays asleep, with successful `CGGetOnlineDisplayList` results. `CGDisplayIsAsleep` is the operating-system observation; it does not prove that a hardware power button was used. Another earlier run had awake displays despite a user report of screens off; that run is not counted as the controlled asleep result.

The live records are retained in the pinned chat **pen.dev — tests arrière-plan et deux documents**, thread `01a1d85b-4089-7f81-824f-25ec17a62a3f`, with per-phase JSON outputs. They are bounded observations on this installation, not an automated regression suite or a universal plugin capability guarantee.

## Operator implications

- A connected editor need not keep its chat selected or its displays awake for these operations. Initial view creation/connection is a separate condition: an opening acknowledgement alone is insufficient.
- Two connected documents can be targeted independently in one chat. Do not invent a one-editor-per-chat restriction. This capability does not change the single product canvas rule: read [the normal workflow](review-led-workflow.md#existing-canvas-and-editor-connection) and enrich existing product screens in place.
- Target the exact file and read back uncertain mutations before retrying. Persistence can lag editor changes; distinguish immediate, delayed and unverified saves. Changed file metadata/digest plus plugin readback was the save evidence here; the tests did not close/reopen the app or independently reload the edited file to prove durability.
- Long unattended runs, locked sessions, application restarts and computer sleep were not tested. No headless editor guarantee, plugin code fix, runtime adapter or new certification prerequisite is introduced.
