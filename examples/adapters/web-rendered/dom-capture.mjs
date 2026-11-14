// @ts-check
/** External DOM measurement adapter. It reads rendered facts, never a design tree. */

/**
 * Capture annotated screen roots, their semantic descendants and computed styles.
 *
 * The caller runs this function inside the target browser after fonts/images settle.
 * Only visible mapped elements are emitted; unmapped visible interactive elements
 * reject the capture instead of silently disappearing from coverage.
 * @returns {Record<string, unknown>} C12 tree with explicit measurement metadata.
 * @throws {Error} When identities or observed DOM structure cannot be represented.
 */
export function captureRenderedDocument() {
	const screenSelector = "[data-penflow-screen]";
	const nodeSelector = "[data-semantic]";
	const screens = Array.from(document.querySelectorAll(screenSelector));
	if (!screens.length) throw new Error("No annotated screen root was observed");
	/** @param {Element} element */
	const visible = (element) => {
		const rect = element.getBoundingClientRect();
		const style = getComputedStyle(element);
		return rect.width > 0 && rect.height > 0 && style.display !== "none" &&
			style.visibility !== "hidden" && style.visibility !== "collapse";
	};
	/** @param {Element} element */
	const roleOf = (element) => {
		if (element.matches(screenSelector)) return "screen";
		const aria = element.getAttribute("role");
		const ariaRoles = /** @type {Record<string, string>} */ ({
			button: "button", link: "link", textbox: "input", spinbutton: "input",
			combobox: "select", checkbox: "checkbox", radio: "radio", img: "image",
			heading: "heading", navigation: "navigation", status: "text", region: "container", group: "container",
		});
		if (aria) {
			if (!ariaRoles[aria]) throw new Error(`Unsupported observed ARIA role: ${aria}`);
			return ariaRoles[aria];
		}
		if (element.matches("h1,h2,h3,h4,h5,h6")) return "heading";
		if (element.tagName === "NAV") return "navigation";
		if (element instanceof HTMLButtonElement) return "button";
		if (element instanceof HTMLAnchorElement && element.hasAttribute("href")) return "link";
		if (element instanceof HTMLInputElement) {
			return ["checkbox", "radio"].includes(element.type) ? element.type : "input";
		}
		if (element instanceof HTMLSelectElement) return "select";
		if (element instanceof HTMLTextAreaElement) return "input";
		if (element instanceof HTMLImageElement) return "image";
		if (element instanceof SVGElement) return "icon";
		return element.children.length ? "container" : "text";
	};
	/** @param {Element} element @param {DOMRect} origin @returns {Record<string, unknown>} */
	const nodeOf = (element, origin) => {
		const identity = element.getAttribute("data-semantic");
		if (!identity) throw new Error("Every observed screen and node needs data-semantic");
		const rect = element.getBoundingClientRect();
		const style = getComputedStyle(element);
		const role = roleOf(element);
		const visual = /** @type {Record<string, unknown>} */ ({
			fontFamily: style.fontFamily, fontSize: Number.parseFloat(style.fontSize),
			fontWeight: style.fontWeight,
			padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft].map(Number.parseFloat),
		});
		const lineHeight = Number.parseFloat(style.lineHeight);
		if (Number.isFinite(lineHeight)) visual.lineHeight = lineHeight;
		const fill = role === "text" || role === "heading" ? style.color : style.backgroundColor;
		if (fill !== "rgba(0, 0, 0, 0)" && fill !== "transparent") visual.fill = fill;
		if (style.display === "flex" || style.display === "inline-flex") {
			visual.layout = style.flexDirection.startsWith("column") ? "vertical" : "horizontal";
			visual.alignItems = style.alignItems;
			const rowGap = Number.parseFloat(style.rowGap);
			const columnGap = Number.parseFloat(style.columnGap);
			if (Number.isFinite(rowGap) && rowGap === columnGap) visual.gap = rowGap;
		} else if (["block", "inline", "inline-block", "flow-root"].includes(style.display)) {
			// Ordinary flow is an explicit observation, distinct from unrepresented
			// grid/table layout. It does not claim that those engines behave as none.
			visual.layout = "none";
		}
		const mappedChildren = Array.from(element.querySelectorAll(nodeSelector)).filter(
			(child) => child.parentElement?.closest(nodeSelector) === element && visible(child),
		);
		const text = mappedChildren.length ? null : (element.textContent ?? "").trim();
		const node = /** @type {Record<string, unknown>} */ ({
			id: identity, semantic_id: identity, role, text,
			// DOMRect is a border box in layout-viewport CSS pixels, not physical pixels.
			bbox: { x: rect.x - origin.x, y: rect.y - origin.y, width: rect.width, height: rect.height },
			visual, children: mappedChildren.map((child) => nodeOf(child, origin)),
			observed: {
				visible: true, overflow_x: element.scrollWidth > element.clientWidth,
				overflow_y: element.scrollHeight > element.clientHeight,
				line_height_css: style.lineHeight, transform: style.transform,
			},
		});
		if (element instanceof HTMLImageElement) {
			node.image = { natural_width: element.naturalWidth, natural_height: element.naturalHeight,
				object_fit: style.objectFit };
			visual.objectFit = style.objectFit;
		}
		if (role === "icon") visual.iconSize = Math.max(rect.width, rect.height);
		if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement ||
			element instanceof HTMLSelectElement) {
			const labels = Array.from(element.labels ?? []).map((label) => label.textContent?.trim()).filter(Boolean);
			if (labels.length) node.label = labels.join(" ");
		}
		return node;
	};
	const screenTrees = screens.filter(visible).map((screen) => {
		if (screen.parentElement?.closest(screenSelector)) throw new Error("Nested screen roots are ambiguous");
		const controls = screen.querySelectorAll("button,input,select,textarea,a[href],[role=button],[tabindex],[onclick],[contenteditable=true]");
		for (const control of controls) {
			if (visible(control) && !control.matches(nodeSelector)) {
				throw new Error("Visible interactive control is missing data-semantic");
			}
		}
		const origin = screen.getBoundingClientRect();
		const root = nodeOf(screen, origin);
		const ids = Array.from(screen.querySelectorAll(nodeSelector)).filter(visible).map(
			(element) => element.getAttribute("data-semantic"),
		);
		ids.push(screen.getAttribute("data-semantic"));
		if (new Set(ids).size !== ids.length) throw new Error("Duplicate rendered semantic identity");
		const result = /** @type {Record<string, unknown>} */ ({
			screen_id: screen.getAttribute("data-penflow-screen"),
			viewport: { width: innerWidth, height: innerHeight }, root,
			screen_origin: { x: origin.x, y: origin.y },
		});
		const designId = screen.getAttribute("data-design-screen-id");
		if (designId) result.design_screen_id = designId;
		const variant = screen.getAttribute("data-penflow-variant");
		if (variant) result.variant = variant;
		// A state label is not a witnessed interaction. Stateful callers attach their
		// own scenario and observed_states evidence after a real state transition.
		return result;
	});
	if (!screenTrees.length) throw new Error("No visible annotated screen was observed");
	return {
		version: 1,
		measurement: { source: "runtime", units: "css-px", coordinate_space: "screen-relative",
			zoom: window.visualViewport?.scale ?? 1, device_pixel_ratio: devicePixelRatio,
			method: "getBoundingClientRect+getComputedStyle" },
		screens: screenTrees,
	};
}
