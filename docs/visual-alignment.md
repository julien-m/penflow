# Review visual alignment

Use `penflow visual-alignment` to decide what to correct after collecting a mockup reference, a runtime capture and the full rendered comparison. The command reads files and prints a Markdown report. A generated report exits 0, including when it finds incompatible or missing evidence. An unusable manifest or evidence root exits 2. Keep using the original diagnostic command and exit code for automation.

```bash
penflow visual-alignment review.json --evidence-root ./captures > visual-alignment.md
```

Evidence paths resolve inside the selected root, which defaults to the manifest directory. The command accepts the full JSON output of `penflow check --target ... --json` with its `compare-rendered` entry or the full object returned by `compare_rendered`. Counts alone cannot supply individual diagnostics. The manifest associates the diagnostic with the captures. The existing report format carries no independent image or state binding. Read [the capture guide](adapters/web-rendered.md) for the measurement contract.

## Manifest

```json
{
  "version": 1,
  "locale": "en",
  "cases": [
    {
      "title": "Account settings",
      "before": {
        "design": {
          "frame": "settings-approved",
          "screen": "settings",
          "state": "ready",
          "variant": null,
          "viewport": [1440, 900]
        },
        "runtime": {
          "screen": "settings",
          "state": "ready",
          "variant": null,
          "viewport": [1440, 900]
        },
        "images": {"side_by_side": "settings.png"},
        "report": "settings-check.json"
      },
      "findings": [
        {
          "priority": 1,
          "title": "Restore the compact settings header",
          "action": "product_fix",
          "basis": "visual",
          "region": "In each panel, from the account heading through the tabs.",
          "expected": "The first section starts below the tabs in the first viewport.",
          "observed": "The expanded heading takes up the first viewport.",
          "proposal": "Reduce the space between the heading and tabs.",
          "verify": "Recapture the ready state with the same user and test data.",
          "evidence": [{"path": "settings.png", "note": "Compare the heading and tabs."}]
        }
      ]
    }
  ]
}
```

- Record the screen, state, variant and logical viewport independently on each side. Use `variant: null` for a known default variant and omit it when unknown. A missing state or `state: null` means unknown. Set `composite: true` when a design board or capture combines multiple states. A design frame identifies the chosen mockup reference.
- Supply one PNG per side via `images.design` and `images.runtime`, or a side-by-side PNG with the design on the left and runtime on the right, without gutters. `images.scale` defaults to 1 raster pixel per logical pixel. Set `images.design_scale` and `images.runtime_scale` for separate PNGs at different scales. The report checks PNG dimensions, chunk boundaries and checksums. The reviewer establishes the panel contents, provenance, crop and matching data.
- Add up to three material observations to the summary by assigning the smallest priority numbers first. Each finding names a region, an expectation, an observation, a proposal and a specific recapture or check. A case with insufficient evidence can still carry provisional design or recapture notes. Review priorities and product intent come from the operator who inspected the evidence.
- Use one action per observation. `product_fix` needs a comparable pair and a visual observation or measured value. Use `recapture` to obtain comparable evidence and `clarify_design` to resolve reference or behavior ambiguity. `approved_divergence` requires an `approval` reference with `path` and `note` identifying the decision.
- Set `basis` to `visual`, `measurement`, `decision` or `missing_observation`. Cite supporting files with `path` and `note`. A measurement needs at least one `pointer` to a numeric observation in JSON. Include the source and units in the note. Penflow displays the exact value found, without inferring a measure from prose.
- For a repeat, add `after` with the same structure as `before`. Keep the approved frame, screen, state, variant and viewport. Use separate PNGs in both rounds so Penflow can check that the design bytes match and the runtime image data changed. For each reviewed finding, add `follow_up` with `observed` and `evidence`. The output retains both machine verdicts. Distinct image data supports the comparison. Establish capture freshness and resolution from the operator evidence.
- Use `locale: "fr"` for French report labels. Authored observations and machine messages are reproduced in their input language.
