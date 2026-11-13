---
name: mockup-factory
description: Penflow-local guided UX/UI optimizer for pen.dev mockups using current product intent, structural diagnostics and independent final review.
---
# Mockup Factory

Read [the normal review led workflow](../../../docs/review-led-workflow.md) before working. Use current product intent and design anchors; missing administrative receipts do not stop independent checks.

- Inspect the requested screens and current `flow-ui-contract/contract.json`, semantic tree, `ui.pen`, theme and available context mapping. Keep `screen_id`, `semantic_id` and `pencil_node_id` anchors when present. Clarify only functional decisions that cannot be resolved from authorized scope.
- Read project conventions and applicable spacing, layout, component, accessibility and platform guides. Use parent-driven layout, real content and meaningful states. Read [design taste guidance](references/design-taste-advisory.md) when useful; its observations inform review.
- Use the user's requested Pencil/pen.dev plugin and its current documented tools. Read [the Penflow operator boundary](../penflow/SKILL.md) before saving or diagnosing a tool capability. Renderer/MCP/runtime orchestration stays outside Penflow Python core.
- Inspect actual rendered screens, hierarchy, balance, readability, clipping and reference fidelity where relevant. Compare repeated components across screens; local metrics alone cannot prove visual quality. Keep original screenshots/PNGs, display them with absolute-path Markdown images plus clickable links and publish annotation links through `visual-preview url --json <absolute-path>`. Report missing rendered observations explicitly.
- Run `penflow check --target <workspace> --project <consumer-project-root> --json` and relevant product checks. Anchor fixes to concrete product findings. Recheck changed inputs and affected behavior; no full-chain rerun or fixed iteration count is required for unrelated findings.
- Give one fresh native final reviewer the request, anchors, full diff, visual observations and real check results. Correct material findings, disclose accepted limitations and deliver within authorization. A missing essential visual observation with material risk remains unverified.

Only when certification is explicitly requested, read [the former workflow](certification.md), which links its rubric, visual-validation protocol and historical full-chain loop. Do not load those certificate protocols as normal delivery prerequisites.
