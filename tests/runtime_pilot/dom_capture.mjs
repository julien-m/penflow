/** Snapshot only current rendered DOM facts; no expected-tree or contract input. */
export function snapshotDocument() {
    const main = document.querySelector('main');
    const origin = main.getBoundingClientRect();
    const interactive = [...document.querySelectorAll('button,input,select,textarea,a[href],[role="button"],[role="link"],[tabindex],[onclick],[contenteditable="true"]')];
    const unmapped = interactive.filter(element => {
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && getComputedStyle(element).visibility !== 'hidden' && !element.dataset.semantic;
    });
    if (unmapped.length) throw new Error(`Unmapped rendered interactive controls: ${unmapped.map(element => element.outerHTML).join(', ')}`);
    function actualRole(element) {
      const aria = element.getAttribute('role');
      const roles = { button: 'button', link: 'link', textbox: 'input', spinbutton: 'input', combobox: 'select', checkbox: 'checkbox', radio: 'radio', img: 'image', heading: 'text', status: 'text' };
      if (aria) {
        if (!roles[aria]) throw new Error(`Unsupported observed ARIA role: ${aria}`);
        return roles[aria];
      }
      if (element === main) return 'screen';
      if (element.tagName === 'BUTTON') return 'button';
      if (element.tagName === 'A' && element.hasAttribute('href')) return 'link';
      if (element.tagName === 'INPUT') return ['checkbox', 'radio'].includes(element.type) ? element.type : 'input';
      if (element.tagName === 'SELECT') return 'select';
      if (element.tagName === 'TEXTAREA') return 'input';
      if (element.tagName === 'IMG') return 'image';
      return element.children.length ? 'container' : 'text';
    }
    const nodes = [...document.querySelectorAll('[data-semantic]')].map(element => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const role = actualRole(element);
      const parent = element.parentElement?.closest('[data-semantic]');
      const context = Object.fromEntries(['binding', 'entity', 'action', 'testId'].filter(key => element.dataset[key]).map(key => [key === 'testId' ? 'test_id' : key, element.dataset[key]]));
      let painted = element;
      while (painted.parentElement && ['rgba(0, 0, 0, 0)', 'transparent'].includes(getComputedStyle(painted).backgroundColor)) painted = painted.parentElement;
      const background = getComputedStyle(painted).backgroundColor;
      const visual = { fill: role === 'text' ? style.color : background, fontFamily: style.fontFamily, fontSize: parseFloat(style.fontSize),
        fontWeight: style.fontWeight, padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft].map(parseFloat) };
      if (style.display === 'flex') Object.assign(visual, { layout: style.flexDirection === 'column' ? 'vertical' : 'horizontal',
        gap: parseFloat(style.gap), alignItems: style.alignItems });
      const widths = ['Top', 'Right', 'Bottom', 'Left'].map(side => parseFloat(style[`border${side}Width`]));
      if (widths.some(width => width > 0)) {
        const colors = ['Top', 'Right', 'Bottom', 'Left'].map(side => style[`border${side}Color`]);
        if (!colors.every(color => color === colors[0])) throw new Error('C12 adapter cannot represent unequal border colors');
        visual.stroke = colors[0];
        visual.strokeWidth = widths.every(width => width === widths[0]) ? widths[0] : Object.fromEntries(['top', 'right', 'bottom', 'left'].map((side, index) => [side, widths[index]]));
        // CSS borders paint inside the measured border-box rectangle.
        visual.strokeAlignment = 'inner';
      }
      const radii = ['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map(corner => parseFloat(style[`border${corner}Radius`]));
      if (!radii.every(radius => radius === radii[0])) throw new Error('C12 adapter cannot represent unequal corner radii');
      if (radii[0] > 0) visual.cornerRadius = radii[0];
      return { id: element.dataset.semantic, semantic_id: element.dataset.semantic,
        parent_semantic_id: parent?.dataset.semantic ?? null, context,
        role, text: element.labels?.length ? [...element.labels].map(label => label.textContent).join(' ') : (element.children.length ? null : element.textContent),
        bbox: { x: rect.x - origin.x, y: rect.y - origin.y, width: rect.width, height: rect.height },
        viewport_rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden',
        enabled: !element.disabled && element.getAttribute('aria-disabled') !== 'true',
        value: element.tagName === 'INPUT' && element.type === 'number' ? (Number.isFinite(element.valueAsNumber) ? element.valueAsNumber : null) : ('value' in element ? element.value : null),
        computed_css: { color: style.color, backgroundColor: style.backgroundColor, display: style.display,
          boxSizing: style.boxSizing, borderTopWidth: style.borderTopWidth, borderRightWidth: style.borderRightWidth,
          borderBottomWidth: style.borderBottomWidth, borderLeftWidth: style.borderLeftWidth,
          borderTopColor: style.borderTopColor, borderRightColor: style.borderRightColor,
          borderBottomColor: style.borderBottomColor, borderLeftColor: style.borderLeftColor,
          borderTopStyle: style.borderTopStyle, borderRightStyle: style.borderRightStyle,
          borderBottomStyle: style.borderBottomStyle, borderLeftStyle: style.borderLeftStyle,
          borderTopLeftRadius: style.borderTopLeftRadius, borderTopRightRadius: style.borderTopRightRadius,
          borderBottomRightRadius: style.borderBottomRightRadius, borderBottomLeftRadius: style.borderBottomLeftRadius,
          fontFamily: style.fontFamily, fontWeight: style.fontWeight, lineHeight: style.lineHeight,
          justifyContent: style.justifyContent, effective_background: background, flexDirection: style.flexDirection, gap: style.gap, alignItems: style.alignItems, visibility: style.visibility },
        visual };
    });
    const amount = document.querySelector('#amount');
    return { observed_at: new Date().toISOString(), url: location.href, screen_id: main.dataset.screen, state: main.dataset.state,
      properties: amount ? { payment_input: amount.validity.valid ? 'valid' : 'invalid', amount: Number(amount.value),
        actor: new URLSearchParams(location.search).get('actor') || 'buyer' } : {},
      coordinate_space: "screen-relative", screen_origin: { x: origin.x, y: origin.y },
      viewport: { width: innerWidth, height: innerHeight }, nodes };
}
