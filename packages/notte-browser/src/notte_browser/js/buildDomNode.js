// file taken from: https://github.com/browser-use/browser-use/blob/main/browser_use/dom/buildDomTree.js
//
// Builds the tree of ONE document: iframes are not descended into. The caller (dom/parsing.py)
// evaluates this script in every frame and grafts each frame's tree under its iframe element,
// which it identifies by passing the frames' iframe element handles in `frame_elements`.
(
	{ highlight_elements, focus_element, viewport_expansion, enable_pointer_elements, frame_elements = [], collect_elements = false }
) => {
	const { doHighlightElements, focusHighlightIndex, viewportExpansion, debugMode } = {
		doHighlightElements: highlight_elements,
		focusHighlightIndex: focus_element,
		viewportExpansion: viewport_expansion,
		debugMode: false,
	};
	let highlightIndex = 0; // Reset highlight index

	/*
	 * DOM reads that the page cannot redirect. A `<form>` exposes its controls as properties named after
	 * their `name` or `id`, and they win over the form's own properties and methods: with
	 * `<input name="children">`, `form.children` is the input. The walk visits forms like any other
	 * element, so what it reads on an element goes through the prototype that defines it. In the page's
	 * own world (the Playwright backend), the document does the same for named images, forms and embeds
	 * (`<img name="body">` is `document.body`).
	 */
	function nativeGetter(prototype, name) {
		const get = Object.getOwnPropertyDescriptor(prototype, name).get;
		return (node) => get.call(node);
	}
	const parentNodeOf = nativeGetter(Node.prototype, "parentNode");
	const parentElementOf = nativeGetter(Node.prototype, "parentElement");
	const childNodesOf = nativeGetter(Node.prototype, "childNodes");
	const nodeTypeOf = nativeGetter(Node.prototype, "nodeType");
	const nodeNameOf = nativeGetter(Node.prototype, "nodeName");
	const ownerDocumentOf = nativeGetter(Node.prototype, "ownerDocument");
	const childrenOf = nativeGetter(Element.prototype, "children");
	const tagNameOf = nativeGetter(Element.prototype, "tagName");
	const localNameOf = nativeGetter(Element.prototype, "localName");
	const idOf = nativeGetter(Element.prototype, "id");
	const shadowRootOf = nativeGetter(Element.prototype, "shadowRoot");
	const classListOf = nativeGetter(Element.prototype, "classList");

	const NODE = Node.prototype;
	const ELEMENT = Element.prototype;
	const getAttribute = (element, name) => ELEMENT.getAttribute.call(element, name);
	const hasAttribute = (element, name) => ELEMENT.hasAttribute.call(element, name);
	const matches = (element, selector) => ELEMENT.matches.call(element, selector);
	const closest = (element, selector) => ELEMENT.closest.call(element, selector);
	const contains = (node, other) => NODE.contains.call(node, other);
	const getRootNode = (node) => NODE.getRootNode.call(node);
	const getBoundingClientRect = (element) => ELEMENT.getBoundingClientRect.call(element);
	const getClientRects = (element) => ELEMENT.getClientRects.call(element);
	// `checkVisibility` is recent (Chrome 105): undefined where the browser does not have it
	const checkVisibilityOf = ELEMENT.checkVisibility &&
		((element, options) => ELEMENT.checkVisibility.call(element, options));

	/**
	 * Any other property of an element (`disabled`, `offsetWidth`, `onclick`, ...), read from its
	 * prototype chain when the element is a form.
	 *
	 * @param {Element} element - The element.
	 * @param {string} name - The property.
	 * @returns {any} Its value, or undefined when the element has no such property.
	 */
	function propertyOf(element, name) {
		if (!(element instanceof HTMLFormElement)) return element[name];
		for (let prototype = Object.getPrototypeOf(element); prototype !== null; prototype = Object.getPrototypeOf(prototype)) {
			const descriptor = Object.getOwnPropertyDescriptor(prototype, name);
			if (descriptor !== undefined) return descriptor.get ? descriptor.get.call(element) : descriptor.value;
		}
		return undefined;
	}

	const DOCUMENT = Document.prototype;
	const BODY = Object.getOwnPropertyDescriptor(DOCUMENT, "body").get.call(document);
	const DOCUMENT_ELEMENT = Object.getOwnPropertyDescriptor(DOCUMENT, "documentElement").get.call(document);
	const STYLE_SHEETS = Object.getOwnPropertyDescriptor(DOCUMENT, "styleSheets").get.call(document);

	// Add caching mechanisms at the top level
	const DOM_CACHE = {
		boundingRects: new WeakMap(),
		clientRects: new WeakMap(),
		computedStyles: new WeakMap(),
		clearCache: () => {
			DOM_CACHE.boundingRects = new WeakMap();
			DOM_CACHE.clientRects = new WeakMap();
			DOM_CACHE.computedStyles = new WeakMap();
		}
	};

	/**
	 * Gets the cached bounding rect for an element.
	 *
	 * @param {HTMLElement} element - The element to get the bounding rect for.
	 * @returns {DOMRect | null} The cached bounding rect, or null if the element is not found.
	 */
	function getCachedBoundingRect(element) {
		if (!element) return null;

		if (DOM_CACHE.boundingRects.has(element)) {
			return DOM_CACHE.boundingRects.get(element);
		}

		const rect = getBoundingClientRect(element);

		if (rect) {
			DOM_CACHE.boundingRects.set(element, rect);
		}
		return rect;
	}

	/**
	 * Gets the cached computed style for an element.
	 *
	 * @param {HTMLElement} element - The element to get the computed style for.
	 * @returns {CSSStyleDeclaration | null} The cached computed style, or null if the element is not found.
	 */
	function getCachedComputedStyle(element) {
		if (!element) return null;

		if (DOM_CACHE.computedStyles.has(element)) {
			return DOM_CACHE.computedStyles.get(element);
		}

		const style = window.getComputedStyle(element);

		if (style) {
			DOM_CACHE.computedStyles.set(element, style);
		}
		return style;
	}

	/**
	 * Gets the cached client rects for an element.
	 *
	 * @param {HTMLElement} element - The element to get the client rects for.
	 * @returns {DOMRectList | null} The cached client rects, or null if the element is not found.
	 */
	function getCachedClientRects(element) {
		if (!element) return null;

		if (DOM_CACHE.clientRects.has(element)) {
			return DOM_CACHE.clientRects.get(element);
		}

		const rects = getClientRects(element);

		if (rects) {
			DOM_CACHE.clientRects.set(element, rects);
		}
		return rects;
	}

	/**
	 * Hash map of DOM nodes indexed by their highlight index.
	 *
	 * @type {Object<string, any>}
	 */
	const DOM_HASH_MAP = {};

	/**
	 * Highlighted elements by highlight index, only returned when `collect_elements` is set
	 * (the caller then keeps an element handle per interaction node).
	 *
	 * @type {Object<number, HTMLElement> | null}
	 */
	const ELEMENTS = collect_elements ? {} : null;

	const ID = { current: 0 };

	const HIGHLIGHT_CONTAINER_ID = "playwright-highlight-container";

	// Mouse handlers that make an element interactive, and that make a wrapper a click target of its own.
	const CLICK_HANDLER_ATTRS = ["onclick", "onmousedown", "onmouseup", "ondblclick"];

	// Live state of the interactive elements (see `getLiveState`): longer values and option lists are cut.
	const MAX_STATE_VALUE_LENGTH = 200;
	const MAX_STATE_OPTIONS = 50;
	const MAX_STATE_OPTION_LABEL_LENGTH = 100;

	function truncateStateValue(value, state) {
		if (value.length <= MAX_STATE_VALUE_LENGTH) return value;
		state.valueTruncated = true;
		// FNV-1a over UTF-16 code units: a change marker, not a security hash. Keep the
		// full value out of the payload while detecting edits beyond the display cap.
		// Passwords never pass through this function.
		let hash = 0xcbf29ce484222325n;
		for (let i = 0; i < value.length; i++) {
			hash = BigInt.asUintN(64, (hash ^ BigInt(value.charCodeAt(i))) * 0x100000001b3n);
		}
		state.valueDigest = hash.toString(16).padStart(16, "0");
		return value.slice(0, MAX_STATE_VALUE_LENGTH);
	}

	function parseAriaBoolean(element, name) {
		const value = getAttribute(element, name);
		if (value === "true") return true;
		if (value === "false") return false;
		return undefined;
	}

	/**
	 * Reads the live state of a highlighted element: what the attributes do not show once the user
	 * (or a script) changed the element. `getAttribute('value')` is the initial value of an input,
	 * not what is typed in it; same for `checked` and the selected option of a `<select>`.
	 *
	 * Returned as its own payload field (never mixed into `attributes`, which the action descriptions
	 * render), so the rendered descriptions and the action ids are unchanged. Password values are
	 * never read: only whether the field is filled. Returns `undefined` when there is no state.
	 *
	 * @param {HTMLElement} element - A highlighted (interactive) element.
	 * @returns {object | undefined} The live state.
	 */
	function getLiveState(element) {
		const state = {};
		const tagName = tagNameOf(element).toLowerCase();
		if (tagName === "select") {
			state.value = element.value;
			const options = element.options;
			state.options = [];
			for (let i = 0; i < options.length; i++) {
				const option = options[i];
				// the selected options are always listed, even past the cap
				if (i >= MAX_STATE_OPTIONS && !option.selected) {
					state.optionsTruncated = true;
					continue;
				}
				state.options.push({
					value: option.value,
					label: (option.label || option.text || "").trim().slice(0, MAX_STATE_OPTION_LABEL_LENGTH),
					selected: option.selected,
					disabled: option.disabled || !!option.closest("optgroup[disabled]"),
				});
			}
			state.multiple = element.multiple;
		} else if (tagName === "input") {
			const type = (element.type || "text").toLowerCase();
			if (type === "checkbox" || type === "radio") {
				state.checked = element.checked;
			} else if (type === "password") {
				state.filled = element.value.length > 0;
			} else if (type !== "submit" && type !== "button" && type !== "reset" && type !== "image" && type !== "hidden") {
				state.value = truncateStateValue(element.value, state);
			}
		} else if (tagName === "textarea") {
			state.value = truncateStateValue(element.value, state);
		} else if (propertyOf(element, "isContentEditable")) {
			state.value = truncateStateValue(propertyOf(element, "innerText") || "", state);
		} else if (ARIA_RANGE_ROLES.has(getRole(element))) {
			// an ARIA slider or spin button: the value it shows ("14 Point"), else its number
			const value = getAttribute(element, "aria-valuetext") ?? getAttribute(element, "aria-valuenow");
			if (value !== null) state.value = truncateStateValue(value, state);
		}
		if (state.checked === undefined) {
			// role="checkbox" / "switch" / "radio" / "menuitemcheckbox" widgets
			const ariaChecked = getAttribute(element, "aria-checked");
			if (ariaChecked === "true" || ariaChecked === "false") state.checked = ariaChecked === "true";
			else if (ariaChecked === "mixed") state.mixed = true;
		}
		const expanded = parseAriaBoolean(element, "aria-expanded");
		if (expanded !== undefined) state.expanded = expanded;
		const selected = parseAriaBoolean(element, "aria-selected");
		if (selected !== undefined) state.selected = selected;
		const pressed = parseAriaBoolean(element, "aria-pressed");
		if (pressed !== undefined) state.pressed = pressed;
		else if (getAttribute(element, "aria-pressed") === "mixed") state.pressed = "mixed";
		return Object.keys(state).length > 0 ? state : undefined;
	}

	// Accessible names of the highlighted elements (see `getAccessibleName`): longer names are cut.
	const MAX_NAME_LENGTH = 200;
	// Roles whose name comes from their content (https://www.w3.org/TR/wai-aria-1.2/#namefromcontent).
	const NAME_FROM_CONTENT_ROLES = new Set([
		"button", "cell", "checkbox", "columnheader", "gridcell", "heading", "link", "menuitem",
		"menuitemcheckbox", "menuitemradio", "option", "radio", "row", "rowheader", "switch", "tab",
		"tooltip", "treeitem",
	]);
	// Controls whose value the user edits: they add nothing to the name of the element they label.
	const EDITABLE_CONTROL_ROLES = new Set(["textbox", "searchbox", "combobox", "listbox", "spinbutton", "slider"]);
	// widgets whose value is in `aria-valuenow` / `aria-valuetext` (a native range or number input has its own)
	const ARIA_RANGE_ROLES = new Set(["slider", "spinbutton"]);
	const INPUT_ROLES = {
		button: "button", submit: "button", reset: "button", image: "button", checkbox: "checkbox",
		radio: "radio", range: "slider", number: "spinbutton", search: "searchbox", text: "textbox",
		email: "textbox", tel: "textbox", url: "textbox",
		password: "textbox", // pragma: allowlist secret
	};
	// elements without a role of their own, which browsers do not name
	const GENERIC_TAGS = new Set(["div", "span", "a"]);
	const IMPLICIT_ROLES = {
		button: "button", summary: "button", option: "option", textarea: "textbox", td: "cell",
		th: "columnheader", tr: "row", h1: "heading", h2: "heading", h3: "heading", h4: "heading",
		h5: "heading", h6: "heading", img: "img",
	};

	function getRole(element) {
		const explicit = (getAttribute(element, "role") || "").trim().split(/\s+/)[0].toLowerCase();
		if (explicit) return explicit;
		const tagName = localNameOf(element);
		if (tagName === "a" || tagName === "area") return hasAttribute(element, "href") ? "link" : "";
		if (tagName === "select") return element.multiple || element.size > 1 ? "listbox" : "combobox";
		if (tagName === "input") {
			const type = (getAttribute(element, "type") || "text").toLowerCase();
			const role = INPUT_ROLES[type] ?? "";
			return hasAttribute(element, "list") && (role === "textbox" || role === "searchbox") ? "combobox" : role;
		}
		if (propertyOf(element, "isContentEditable") && !(parentElementOf(element) && propertyOf(parentElementOf(element), "isContentEditable"))) return "textbox";
		return IMPLICIT_ROLES[tagName] ?? "";
	}

	function isHiddenForName(element) {
		if (getAttribute(element, "aria-hidden") === "true") return true;
		const style = getCachedComputedStyle(element);
		return style?.display === "none" || style?.visibility === "hidden" || style?.visibility === "collapse";
	}

	function isInline(element) {
		const display = getCachedComputedStyle(element)?.display;
		return display === undefined || display === "inline" || display === "contents";
	}

	/**
	 * The accessible name of an element (https://www.w3.org/TR/accname-1.2/), as a screen reader
	 * announces it: `aria-labelledby`, `aria-label`, `<label>` (for / wrapping), `alt`, `<legend>`,
	 * button `value`, the text content of buttons, links and other roles named from content, then
	 * `title` and `placeholder`. Shadow roots and slotted content are traversed.
	 *
	 * Unlike browsers, the value of an editable control (a text field, a select) inside a label or an
	 * `aria-labelledby` target is never part of a name, so a name cannot contain what was typed.
	 * CSS generated content (`::before` / `::after`) is not read. Returns `undefined` for no name.
	 *
	 * @param {HTMLElement} element - A highlighted (interactive) element.
	 * @returns {string | undefined} The accessible name, cut to `MAX_NAME_LENGTH` characters.
	 */
	function getAccessibleName(element) {
		const context = { visited: new Set(), budget: 4 * MAX_NAME_LENGTH };
		const name = textAlternative(element, context, { root: true, labelledBy: false, content: false, hidden: false });
		const cleaned = name.replace(/\s+/g, " ").trim();
		return cleaned.length > 0 ? cleaned.slice(0, MAX_NAME_LENGTH) : undefined;
	}

	function textAlternative(element, context, step) {
		if (context.visited.has(element) || context.budget <= 0) return "";
		context.visited.add(element);
		if (!step.root && !step.hidden && isHiddenForName(element)) return "";
		const tagName = localNameOf(element);
		const role = getRole(element);

		// aria-labelledby, not followed from a labelledby target
		if (!step.labelledBy && hasAttribute(element, "aria-labelledby")) {
			const scope = getRootNode(element);
			const parts = [];
			for (const id of getAttribute(element, "aria-labelledby").trim().split(/\s+/)) {
				const target = id && (scope instanceof Document ? DOCUMENT.getElementById.call(scope, id) : scope.getElementById?.(id));
				if (!target) continue;
				context.visited.delete(target);
				parts.push(textAlternative(target, context, {
					root: false, labelledBy: true, content: true, hidden: step.hidden || isHiddenForName(target),
				}));
			}
			const text = parts.join(" ");
			if (text.trim()) return text;
		}
		// an editable control inside the label of another element: its value is left out
		if (!step.root && EDITABLE_CONTROL_ROLES.has(role)) return "";

		const ariaLabel = getAttribute(element, "aria-label");
		if (ariaLabel && ariaLabel.trim()) return ariaLabel;

		// host language labels: `<label>` first, even for input buttons, which then fall back to their value
		const labels = propertyOf(element, "labels");
		if (labels && labels.length > 0) {
			const text = Array.from(labels, (label) => {
				context.visited.delete(label);
				return textAlternative(label, context, { root: false, labelledBy: step.labelledBy, content: true, hidden: step.hidden });
			}).join(" ");
			if (text.trim()) return text;
		}
		if (tagName === "input") {
			const type = (getAttribute(element, "type") || "text").toLowerCase();
			if (type === "button" || type === "submit" || type === "reset") {
				const value = getAttribute(element, "value");
				if (value && value.trim()) return value;
				if (type !== "button") return type === "submit" ? "Submit" : "Reset";
			}
			if (type === "image") {
				const text = getAttribute(element, "alt") || getAttribute(element, "value") || getAttribute(element, "title");
				return text && text.trim() ? text : "Submit";
			}
		}
		if (tagName === "img" || tagName === "area") {
			const alt = getAttribute(element, "alt");
			if (alt && alt.trim()) return alt;
		} else if (tagName === "fieldset") {
			const legend = Array.from(childrenOf(element)).find((child) => localNameOf(child) === "legend");
			const text = legend ? textAlternative(legend, context, { ...step, root: false, content: true }) : "";
			if (text.trim()) return text;
		} else if (tagName === "svg") {
			const title = Array.from(childrenOf(element)).find((child) => localNameOf(child) === "title");
			if (title && title.textContent.trim()) return title.textContent;
		}

		// name from content: roles named by their text, and every descendant of a label
		if (step.content || NAME_FROM_CONTENT_ROLES.has(role)) {
			const text = contentText(element, context, step);
			if (text.trim()) return text;
		}

		// tooltips name the element itself only (not its ancestors), and never a generic element
		if (!step.root || (role === "" && GENERIC_TAGS.has(tagName))) return "";
		const title = getAttribute(element, "title");
		if (title && title.trim()) return title;
		const placeholder = getAttribute(element, "placeholder") || getAttribute(element, "aria-placeholder");
		if (placeholder && placeholder.trim() && (tagName === "input" || tagName === "textarea" || role === "textbox")) {
			return placeholder;
		}
		return "";
	}

	// browsers name elements after their rendered text: `text-transform` applies
	function transformText(text, parent) {
		const transform = parent ? getCachedComputedStyle(parent)?.textTransform : undefined;
		if (transform === "uppercase") return text.toUpperCase();
		if (transform === "lowercase") return text.toLowerCase();
		if (transform === "capitalize") return text.replace(/(^|\s)(\S)/g, (_, space, letter) => space + letter.toUpperCase());
		return text;
	}

	function contentText(element, context, step) {
		const childStep = { root: false, labelledBy: step.labelledBy, content: true, hidden: step.hidden };
		let children = shadowRootOf(element) ? shadowRootOf(element).childNodes : childNodesOf(element);
		if (localNameOf(element) === "slot") {
			const assigned = element.assignedNodes({ flatten: true });
			if (assigned.length > 0) children = assigned;
		}
		let text = "";
		for (const child of children) {
			if (context.budget <= 0) break;
			if (nodeTypeOf(child) === Node.TEXT_NODE) {
				text += transformText(child.data, parentElementOf(child));
				// formatting whitespace is collapsed away: it does not use up the budget
				context.budget -= child.data.trim().length;
			} else if (nodeTypeOf(child) === Node.ELEMENT_NODE && localNameOf(child) === "br") {
				text += " ";
			} else if (nodeTypeOf(child) === Node.ELEMENT_NODE) {
				const childText = textAlternative(child, context, childStep);
				text += isInline(child) ? childText : ` ${childText} `;
			}
		}
		return text;
	}

	// Add a WeakMap cache for XPath strings
	const xpathCache = new WeakMap();
	// position of an element among its siblings of the same tag (see `getElementPosition`)
	const positionCache = new WeakMap();

	// // Initialize once and reuse
	// const viewportObserver = new IntersectionObserver(
	//   (entries) => {
	//     entries.forEach(entry => {
	//       elementVisibilityMap.set(entry.target, entry.isIntersecting);
	//     });
	//   },
	//   { rootMargin: `${viewportExpansion}px` }
	// );

	/**
	 * Highlights an element in the DOM and returns the index of the next element.
	 *
	 * @param {HTMLElement} element - The element to highlight.
	 * @param {number} index - The index of the element.
	 * @param {HTMLElement | null} parentIframe - The parent iframe node.
	 * @returns {number} The index of the next element.
	 */
	function highlightElement(node, parentIframe = null) {
		if (!node) return null;
		// Create or get node container
		const rect = getBoundingClientRect(node);
		const bbox = {
			x: rect.left,
			y: rect.top,
			width: rect.width,
			height: rect.height,
			scroll_x: window.scrollX,
			scroll_y: window.scrollY,
			iframe_offset_x: parentIframe ? parentIframe.getBoundingClientRect().left : 0,
			iframe_offset_y: parentIframe ? parentIframe.getBoundingClientRect().top : 0,
			viewport_width: window.innerWidth,
			viewport_height: window.innerHeight,
		};
		return bbox;
	}

	// // Add this function to perform cleanup when needed
	// function cleanupHighlights() {
	//   if (window._highlightCleanupFunctions && window._highlightCleanupFunctions.length) {
	//     window._highlightCleanupFunctions.forEach(fn => fn());
	//     window._highlightCleanupFunctions = [];
	//   }

	//   // Also remove the container
	//   const container = document.getElementById(HIGHLIGHT_CONTAINER_ID);
	//   if (container) container.remove();
	// }

	/**
	 * Gets the position of an element in its parent: its parent element, or the shadow root it is a direct
	 * child of.
	 *
	 * @param {HTMLElement} currentElement - The element to get the position for.
	 * @returns {number} The position of the element in its parent.
	 */
	function getElementPosition(currentElement) {
		const parentNode = parentNodeOf(currentElement);
		const parent = parentElementOf(currentElement) ?? (parentNode instanceof ShadowRoot ? parentNode : null);
		if (!parent) {
			return 0; // No parent means no siblings
		}
		if (positionCache.has(currentElement)) return positionCache.get(currentElement);

		// the positions of all the children are computed at once: one pass over the siblings, not one per child
		// a shadow root is not an element (and cannot be clobbered): its own `children` is safe to read
		const children = parent instanceof ShadowRoot ? parent.children : childrenOf(parent);
		const counts = new Map();
		for (const child of children) {
			const tagName = nodeNameOf(child).toLowerCase();
			counts.set(tagName, (counts.get(tagName) ?? 0) + 1);
		}
		const seen = new Map();
		for (const child of children) {
			const tagName = nodeNameOf(child).toLowerCase();
			const index = (seen.get(tagName) ?? 0) + 1; // 1-based index
			seen.set(tagName, index);
			positionCache.set(child, counts.get(tagName) === 1 ? 0 : index); // 0: only element of its type
		}
		return positionCache.get(currentElement);
	}


	/**
	 * The XPath of an element in its document, or in its shadow root: the path restarts at a shadow root,
	 * whose direct children have their own step alone (the Python side chains the paths of the hosts).
	 *
	 * @param {HTMLElement} element - The element.
	 * @returns {string} Its XPath.
	 */
	function getXPathTree(element) {
		if (xpathCache.has(element)) return xpathCache.get(element);

		const position = getElementPosition(element);
		const tagName = nodeNameOf(element).toLowerCase();
		const xpathIndex = position > 0 ? `[${position}]` : "";
		const segment = `${tagName}${xpathIndex}`;
		// the parent's path is cached: the tree is built from the top, so it is usually already known
		const parent = parentNodeOf(element);
		const parentPath = parent && nodeTypeOf(parent) === Node.ELEMENT_NODE ? getXPathTree(parent) : "";
		const result = parentPath ? `${parentPath}/${segment}` : segment;

		xpathCache.set(element, result);
		return result;
	}

	/**
	 * What hides the content of an element, inherited down the tree (see `contentScope`).
	 *
	 * - `ariaHidden`: inside `aria-hidden="true"`, and not inside focusable content
	 * - `clipper`: the element that clips the content to an empty box (`height: 0; overflow: hidden`), or null
	 * - `inControl`: inside a highlighted, off-screen or disabled element (see `handleHighlighting`), whose text is its label
	 */
	const VISIBLE_SCOPE = { ariaHidden: false, clipper: null, inControl: false };

	/**
	 * Checks if an element can be reached with the Tab key. Focusable content stays visible inside an
	 * `aria-hidden` subtree.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is focusable.
	 */
	function isFocusable(element) {
		return propertyOf(element, "tabIndex") >= 0 && !matches(element, ':disabled');
	}

	/**
	 * Checks if an element clips its content to an empty box: a block with `overflow` other than
	 * `visible` and no height (or width) in that direction, as collapsed accordions and menus are.
	 * Inline elements, and elements without a box (`display: contents`, the options of a `<select>`),
	 * do not clip.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element clips its content to an empty box.
	 */
	function clipsToNothing(element) {
		const style = getCachedComputedStyle(element);
		if (!style || style.display === "inline" || style.display === "contents") return false;
		if (!getCachedClientRects(element)?.length) return false;
		const rect = getCachedBoundingRect(element);
		if (!rect) return false;
		return (style.overflowY !== "visible" && rect.height === 0) || (style.overflowX !== "visible" && rect.width === 0);
	}

	/**
	 * Checks if an element is laid out outside the box of a clipping ancestor: a fixed element, or an
	 * absolutely positioned one whose containing block (its nearest positioned ancestor) is outside the
	 * clipping element.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @param {HTMLElement} clipper - The clipping ancestor.
	 * @returns {boolean} Whether the element escapes the clipping.
	 */
	function escapesClip(element, clipper) {
		const position = getCachedComputedStyle(element)?.position;
		if (position === "fixed") return true;
		if (position !== "absolute") return false;
		const containingBlock = propertyOf(element, "offsetParent");
		return containingBlock === null || !contains(clipper, containingBlock);
	}

	/**
	 * The scope of an element's children: what hides them, given the element and its own scope.
	 *
	 * @param {HTMLElement} element - The element.
	 * @param {Object} scope - The scope of the element.
	 * @param {boolean} isControl - Whether the element is highlighted, off-screen or disabled.
	 * @returns {Object} The scope of its children.
	 */
	function contentScope(element, scope, isControl) {
		let ariaHidden = scope.ariaHidden;
		if (getAttribute(element, "aria-hidden") === "true") ariaHidden = !isFocusable(element);
		else if (ariaHidden && isFocusable(element)) ariaHidden = false;
		let clipper = scope.clipper;
		// an element that escapes the clipping is assumed not to be clipped by an outer clipper either
		if (clipper !== null && escapesClip(element, clipper)) clipper = null;
		if (clipsToNothing(element)) clipper = element;
		const inControl = scope.inControl || isControl;
		if (ariaHidden === scope.ariaHidden && clipper === scope.clipper && inControl === scope.inControl) return scope;
		return { ariaHidden, clipper, inControl };
	}

	/**
	 * The element itself, or its nearest ancestor with a box when it is `display: contents`.
	 *
	 * @param {HTMLElement} element - The element.
	 * @returns {HTMLElement} The element with the box.
	 */
	function boxOf(element) {
		while (parentElementOf(element) && getCachedComputedStyle(element)?.display === "contents") {
			element = parentElementOf(element);
		}
		return element;
	}

	/**
	 * Checks if an element is rendered: not under `display: none` or a skipped `content-visibility`
	 * (`hidden="until-found"`, a closed `<details>`), not `visibility: hidden` unless `checkVisibility`
	 * is unset, and not under `opacity: 0` when `checkOpacity` is set.
	 *
	 * `visibility` is read on the element itself, as a child can be visible in a hidden parent. The
	 * options of a `<select>` and `display: contents` elements have no box of their own, which
	 * `checkVisibility` reads as hidden: the box checked is the select's, or the nearest ancestor's.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @param {boolean} checkOpacity - Whether `opacity: 0` hides the element.
	 * @param {boolean} checkVisibility - Whether `visibility: hidden` hides the element.
	 * @returns {boolean} Whether the element is rendered.
	 */
	function isRendered(element, checkOpacity, checkVisibility = true) {
		if (localNameOf(element) === "option" || localNameOf(element) === "optgroup") {
			element = closest(element, "select") ?? element;
		}
		if (checkVisibility && getCachedComputedStyle(element)?.visibility !== "visible") return false;
		const box = boxOf(element);
		if (!checkVisibilityOf) return true;
		return checkVisibilityOf(box, { checkOpacity, checkVisibilityCSS: false });
	}

	/**
	 * Checks if a text node is hidden: not rendered, clipped away, or with an empty box.
	 *
	 * `opacity: 0` and `aria-hidden` hide text on screen only. Below the fold, content waiting to fade
	 * in on scroll has `opacity: 0`, and the visible text next to a control is often `aria-hidden`
	 * (the control carries the name), while the control is offered only once it is in view. Inside a
	 * highlighted element, `aria-hidden` text is kept: it is part of what the element shows (an icon).
	 * Text that is rendered outside the viewport is not hidden.
	 *
	 * @param {Text} textNode - The text node to check.
	 * @param {Object} scope - The scope of its parent element.
	 * @returns {boolean} Whether the text node is hidden.
	 */
	function isTextNodeHidden(textNode, scope) {
		if (scope.clipper !== null) return true;
		const parent = textNode.parentElement;
		if (!isRendered(parent, false)) return true;
		// the content a rendered box skips (`hidden="until-found"`, a closed `<details>` outside its
		// `<summary>`): its elements are not rendered, but its own text nodes have a box
		const box = boxOf(parent);
		if (getCachedComputedStyle(box)?.contentVisibility === "hidden") return true;
		if (localNameOf(box) === "details" && !box.open && closest(parent, "summary")?.parentElement !== box) return true;
		const rects = getTextRects(textNode);
		// no box at all (the text of a `<textarea>`): nothing says it is hidden
		if (rects.length === 0) return false;
		if (rects.every((rect) => rect.width === 0 || rect.height === 0)) return true;
		if (!rects.some(isOnScreen)) return false;
		if (scope.ariaHidden && !scope.inControl) return true;
		return !isRendered(parent, true);
	}

	const textRects = new WeakMap();

	/**
	 * The client rects of a text node, read once per build (`isTextNodeHidden` and `isTextNodeInViewport`
	 * both look at them).
	 *
	 * @param {Text} textNode - The text node.
	 * @returns {DOMRect[]} Its client rects.
	 */
	function getTextRects(textNode) {
		if (textRects.has(textNode)) return textRects.get(textNode);
		const range = DOCUMENT.createRange.call(document);
		range.selectNodeContents(textNode);
		const rects = Array.from(range.getClientRects());
		textRects.set(textNode, rects);
		return rects;
	}

	function isOnScreen(rect) {
		return rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth;
	}

	/**
	 * Checks if a highlight candidate (a visible element) is hidden: clipped away, or on screen with
	 * `opacity: 0` (see `isTextNodeHidden`). A form control with `opacity: 0` is still a control
	 * (custom checkboxes and file inputs are drawn over by their label): only its parent's opacity
	 * hides it. `aria-hidden` does not hide a control the user can see and click (Google Flights'
	 * previous / next day buttons are `aria-hidden`).
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @param {Object} scope - The scope of the element.
	 * @returns {boolean} Whether the element is hidden.
	 */
	function isElementHidden(element, scope) {
		if (scope.clipper !== null && !escapesClip(element, scope.clipper)) return true;
		if (!isOnScreen(getCachedBoundingRect(element))) return false;
		if (!DISABLEABLE_TAGS.has(localNameOf(element))) return !isRendered(element, true);
		const parent = parentElementOf(element);
		return !isRendered(element, false) || (parent !== null && !isRendered(parent, true, false));
	}

	/**
	 * Checks if a text node is in the (expanded) viewport and rendered.
	 *
	 * @param {Text} textNode - The text node to check.
	 * @returns {boolean} Whether the text node is in the viewport.
	 */
	function isTextNodeInViewport(textNode) {
		try {
			// Special case: when viewportExpansion is -1, consider all text nodes as visible
			if (viewportExpansion === -1) {
				// Still check parent visibility for basic filtering
				const parentElement = textNode.parentElement;
				if (!parentElement) return false;

				try {
					return checkVisibilityOf(parentElement, {
						checkOpacity: true,
						checkVisibilityCSS: true,
					});
				} catch (e) {
					// Fallback if checkVisibility is not supported
					const style = window.getComputedStyle(parentElement);
					return style.display !== 'none' &&
						style.visibility !== 'hidden' &&
						style.opacity !== '0';
				}
			}

			const rects = getTextRects(textNode);

			if (!rects || rects.length === 0) {
				return false;
			}

			let isAnyRectVisible = false;
			let isAnyRectInViewport = false;

			for (const rect of rects) {
				// Check size
				if (rect.width > 0 && rect.height > 0) {
					isAnyRectVisible = true;

					// Viewport check for this rect
					if (!(
						rect.bottom < -viewportExpansion ||
						rect.top > window.innerHeight + viewportExpansion ||
						rect.right < -viewportExpansion ||
						rect.left > window.innerWidth + viewportExpansion
					)) {
						isAnyRectInViewport = true;
						break; // Found a visible rect in viewport, no need to check others
					}
				}
			}

			if (!isAnyRectVisible || !isAnyRectInViewport) {
				return false;
			}

			// Check parent visibility
			const parentElement = textNode.parentElement;
			if (!parentElement) return false;

			try {
				return checkVisibilityOf(parentElement, {
					checkOpacity: true,
					checkVisibilityCSS: true,
				});
			} catch (e) {
				// Fallback if checkVisibility is not supported
				const style = window.getComputedStyle(parentElement);
				return style.display !== 'none' &&
					style.visibility !== 'hidden' &&
					style.opacity !== '0';
			}
		} catch (e) {
			console.warn('Error checking text node visibility:', e);
			return false;
		}
	}

	/**
	 * Checks if a zero-size element has a visible descendant with a non-empty box, looking through
	 * zero-size children. Its own empty rect then says nothing about where its content is: an
	 * inline element around a floated or positioned link has an empty rect while the link is laid
	 * out (and visible) elsewhere. Descendants that are laid out but not rendered (e.g. under
	 * `hidden="until-found"`) don't count.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether a visible descendant has a width and a height.
	 */
	function hasVisibleSizedChild(element) {
		for (const child of childrenOf(element)) {
			const rect = getCachedBoundingRect(child);
			if (!rect) continue;
			if (rect.width === 0 || rect.height === 0) {
				if (hasVisibleSizedChild(child)) return true;
				continue;
			}
			if (!checkVisibilityOf ||
				checkVisibilityOf(child, { checkOpacity: true, checkVisibilityCSS: true })) {
				return true;
			}
		}
		return false;
	}

	/**
	 * Checks if an element is accepted.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is accepted.
	 */
	function isElementAccepted(element) {
		if (!element || !tagNameOf(element)) return false;

		// Always accept body and common container elements
		const alwaysAccept = new Set([
			"body", "div", "main", "article", "section", "nav", "header", "footer"
		]);
		const tagName = tagNameOf(element).toLowerCase();

		if (alwaysAccept.has(tagName)) return true;

		const leafElementDenyList = new Set([
			"svg",
			"script",
			"style",
			"link",
			"meta",
			"noscript",
			"template",
		]);

		return !leafElementDenyList.has(tagName);
	}

	/**
	 * Checks if an element is visible.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is visible.
	 */
	function isElementVisible(element) {
		const style = getCachedComputedStyle(element);
		return (
			propertyOf(element, "offsetWidth") > 0 &&
			propertyOf(element, "offsetHeight") > 0 &&
			style?.visibility !== "hidden" &&
			style?.display !== "none"
		);
	}

	let hoverCursorRules = null;

	/**
	 * The `:hover` rules of the page's stylesheets that set a cursor, in stylesheet order, read once per
	 * build: matching each element against every `:hover` rule of a large stylesheet was most of the
	 * build. A rule without a cursor never decides the hover cursor, so it is left out.
	 *
	 * @returns {{baseSelector: string, cursor: string}[]} The rules, with `:hover` removed from their selector.
	 */
	function getHoverCursorRules() {
		if (hoverCursorRules !== null) return hoverCursorRules;
		hoverCursorRules = [];
		for (const stylesheet of Array.from(STYLE_SHEETS)) {
			try {
				for (const rule of Array.from(stylesheet.cssRules || [])) {
					if (!rule.selectorText || !rule.selectorText.includes(':hover')) continue;
					const cursor = rule.style?.cursor;
					if (cursor && cursor !== '') {
						// Remove :hover from selector to test match
						hoverCursorRules.push({ baseSelector: rule.selectorText.replace(/:hover/g, ''), cursor });
					}
				}
			} catch (e) {
				// Skip CORS-protected stylesheets
				continue;
			}
		}
		return hoverCursorRules;
	}

	/**
	 * Checks if an element has a pointer cursor including hover states.
	 * This function analyzes both normal and :hover pseudo-class cursor values
	 * to determine if an element becomes interactive on hover.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {Object} Object containing cursor analysis results.
	 */
	function getElementCursorStates(element) {
		if (!element || nodeTypeOf(element) !== Node.ELEMENT_NODE) {
			return {
				normalCursor: null,
				hoverCursor: null,
				hasHoverRule: false,
				isInteractive: false,
				isHoverInteractive: false
			};
		}

		// Cache the tagName and style lookups
		const tagName = tagNameOf(element).toLowerCase();
		const style = getCachedComputedStyle(element);
		const normalCursor = style?.cursor;

		// Define interactive cursors
		const interactiveCursors = new Set([
			'pointer',    // Link/clickable elements
			'move',       // Movable elements
			'text',       // Text selection
			'grab',       // Grabbable elements
			'grabbing',   // Currently grabbing
			'cell',       // Table cell selection
			'copy',       // Copy operation
			'alias',      // Alias creation
			'all-scroll', // Scrollable content
			'col-resize', // Column resize
			'context-menu', // Context menu available
			'crosshair',  // Precise selection
			'e-resize',   // East resize
			'ew-resize',  // East-west resize
			'help',       // Help available
			'n-resize',   // North resize
			'ne-resize',  // Northeast resize
			'nesw-resize', // Northeast-southwest resize
			'ns-resize',  // North-south resize
			'nw-resize',  // Northwest resize
			'nwse-resize', // Northwest-southeast resize
			'row-resize', // Row resize
			's-resize',   // South resize
			'se-resize',  // Southeast resize
			'sw-resize',  // Southwest resize
			'vertical-text', // Vertical text selection
			'w-resize',   // West resize
			'zoom-in',    // Zoom in
			'zoom-out'    // Zoom out
		]);

		// Define non-interactive cursors
		const nonInteractiveCursors = new Set([
			'not-allowed', // Action not allowed
			'no-drop',     // Drop not allowed
			'wait',        // Processing
			'progress',    // In progress
			'initial',     // Initial value
			'inherit'      // Inherited value
			//? Let's just include all potentially clickable elements that are not specifically blocked
			// 'none',        // No cursor
			// 'default',     // Default cursor
			// 'auto',        // Browser default
		]);

		// Find the first `:hover` rule that matches the element and sets a cursor
		let hoverCursor = null;
		let foundHoverRule = false;

		for (const rule of getHoverCursorRules()) {
			try {
				// Check if element matches the base selector
				if (matches(element, rule.baseSelector)) {
					hoverCursor = rule.cursor;
					foundHoverRule = true;
					break;
				}
			} catch (e) {
				// Skip invalid selectors
				continue;
			}
		}

		// Exclude HTML element
		if (tagNameOf(element).toLowerCase() === "html") {
			return {
				normalCursor: normalCursor,
				hoverCursor: hoverCursor,
				hasHoverRule: foundHoverRule,
				isInteractive: false,
				isHoverInteractive: false
			};
		}

		// Check if normal cursor is interactive
		const isNormalInteractive = normalCursor &&
			!nonInteractiveCursors.has(normalCursor) &&
			interactiveCursors.has(normalCursor);

		// Check if hover cursor is interactive
		const isHoverInteractive = hoverCursor &&
			!nonInteractiveCursors.has(hoverCursor) &&
			interactiveCursors.has(hoverCursor);

		return {
			normalCursor: normalCursor,
			hoverCursor: hoverCursor,
			hasHoverRule: foundHoverRule,
			isInteractive: isNormalInteractive,
			isHoverInteractive: isHoverInteractive
		};
	}

	const pointerCache = new WeakMap();

	/**
	 * Checks if an element has a pointer cursor (clickable/interactive cursor),
	 * including hover states. This function focuses specifically on cursor-based detection.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element has a pointer cursor (normal or hover).
	 */
	function isPointerElementWithHover(element) {
		// asked up to three times per element (`isInteractiveElement`, `pointerElement`, the distinct interaction check)
		if (pointerCache.has(element)) return pointerCache.get(element);
		const cursorStates = getElementCursorStates(element);

		// Element is interactive if it has pointer cursor in normal state OR hover state
		const result = cursorStates.isInteractive || cursorStates.isHoverInteractive;
		pointerCache.set(element, result);
		return result;
	}

	const NON_INTERACTIVE_CURSORS = new Set(['not-allowed', 'no-drop', 'wait', 'progress']);

	function getDisabledReason(element, style) {
		if (style?.cursor && NON_INTERACTIVE_CURSORS.has(style.cursor)) {
			return 'DISABLED_CURSOR';
		}
		if (
			hasAttribute(element, 'disabled') ||
			getAttribute(element, 'disabled') === 'true' ||
			getAttribute(element, 'disabled') === '' ||
			getAttribute(element, 'aria-disabled') === 'true'
		) {
			return 'DISABLED_ATTRIBUTE';
		}
		// `:disabled` also matches the controls of a disabled `<fieldset>`, whose `.disabled` is false
		if (propertyOf(element, "disabled") || matches(element, ':disabled')) {
			return 'DISABLED_PROPERTY';
		}
		if (propertyOf(element, "inert") || hasAttribute(element, 'inert') || getAttribute(element, 'aria-inert') === 'true') {
			return 'DISABLED_INERT';
		}
		return null;
	}


	/**
	 * Checks if an element is interactive (general interactivity detection).
	 * This function focuses on element types, roles, attributes, and event listeners.
	 *
	 * lots of comments, and uncommented code - to show the logic of what we already tried
	 *
	 * One of the things we tried at the beginning was also to use event listeners, and other fancy class, style stuff -> what actually worked best was just combining most things with computed cursor style :)
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @param {boolean} usePointerCursor - Whether a pointer cursor alone makes the element interactive.
	 */
	function isInteractiveElement(element, usePointerCursor = enable_pointer_elements) {
		if (!element || nodeTypeOf(element) !== Node.ELEMENT_NODE) {
			return false;
		}

		// Cache the tagName and style lookups
		const tagName = tagNameOf(element).toLowerCase();
		const style = getCachedComputedStyle(element);

		const disabledReason = getDisabledReason(element, style);
		if (disabledReason !== null) {
			return disabledReason;
		}

		// Check if element has pointer cursor using the dedicated function
		let isInteractiveCursor = isPointerElementWithHover(element);

		// Genius fix for almost all interactive elements
		if (isInteractiveCursor && usePointerCursor) {
			return true;
		}

		// Define non-interactive cursors for form element checks
		const nonInteractiveCursors = new Set([
			'not-allowed', // Action not allowed
			'no-drop',     // Drop not allowed
			'wait',        // Processing
			'progress'     // In progress
			//? Let's just include all potentially clickable elements that are not specifically blocked
			// 'none',        // No cursor
			// 'default',     // Default cursor
			// 'auto',        // Browser default
		]);

		const interactiveElements = new Set([
			"a",          // Links
			"button",     // Buttons
			"input",      // All input types (text, checkbox, radio, etc.)
			"select",     // Dropdown menus
			"textarea",   // Text areas
			"details",    // Expandable details
			"summary",    // Summary element (clickable part of details)
			"option",     // Select options
			"optgroup",   // Option groups
			// These last 3 should be already covered by "pointer" elements if they are indeed interactive
			//"label",      // Form labels (often clickable)
			//"fieldset",   // Form fieldsets (can be interactive with legend)
			//"ylegend",     // Fieldset legends
		]);

		// Define explicit disable attributes and properties
		const explicitDisableTags = new Set([
			'disabled',           // Standard disabled attribute
			// 'aria-disabled',      // ARIA disabled state
			// 'readonly',          // Read-only state
			// 'aria-readonly',     // ARIA read-only state
			// 'aria-hidden',       // Hidden from accessibility
			// 'hidden',            // Hidden attribute
			// 'inert',             // Inert attribute
			// 'aria-inert',        // ARIA inert state
			// 'tabindex="-1"',     // Removed from tab order
			// 'aria-hidden="true"' // Hidden from screen readers
		]);

		// handle inputs, select, checkbox, radio, textarea, button and make sure they are not cursor style disabled/not-allowed
		if (interactiveElements.has(tagName)) {
			// Check for non-interactive cursor
			if (style?.cursor && nonInteractiveCursors.has(style.cursor)) {
				return 'DISABLED_CURSOR';
			}

			// Check for explicit disable attributes
			for (const disableTag of explicitDisableTags) {
				if (hasAttribute(element, disableTag) ||
					getAttribute(element, disableTag) === 'true' ||
					getAttribute(element, disableTag) === '') {
					return 'DISABLED_ATTRIBUTE';
				}
			}

			// Check for disabled property on form elements
			if (propertyOf(element, "disabled")) {
				return 'DISABLED_PROPERTY';
			}

			// Check for inert property
			if (propertyOf(element, "inert")) {
				return 'DISABLED_INERT';
			}

			return true;
		}

		const role = getAttribute(element, "role");
		const ariaRole = getAttribute(element, "aria-role");

		// Check for contenteditable attribute
		if (getAttribute(element, "contenteditable") === "true" || propertyOf(element, "isContentEditable")) {
			return true;
		}

		// Added enhancement to capture dropdown interactive elements
		if (classListOf(element) && (
			classListOf(element).contains("button") ||
			classListOf(element).contains('dropdown-toggle') ||
			getAttribute(element, 'data-index') ||
			getAttribute(element, 'data-toggle') === 'dropdown' ||
			getAttribute(element, 'aria-haspopup') === 'true'
		)) {
			return true;
		}


		const interactiveRoles = new Set([
			'button',           // Directly clickable element
			// 'link',            // Clickable link
			'menu',            // Menu container (ARIA menus)
			'menubar',         // Menu bar container
			'menuitem',        // Clickable menu item
			'menuitemradio',   // Radio-style menu item (selectable)
			'menuitemcheckbox', // Checkbox-style menu item (toggleable)
			'radio',           // Radio button (selectable)
			'checkbox',        // Checkbox (toggleable)
			'tab',             // Tab (clickable to switch content)
			'switch',          // Toggle switch (clickable to change state)
			'slider',          // Slider control (draggable)
			'spinbutton',      // Number input with up/down controls
			'combobox',        // Dropdown with text input
			'searchbox',       // Search input field
			'textbox',         // Text input field
			'listbox',         // Selectable list
			'option',          // Selectable option in a list
			'scrollbar'        // Scrollable control
		]);


		// Basic role/attribute checks
		const hasInteractiveRole =
			interactiveElements.has(tagName) ||
			(role && interactiveRoles.has(role)) ||
			(ariaRole && interactiveRoles.has(ariaRole));

		if (hasInteractiveRole) return true;

		// the focusable cells of a grid (the days of a date picker), which act on click; the empty cells
		// before the first day of a month are fillers
		if (hasAttribute(element, "tabindex") && isGridCell(element) && (propertyOf(element, "textContent") || "").trim() !== "") return true;


		// check whether element has event listeners by window.getEventListeners
		try {
			if (typeof getEventListeners === 'function') {
				const listeners = getEventListeners(element);
				const mouseEvents = ['click', 'mousedown', 'mouseup', 'dblclick'];
				for (const eventType of mouseEvents) {
					if (listeners[eventType] && listeners[eventType].length > 0) {
						return true; // Found a mouse interaction listener
					}
				}
			}

			const getEventListenersForNode = ownerDocumentOf(element)?.defaultView?.getEventListenersForNode || window.getEventListenersForNode;
			if (typeof getEventListenersForNode === 'function') {
				const listeners = getEventListenersForNode(element);
				const interactionEvents = ['click', 'mousedown', 'mouseup', 'keydown', 'keyup', 'submit', 'change', 'input', 'focus', 'blur'];
				for (const eventType of interactionEvents) {
					for (const listener of listeners) {
						if (listener.type === eventType) {
							return true; // Found a common interaction listener
						}
					}
				}
			}
			// Fallback: Check common event attributes if getEventListeners is not available (getEventListeners doesn't work in page.evaluate context)
			for (const attr of CLICK_HANDLER_ATTRS) {
				if (hasAttribute(element, attr) || typeof propertyOf(element, attr) === 'function') {
					return true;
				}
			}
		} catch (e) {
			// console.warn(`Could not check event listeners for ${element.tagName}:`, e);
			// If checking listeners fails, rely on other checks
		}

		return false
	}


	/**
	 * Checks if an element is a cell of an interactive grid: `role="gridcell"`, or a `<td>` of a table with
	 * `role="grid"` or `"treegrid"`. Unlike the cells of a data table, they are widgets the user picks
	 * (https://www.w3.org/WAI/ARIA/apg/patterns/grid/).
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is a grid cell.
	 */
	function isGridCell(element) {
		const role = getRole(element);
		if (role === "gridcell") return true;
		if (role !== "cell" || localNameOf(element) !== "td") return false;
		const table = closest(element, "table");
		const tableRole = table === null ? undefined : getAttribute(table, "role")?.trim().toLowerCase();
		return tableRole === "grid" || tableRole === "treegrid";
	}

	/**
	 * Checks if an element is the topmost element at its position.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is the topmost element at its position.
	 */
	function isTopElement(element) {
		// Special case: when viewportExpansion is -1, consider all elements as "top" elements
		if (viewportExpansion === -1) {
			return true;
		}

		const rects = getCachedClientRects(element); // Replace element.getClientRects()

		if (!rects || rects.length === 0) {
			return false; // No geometry, cannot be top
		}

		let isAnyRectInViewport = false;
		for (const rect of rects) {
			// Use the same logic as isInExpandedViewport check
			if (rect.width > 0 && rect.height > 0 && !( // Only check non-empty rects
				rect.bottom < -viewportExpansion ||
				rect.top > window.innerHeight + viewportExpansion ||
				rect.right < -viewportExpansion ||
				rect.left > window.innerWidth + viewportExpansion
			)) {
				isAnyRectInViewport = true;
				break;
			}
		}

		if (!isAnyRectInViewport) {
			return false; // All rects are outside the viewport area
		}


		// Find the correct document context and root element
		let doc = ownerDocumentOf(element);

		// If we're in an iframe, elements are considered top by default
		if (doc !== window.document) {
			return true;
		}

		// For shadow DOM, we need to check within its own root context
		const shadowRoot = getRootNode(element);
		if (shadowRoot instanceof ShadowRoot) {
			const centerX = rects[Math.floor(rects.length / 2)].left + rects[Math.floor(rects.length / 2)].width / 2;
			const centerY = rects[Math.floor(rects.length / 2)].top + rects[Math.floor(rects.length / 2)].height / 2;

			try {
				const topEl = shadowRoot.elementFromPoint(centerX, centerY);
				if (!topEl) return false;

				let current = topEl;
				while (current && current !== shadowRoot) {
					if (current === element) return true;
					current = parentElementOf(current);
				}
				return false;
			} catch (e) {
				return true;
			}
		}

		// For elements in viewport, check if they're topmost
		const centerX = rects[Math.floor(rects.length / 2)].left + rects[Math.floor(rects.length / 2)].width / 2;
		const centerY = rects[Math.floor(rects.length / 2)].top + rects[Math.floor(rects.length / 2)].height / 2;

		try {
			const topEl = DOCUMENT.elementFromPoint.call(document, centerX, centerY);
			if (!topEl) return false;

			let current = topEl;
			while (current && current !== DOCUMENT_ELEMENT) {
				if (current === element) return true;
				current = parentElementOf(current);
			}
			return false;
		} catch (e) {
			return true;
		}
	}

	const OFFSCREEN_CONTROL_TAGS = new Set(['a', 'button', 'input', 'select', 'textarea', 'option']);
	// form fields, named by the label next to them rather than by their content
	const FIELD_TAGS = new Set(['input', 'select', 'textarea']);

	/**
	 * Checks if an element is a link, button, form field or option by its tag or ARIA role: the controls
	 * described above or below the viewport. Pointer cursors are not looked at there: the generic clickables
	 * they find are not described off-screen, and reading every `:hover` rule of the page for each element
	 * below the fold (`getElementCursorStates`) would make the walk several times slower.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is a control by its tag or role.
	 */
	function isOffscreenCandidate(element) {
		const role = getAttribute(element, 'role');
		if (role !== null && role !== '') return INTERACTIVE_ROLES.has(role);
		return OFFSCREEN_CONTROL_TAGS.has(tagNameOf(element).toLowerCase());
	}

	/**
	 * Checks if an element is above or below the (expanded) viewport, where scrolling the page brings it:
	 * the center of its middle box (where `isTopElement` looks for it) is outside the viewport vertically,
	 * and the element is across it horizontally. A control cut by the edge of the viewport, with its center
	 * outside, is then off-screen rather than in view. Content left or right of the viewport is not:
	 * scrolling does not reveal it (off-canvas menus, skip links, carousel slides).
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is above or below the viewport.
	 */
	function isAboveOrBelowViewport(element) {
		if (viewportExpansion === -1) return false;
		const rects = getCachedClientRects(element);
		const rect = getCachedBoundingRect(element);
		if (!rects || rects.length === 0 || !rect || rect.width === 0 || rect.height === 0) return false;
		const middle = rects[Math.floor(rects.length / 2)];
		const centerY = middle.top + middle.height / 2;
		const outside = centerY < -viewportExpansion || centerY > window.innerHeight + viewportExpansion;
		const across = rect.right > -viewportExpansion && rect.left < window.innerWidth + viewportExpansion;
		return outside && across;
	}

	/**
	 * Checks if an element is a control that scrolling the page can bring into view (see `handleHighlighting`).
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is an off-screen control.
	 */
	function isOffscreenControl(element) {
		// not rendered (in a closed `<details>`, `hidden="until-found"`), or out of reach of scrolling:
		// `isTopElement` rules these out in view
		return isOffscreenCandidate(element) && isAboveOrBelowViewport(element) && isRendered(element, false) &&
			!isOutOfReach(element);
	}

	/**
	 * Whether the scrolled area of a box starts at its end along an axis: at the bottom of a
	 * `column-reverse` flex box, at the right of a right-to-left box (or a `row-reverse` left-to-right
	 * one), where Chromium's scroll offsets go negative. Null when it is not known (vertical writing
	 * modes, `wrap-reverse`).
	 *
	 * @param {CSSStyleDeclaration} style - The computed style of the box.
	 * @param {boolean} vertical - The axis: vertical or horizontal.
	 * @returns {boolean | null} Whether the scrolled area starts at the end, or null.
	 */
	function scrollStartsAtEnd(style, vertical) {
		if (style.writingMode !== "horizontal-tb") return null;
		const flex = style.display === "flex" || style.display === "inline-flex";
		if (flex && style.flexWrap === "wrap-reverse") return null;
		if (vertical) return flex && style.flexDirection === "column-reverse";
		const rtl = style.direction === "rtl";
		return flex && style.flexDirection === "row-reverse" ? !rtl : rtl;
	}

	/**
	 * Where a box that clips its overflow can show its content along an axis, in viewport coordinates:
	 * its own box, or, along an axis it scrolls (`auto` or `scroll`, with overflowing content), the whole
	 * area it scrolls through. Its scroll sizes are scaled to its box on screen (`transform: scale`).
	 * Null when the box does not clip along the axis (`overflow: visible`, or no box of its own to clip
	 * with: `display: contents` or `inline`, as in `clipsToNothing`), or when where its scrolled area lies
	 * is not known.
	 *
	 * @param {HTMLElement} box - The box.
	 * @param {DOMRect} rect - Its bounding rect.
	 * @param {CSSStyleDeclaration} style - Its computed style.
	 * @param {boolean} vertical - The axis: vertical or horizontal.
	 * @returns {{start: number, end: number, scrolls: boolean} | null} The range, and whether the box scrolls.
	 */
	function visibleRange(box, rect, style, vertical) {
		const overflow = vertical ? style.overflowY : style.overflowX;
		if (overflow === "visible" || style.display === "contents" || style.display === "inline") return null;
		if (!getCachedClientRects(box)?.length) return null;
		const [rectStart, rectEnd] = vertical ? [rect.top, rect.bottom] : [rect.left, rect.right];
		const scrollSize = vertical ? propertyOf(box, "scrollHeight") : propertyOf(box, "scrollWidth");
		const clientSize = vertical ? propertyOf(box, "clientHeight") : propertyOf(box, "clientWidth");
		const scrolls = (overflow === "auto" || overflow === "scroll") && scrollSize > clientSize;
		if (!scrolls) return { start: rectStart, end: rectEnd, scrolls };
		const atEnd = scrollStartsAtEnd(style, vertical);
		if (atEnd === null) return { start: -Infinity, end: Infinity, scrolls };
		const layoutSize = vertical ? propertyOf(box, "offsetHeight") : propertyOf(box, "offsetWidth");
		const scale = layoutSize > 0 ? (rectEnd - rectStart) / layoutSize : 1;
		const clientStart = (vertical ? propertyOf(box, "clientTop") : propertyOf(box, "clientLeft")) * scale;
		const offset = (vertical ? propertyOf(box, "scrollTop") : propertyOf(box, "scrollLeft")) * scale;
		// the edge the scrolled area starts from, where the current scroll offset has moved it
		const origin = rectStart + clientStart - offset + (atEnd ? clientSize * scale : 0);
		return atEnd ?
			{ start: origin - scrollSize * scale, end: origin, scrolls } :
			{ start: origin, end: origin + scrollSize * scale, scrolls };
	}

	/**
	 * Checks if scrolling cannot bring an element above or below the viewport into view:
	 * - it is laid out outside where an ancestor that clips its overflow can show it: outside its box
	 *   (`overflow: hidden` or `clip`, as carousels and "show more" sections are, or an axis an `auto`
	 *   box has nothing to scroll on), or outside the area a scrollable ancestor scrolls through (before
	 *   the start of its content);
	 * - it is fixed, or inside a fixed element, outside the viewport (a closed slide-in panel): scrolling
	 *   the page does not move it. A fixed panel on screen that scrolls can still bring it into view, and a
	 *   sticky element scrolls with the page until it sticks: both are reachable.
	 *
	 * A scrollable ancestor can bring the element anywhere in its box along the axes it scrolls: the
	 * ancestors above it are checked against that box (and with its position, for what it escapes).
	 * `<body>` and `<html>` are not checked: their overflow is the page's.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether scrolling cannot reveal the element.
	 */
	function isOutOfReach(element) {
		const elementRect = getCachedBoundingRect(element);
		let rect = { top: elementRect.top, bottom: elementRect.bottom, left: elementRect.left, right: elementRect.right };
		// the element whose box `rect` is: the element, or the scrollable ancestor it can be scrolled anywhere in
		let owner = element;
		for (let ancestor = element; ancestor && ancestor !== BODY; ancestor = reachAncestor(ancestor)) {
			const style = getCachedComputedStyle(ancestor);
			if (!style) continue;
			const box = ancestor === element ? null : getCachedBoundingRect(ancestor);
			if (box && !escapesClip(owner, ancestor)) {
				const y = visibleRange(ancestor, box, style, true);
				const x = visibleRange(ancestor, box, style, false);
				if (y !== null && (rect.bottom <= y.start || rect.top >= y.end)) return true;
				if (x !== null && (rect.right <= x.start || rect.left >= x.end)) return true;
				const scrollsY = y !== null && y.scrolls;
				const scrollsX = x !== null && x.scrolls;
				if (scrollsY || scrollsX) {
					rect = {
						top: scrollsY ? box.top : rect.top,
						bottom: scrollsY ? box.bottom : rect.bottom,
						left: scrollsX ? box.left : rect.left,
						right: scrollsX ? box.right : rect.right,
					};
					owner = ancestor;
				}
			}
			// after its own scrolling: a fixed panel on screen can be scrolled to what it holds
			if (style.position === "fixed") {
				return rect.bottom <= -viewportExpansion || rect.top >= window.innerHeight + viewportExpansion ||
					rect.right <= -viewportExpansion || rect.left >= window.innerWidth + viewportExpansion;
			}
		}
		return false;
	}

	const reachAncestors = new WeakMap();

	/**
	 * The nearest ancestor of an element that `isOutOfReach` has to look at: one that clips its overflow
	 * (`visibleRange` is not null along an axis) or is fixed, below `<body>`. The others change nothing
	 * there. Remembered per element: the off-screen controls of a page share most of their ancestors.
	 *
	 * @param {HTMLElement} element - The element.
	 * @returns {HTMLElement | null} The ancestor, or null when there is none.
	 */
	function reachAncestor(element) {
		if (reachAncestors.has(element)) return reachAncestors.get(element);
		let ancestor = parentElementOf(element);
		if (ancestor === BODY) ancestor = null;
		if (ancestor !== null) {
			const style = getCachedComputedStyle(ancestor);
			const rect = getCachedBoundingRect(ancestor);
			const matters = style.position === "fixed" ||
				visibleRange(ancestor, rect, style, true) !== null || visibleRange(ancestor, rect, style, false) !== null;
			if (!matters) ancestor = reachAncestor(ancestor);
		}
		reachAncestors.set(element, ancestor);
		return ancestor;
	}

	const EXCLUDED_CONTENT ="svg, script, style, link, meta, noscript, template";

	/**
	 * Checks if an element has text that the page description keeps: a non-empty text node that is
	 * rendered and not inside an element the tree leaves out (see `isElementAccepted`). The `<title>` of
	 * an `<svg>` icon is in `textContent`, but not in the description.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element has text in the description.
	 */
	function hasDescribedText(element) {
		const walker = DOCUMENT.createTreeWalker.call(document, element, NodeFilter.SHOW_TEXT);
		for (let text = walker.nextNode(); text !== null; text = walker.nextNode()) {
			const parent = text.parentElement;
			if (!parent || !text.textContent.trim()) continue;
			const excluded = closest(parent, EXCLUDED_CONTENT);
			if (excluded !== null && contains(element, excluded)) continue;
			if (isRendered(parent, false)) return true;
		}
		return false;
	}

	/**
	 * Checks if an element is within the expanded viewport.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @param {number} viewportExpansion - The viewport expansion.
	 * @returns {boolean} Whether the element is within the expanded viewport.
	 */
	function isInExpandedViewport(element, viewportExpansion) {
		if (viewportExpansion === -1) {
			return true;
		}

		const rects = getClientRects(element); // Use getClientRects

		if (!rects || rects.length === 0) {
			// Fallback to getBoundingClientRect if getClientRects is empty,
			// useful for elements like <svg> that might not have client rects but have a bounding box.
			const boundingRect = getCachedBoundingRect(element);
			if (!boundingRect || boundingRect.width === 0 || boundingRect.height === 0) {
				return false;
			}
			return !(
				boundingRect.bottom < -viewportExpansion ||
				boundingRect.top > window.innerHeight + viewportExpansion ||
				boundingRect.right < -viewportExpansion ||
				boundingRect.left > window.innerWidth + viewportExpansion
			);
		}

		// Check if *any* client rect is within the viewport
		for (const rect of rects) {
			if (rect.width === 0 || rect.height === 0) continue; // Skip empty rects

			if (!(
				rect.bottom < -viewportExpansion ||
				rect.top > window.innerHeight + viewportExpansion ||
				rect.right < -viewportExpansion ||
				rect.left > window.innerWidth + viewportExpansion
			)) {
				return true; // Found at least one rect in the viewport
			}
		}

		return false; // No rects were found in the viewport
	}

	// /**
	//  * Gets the effective scroll of an element.
	//  *
	//  * @param {HTMLElement} element - The element to get the effective scroll for.
	//  * @returns {Object} The effective scroll of the element.
	//  */
	// function getEffectiveScroll(element) {
	//   let currentEl = element;
	//   let scrollX = 0;
	//   let scrollY = 0;

	//   while (currentEl && currentEl !== document.documentElement) {
	//     if (currentEl.scrollLeft || currentEl.scrollTop) {
	//       scrollX += currentEl.scrollLeft;
	//       scrollY += currentEl.scrollTop;
	//     }
	//     currentEl = currentEl.parentElement;
	//   }

	//   scrollX += window.scrollX;
	//   scrollY += window.scrollY;

	//   return { scrollX, scrollY };
	// }

	/**
	 * Checks if an element is an interactive candidate.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is an interactive candidate.
	 */
	function isInteractiveCandidate(element) {
		if (!element || nodeTypeOf(element) !== Node.ELEMENT_NODE) return false;

		const tagName = tagNameOf(element).toLowerCase();

		// Fast-path for common interactive elements
		const interactiveElements = new Set([
			"a", "button", "input", "select", "textarea", "details", "summary", "label"
		]);

		if (interactiveElements.has(tagName)) return true;

		// Quick attribute checks without getting full lists
		const hasQuickInteractiveAttr = hasAttribute(element, "onclick") ||
			hasAttribute(element, "role") ||
			hasAttribute(element, "tabindex") ||
			hasAttribute(element, "aria-") ||
			hasAttribute(element, "data-action") ||
			getAttribute(element, "contenteditable") === "true";

		return hasQuickInteractiveAttr;
	}

	// --- Define constants for distinct interaction check ---
	const DISTINCT_INTERACTIVE_TAGS = new Set([
		'button', 'input', 'select', 'textarea', 'summary', 'details', 'label', 'option'
	]);
	const INTERACTIVE_ROLES = new Set([
		'button', 'link', 'menuitem', 'menuitemradio', 'menuitemcheckbox',
		'radio', 'checkbox', 'tab', 'switch', 'slider', 'spinbutton',
		'combobox', 'searchbox', 'textbox', 'listbox', 'option', 'scrollbar'
	]);


	/**
	 * Heuristically determines if an element should be considered as independently interactive,
	 * even if it's nested inside another interactive container.
	 *
	 * This function helps detect deeply nested actionable elements (e.g., menu items within a button)
	 * that may not be picked up by strict interactivity checks.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is heuristically interactive.
	 */
	function isHeuristicallyInteractive(element) {
		if (!element || nodeTypeOf(element) !== Node.ELEMENT_NODE) return false;

		// Skip non-visible elements early for performance
		if (!isElementVisible(element)) return false;

		// Check for common attributes that often indicate interactivity
		const hasInteractiveAttributes =
			hasAttribute(element, 'role') ||
			hasAttribute(element, 'tabindex') ||
			hasAttribute(element, 'onclick') ||
			typeof propertyOf(element, "onclick") === 'function';

		// Check for semantic class names suggesting interactivity
		const hasInteractiveClass = /\b(btn|clickable|menu|item|entry|link)\b/i.test(propertyOf(element, "className") || '');

		// Determine whether the element is inside a known interactive container
		const isInKnownContainer = Boolean(
			closest(element, 'button,a,[role="button"],.menu,.dropdown,.list,.toolbar')
		);

		// Ensure the element has at least one visible child (to avoid marking empty wrappers)
		const hasVisibleChildren = [...childrenOf(element)].some(isElementVisible);

		// Avoid highlighting elements whose parent is <body> (top-level wrappers)
		const isParentBody = parentElementOf(element) === BODY;

		// `cursor` is inherited: the text and icon wrappers inside a link or a button have its pointer
		// cursor, which says nothing about them
		const parentCursor = parentElementOf(element) ? getCachedComputedStyle(parentElementOf(element))?.cursor : undefined;
		const hasOwnCursor = getCachedComputedStyle(element)?.cursor !== parentCursor;

		return (
			(isInteractiveElement(element, enable_pointer_elements && hasOwnCursor) || hasInteractiveAttributes || hasInteractiveClass) &&
			hasVisibleChildren &&
			isInKnownContainer &&
			!isParentBody
		);
	}


	/**
	 * Checks if an element likely represents a distinct interaction
	 * separate from its parent (if the parent is also interactive).
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @param {boolean} ignoreDisabled - Whether to answer as if the element were enabled.
	 * @returns {boolean} Whether the element is a distinct interaction.
	 */
	function isElementDistinctInteraction(element, ignoreDisabled = false) {
		if (!element || nodeTypeOf(element) !== Node.ELEMENT_NODE) {
			return false;
		}

		if (!ignoreDisabled && getDisabledReason(element, getCachedComputedStyle(element)) !== null) {
			return false;
		}

		const tagName = tagNameOf(element).toLowerCase();
		const role = getAttribute(element, 'role');

		// Check if it's an iframe - always distinct boundary
		if (tagName === 'iframe') {
			return true;
		}

		// Check tag name
		if (DISTINCT_INTERACTIVE_TAGS.has(tagName)) {
			return true;
		}
		// Check interactive roles
		if (role && INTERACTIVE_ROLES.has(role)) {
			return true;
		}
		// a link goes to a page of its own: the clickable card around it may not (its handler can be
		// wired to part of the card, or not yet attached)
		if (getRole(element) === 'link') {
			return true;
		}
		// Check contenteditable
		if (propertyOf(element, "isContentEditable") || getAttribute(element, 'contenteditable') === 'true') {
			return true;
		}
		// Check for common testing/automation attributes
		if (hasAttribute(element, 'data-testid') || hasAttribute(element, 'data-cy') || hasAttribute(element, 'data-test')) {
			return true;
		}
		// Check for explicit onclick handler (attribute or property)
		if (hasAttribute(element, 'onclick') || typeof propertyOf(element, "onclick") === 'function') {
			return true;
		}

		// return false

		// Check for other common interaction event listeners
		try {
			const getEventListenersForNode = ownerDocumentOf(element)?.defaultView?.getEventListenersForNode || window.getEventListenersForNode;
			if (typeof getEventListenersForNode === 'function') {
				const listeners = getEventListenersForNode(element);
				const interactionEvents = ['click', 'mousedown', 'mouseup', 'keydown', 'keyup', 'submit', 'change', 'input', 'focus', 'blur'];
				for (const eventType of interactionEvents) {
					for (const listener of listeners) {
						if (listener.type === eventType) {
							return true; // Found a common interaction listener
						}
					}
				}
			}
			// Fallback: Check common event attributes if getEventListeners is not available (getEventListenersForNode doesn't work in page.evaluate context)
			const commonEventAttrs = ['onmousedown', 'onmouseup', 'onkeydown', 'onkeyup', 'onsubmit', 'onchange', 'oninput', 'onfocus', 'onblur'];
			if (commonEventAttrs.some(attr => hasAttribute(element, attr))) {
				return true;
			}
		} catch (e) {
			// console.warn(`Could not check event listeners for ${element.tagName}:`, e);
			// If checking listeners fails, rely on other checks
		}



		// if the element is not strictly interactive but appears clickable based on heuristic signals
		if (isHeuristicallyInteractive(element)) {
			return true;
		}

		// Default to false: if it's interactive but doesn't match above,
		// assume it triggers the same action as the parent.
		return false;
	}
	// --- End distinct interaction check ---

	/**
	 * Handles the logic for deciding whether to highlight an element and performing the highlight.
	 * @param {
	  {
		  tagName: string;
		  attributes: Record<string, string>;
		  xpath: any;
		  children: never[];
		  isVisible?: boolean;
		  isTopElement?: boolean;
		  isInteractive?: boolean;
		  isInViewport?: boolean;
		  highlightIndex?: number;
		  shadowRoot?: boolean;
	 }} nodeData - The node data object.
	 * @param {HTMLElement} node - The node to highlight.
	 * @param {HTMLElement | null} parentIframe - The parent iframe node.
	 * @param {boolean} isParentHighlighted - Whether the parent node is highlighted.
	 * @param {boolean} isOffscreen - Whether the node is a control above or below the viewport.
	 * @returns {boolean} Whether the element was highlighted.
	 */
	function handleHighlighting(nodeData, node, parentIframe, isParentHighlighted, isOffscreen = false) {
		if (!nodeData.isInteractive) return false; // Not interactive, definitely don't highlight

		let shouldHighlight = false;
		if (!isParentHighlighted) {
			// Parent wasn't highlighted, this interactive node can be highlighted.
			shouldHighlight = true;
		} else {
			// Parent *was* highlighted. Only highlight this node if it represents a distinct interaction.
			if (isElementDistinctInteraction(node)) {
				shouldHighlight = true;
			} else {
				// console.log(`Skipping highlight for ${nodeData.tagName} (parent highlighted)`);
				shouldHighlight = false;
			}
		}

		if (shouldHighlight) {
			// Check viewport status before assigning index and highlighting
			nodeData.isInViewport = isInExpandedViewport(node, viewportExpansion);

			// When viewportExpansion is -1, all interactive elements should get a highlight index
			// regardless of viewport status
			if (!isOffscreen && (nodeData.isInViewport || viewportExpansion === -1)) {
				nodeData.highlightIndex = highlightIndex++;
				if (ELEMENTS) ELEMENTS[nodeData.highlightIndex] = node;

				if (doHighlightElements) {
					if (focusHighlightIndex >= 0) {
						if (focusHighlightIndex === nodeData.highlightIndex) {
							nodeData.bbox = highlightElement(node, parentIframe);
						}
					} else {
						nodeData.bbox = highlightElement(node, parentIframe);
					}
					return true; // Successfully highlighted
				}
			} else if (isOffscreen || (!nodeData.isInViewport && isOffscreenControl(node))) {
				// described like a highlighted element (its nested elements too), but without a highlight
				// index: it offers no action until it is scrolled into view
				nodeData.offscreen = true;
				return true;
			}
		}

		return false; // Did not highlight
	}

	const DISABLEABLE_TAGS = new Set(['button', 'input', 'select', 'textarea']);

	/**
	 * Checks if an element is a control that cannot be used yet: a form control that is `disabled`
	 * (or inside a disabled `<fieldset>`), or a control or widget with `aria-disabled="true"`.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is a disabled control.
	 */
	function isDisabledControl(element) {
		const tagName = tagNameOf(element).toLowerCase();
		if (DISABLEABLE_TAGS.has(tagName) && matches(element, ':disabled')) return true;
		if (getAttribute(element, 'aria-disabled') !== 'true') return false;
		const role = getAttribute(element, 'role');
		return DISABLEABLE_TAGS.has(tagName) ||
			(tagName === 'a' && hasAttribute(element, 'href')) ||
			(role !== null && INTERACTIVE_ROLES.has(role));
	}

	/**
	 * Marks a disabled control as `disabled` when it would be highlighted if it were enabled (same
	 * nesting rules, in the viewport or above or below it). It gets no highlight index: it is described, but
	 * offers no action.
	 *
	 * @param {Object} nodeData - The node data object.
	 * @param {HTMLElement} node - The node to check.
	 * @param {boolean} isParentHighlighted - Whether the parent node is highlighted.
	 * @returns {boolean} Whether the node was marked.
	 */
	function handleDisabledControl(nodeData, node, isParentHighlighted) {
		if (!isDisabledControl(node)) return false;
		if (isParentHighlighted && !isElementDistinctInteraction(node, true)) return false;
		if (!isInExpandedViewport(node, viewportExpansion) && !isAboveOrBelowViewport(node)) return false;
		nodeData.disabled = true;
		return true;
	}

	/**
	 * The XPath of an element as the payload gives it: `xpathStep`, its last step, when its XPath is the XPath
	 * of its parent in the payload followed by that step (the Python builder joins them back), else the whole
	 * `xpath` (the children of `<body>`, whose XPath is `/body`, and of shadow roots). Whole XPaths were most
	 * of the payload.
	 *
	 * @param {string} xpath - The XPath of the element.
	 * @param {string | null} parentXPath - The XPath of its parent in the payload, or null.
	 * @returns {{xpathStep: string} | {xpath: string}} The payload field.
	 */
	function payloadXPath(xpath, parentXPath) {
		if (parentXPath !== null && xpath.startsWith(`${parentXPath}/`)) {
			const step = xpath.slice(parentXPath.length + 1);
			if (step.length > 0 && !step.includes("/")) return { xpathStep: step };
		}
		return { xpath };
	}

	/**
	 * Creates a node data object for a given node and its descendants.
	 *
	 * @param {HTMLElement} node - The node to process.
	 * @param {HTMLElement | null} parentIframe - The parent iframe node.
	 * @param {boolean} isParentHighlighted - Whether the parent node is highlighted.
	 * @param {Object} scope - What hides the node (see `VISIBLE_SCOPE`).
	 * @param {string | null} parentXPath - The XPath of the node's parent in the payload (see `payloadXPath`).
	 * @returns {string | null} The ID of the node data object, or null if the node is not processed.
	 */
	function buildDomTree(node, parentIframe = null, isParentHighlighted = false, scope = VISIBLE_SCOPE, parentXPath = null) {
		// Fast rejection checks first
		if (!node || (nodeTypeOf(node) !== Node.ELEMENT_NODE && nodeTypeOf(node) !== Node.TEXT_NODE) ||
			(nodeTypeOf(node) === Node.ELEMENT_NODE && idOf(node) === HIGHLIGHT_CONTAINER_ID)) {
			return null;
		}

		// Special handling for root node (body)
		if (node === BODY) {
			const nodeData = {
				tagName: 'body',
				attributes: {},
				xpath: '/body',
				children: [],
			};

			// Process children of body
			for (const child of childNodesOf(node)) {
				const domElement = buildDomTree(child, parentIframe, false, VISIBLE_SCOPE, nodeData.xpath); // Body's children have no highlighted parent initially
				if (domElement) nodeData.children.push(domElement);
			}

			const id = `${ID.current++}`;
			DOM_HASH_MAP[id] = nodeData;
			return id;
		}

		// Early bailout for non-element nodes except text
		if (nodeTypeOf(node) !== Node.ELEMENT_NODE && nodeTypeOf(node) !== Node.TEXT_NODE) {
			return null;
		}

		// Process text nodes
		if (nodeTypeOf(node) === Node.TEXT_NODE) {
			const textContent = node.textContent?.trim();
			if (!textContent) {
				return null;
			}

			// Only check visibility for text nodes that might be visible
			const parentElement = parentElementOf(node);
			if (!parentElement || tagNameOf(parentElement).toLowerCase() === 'script') {
				return null;
			}

			// hidden text is left out; text outside the viewport is kept
			if (isTextNodeHidden(node, scope)) {
				return null;
			}

			const id = `${ID.current++}`;
			DOM_HASH_MAP[id] = {
				type: "TEXT_NODE",
				text: textContent,
				isInViewport: isTextNodeInViewport(node),
			};
			return id;
		}

		// Quick checks for element nodes
		if (nodeTypeOf(node) === Node.ELEMENT_NODE && !isElementAccepted(node)) {
			return null;
		}

		// Early viewport check - only filter out elements clearly outside viewport
		// The getBoundingClientRect() of the Shadow DOM host element may return width/height = 0
		if (viewportExpansion !== -1 && !shadowRootOf(node)) {
			const rect = getCachedBoundingRect(node); // Keep for initial quick check
			const style = getCachedComputedStyle(node);

			// Skip viewport check for fixed/sticky elements as they may appear anywhere
			const isFixedOrSticky = style && (style.position === 'fixed' || style.position === 'sticky');

			// Check if element has actual dimensions using offsetWidth/Height (quick check)
			const hasSize = propertyOf(node, "offsetWidth") > 0 || propertyOf(node, "offsetHeight") > 0;

			// Use getBoundingClientRect for the quick OUTSIDE check.
			// isInExpandedViewport will do the more accurate check later if needed.
			if (!rect || (!isFixedOrSticky && !hasSize && (
				rect.bottom < -viewportExpansion ||
				rect.top > window.innerHeight + viewportExpansion ||
				rect.right < -viewportExpansion ||
				rect.left > window.innerWidth + viewportExpansion
			) && !hasVisibleSizedChild(node))) {
				// console.log("Skipping node outside viewport (quick check):", node.tagName, rect);
				return null;
			}
		}

		/**
		 * @type {
		  {
			  tagName: string;
			  attributes: Record<string, string | null>;
			  xpath: any;
			  children: never[];
			  isVisible?: boolean;
			  isTopElement?: boolean;
			  isInteractive?: boolean;
			  isInViewport?: boolean;
			  highlightIndex?: number;
			  shadowRoot?: boolean;
		  }
		} nodeData - The node data object.
		 */
		const xpath = getXPathTree(node);
		const nodeData = {
			tagName: tagNameOf(node).toLowerCase(),
			attributes: {},
			...payloadXPath(xpath, parentXPath),
			children: [],
		};

		// Get attributes for interactive elements or potential text containers
		if (isInteractiveCandidate(node) || tagNameOf(node).toLowerCase() === 'iframe' || tagNameOf(node).toLowerCase() === 'body') {
			const attributeNames = ELEMENT.getAttributeNames.call(node) || [];
			for (const name of attributeNames) {
				const value = getAttribute(node, name);
				nodeData.attributes[name] = value;
			}
		}

		let nodeWasHighlighted = false;
		// Perform visibility, interactivity, and highlighting checks
		if (nodeTypeOf(node) === Node.ELEMENT_NODE) {
			nodeData.isVisible = isElementVisible(node); // isElementVisible uses offsetWidth/Height, which is fine
			if (nodeData.isVisible) {
				nodeData.isTopElement = isTopElement(node);

				// Special handling for ARIA menu containers - check interactivity even if not top element
				const role = getAttribute(node, 'role');
				const isMenuContainer = role === 'menu' || role === 'menubar' || role === 'listbox';
				// a control above or below the viewport: described, without an action (see `handleHighlighting`);
				// a menu container cut by the edge of the viewport keeps its highlight index
				const isOffscreen = !nodeData.isTopElement && !isMenuContainer && isOffscreenControl(node);

				if ((nodeData.isTopElement || isMenuContainer || isOffscreen) && !isElementHidden(node, scope)) {
					const interactiveResult = isOffscreen
						? (getDisabledReason(node, getCachedComputedStyle(node)) ?? true)
						: isInteractiveElement(node);

					// Parse interactive result for disabled state
					if (typeof interactiveResult === 'string') {
						nodeData.isInteractive = false;
						nodeData.disabledReason = interactiveResult.startsWith('DISABLED_') ? interactiveResult : null;
					} else {
						nodeData.isInteractive = interactiveResult;
						nodeData.disabledReason = null;
					}

					// Add pointer element detection using dedicated function
					nodeData.pointerElement = !isOffscreen && isPointerElementWithHover(node);
					// Call the dedicated highlighting function
					nodeWasHighlighted = handleHighlighting(nodeData, node, parentIframe, isParentHighlighted, isOffscreen);
					const isDisabled = nodeData.disabledReason && handleDisabledControl(nodeData, node, isParentHighlighted);
					// an off-screen link or button without text is named like in view (an image link by its `alt`)
					if (nodeData.offscreen && !FIELD_TAGS.has(localNameOf(node)) && !hasDescribedText(node)) {
						const accessibleName = getAccessibleName(node);
						if (accessibleName !== undefined) nodeData.accessibleName = accessibleName;
					}
					// an off-screen checkbox, radio or switch says whether it is checked, and a toggle button, tab or
					// menu button whether it is pressed, selected or expanded, as in view. Not its other live state: a
					// typed value would be in the description, which secrets are not masked in
					if (nodeData.offscreen) {
						const state = {};
						const checked = localNameOf(node) === "input" && (node.type === "checkbox" || node.type === "radio")
							? node.checked
							: parseAriaBoolean(node, "aria-checked");
						if (checked !== undefined) state.checked = checked;
						for (const key of ["pressed", "selected", "expanded"]) {
							const value = parseAriaBoolean(node, `aria-${key}`);
							if (value !== undefined) state[key] = value;
						}
						if (Object.keys(state).length > 0) nodeData.state = state;
					}
					if (nodeData.highlightIndex !== undefined || isDisabled) {
						const state = getLiveState(node);
						if (state !== undefined) nodeData.state = state;
						const accessibleName = getAccessibleName(node);
						if (accessibleName !== undefined) nodeData.accessibleName = accessibleName;
						// a mouse handler of its own (the ones `isInteractiveElement` counts): the element may do
						// something else than the control around or inside it
						if (CLICK_HANDLER_ATTRS.some((attr) => hasAttribute(node, attr) || typeof propertyOf(node, attr) === "function")) {
							nodeData.clickHandler = true;
						}
					}
				}
			}
		}

		const isControl = nodeData.highlightIndex !== undefined || nodeData.offscreen === true || nodeData.disabled === true;
		const childScope = contentScope(node, scope, isControl);

		// Process children, with special handling for iframes and rich text editors
		if (tagNameOf(node)) {
			const tagName = tagNameOf(node).toLowerCase();

			// Iframes: their documents are built by separate evaluations (one per frame, which also
			// works for cross-origin iframes). Mark the visible iframe elements the caller asked about
			// so it can graft each frame's tree here, and give the position of the iframe's content
			// box, which the caller adds to the bounding boxes of the frame's elements.
			if (tagName === "iframe") {
				const frameIndex = frame_elements.indexOf(node);
				if (frameIndex !== -1 && nodeData.isVisible) {
					const rect = getCachedBoundingRect(node);
					const style = getCachedComputedStyle(node);
					nodeData.frameIndex = frameIndex;
					nodeData.frameOffset = {
						x: rect.left + propertyOf(node, "clientLeft") + (parseFloat(style.paddingLeft) || 0),
						y: rect.top + propertyOf(node, "clientTop") + (parseFloat(style.paddingTop) || 0),
					};
				}
			}
			// Handle rich text editors and contenteditable elements
			else if (
				propertyOf(node, "isContentEditable") ||
				getAttribute(node, "contenteditable") === "true" ||
				idOf(node) === "tinymce" ||
				classListOf(node).contains("mce-content-body") ||
				(tagName === "body" && getAttribute(node, "data-id")?.startsWith("mce_"))
			) {
				// Process all child nodes to capture formatted text
				for (const child of childNodesOf(node)) {
					const domElement = buildDomTree(child, parentIframe, nodeWasHighlighted, childScope, xpath);
					if (domElement) nodeData.children.push(domElement);
				}
			}
			else {
				// Handle shadow DOM
				if (shadowRootOf(node)) {
					nodeData.shadowRoot = true;
					for (const child of shadowRootOf(node).childNodes) {
						const domElement = buildDomTree(child, parentIframe, nodeWasHighlighted, childScope, xpath);
						if (domElement) nodeData.children.push(domElement);
					}
				}
				// Handle regular elements
				for (const child of childNodesOf(node)) {
					// Pass the highlighted status of the *current* node to its children
					const passHighlightStatusToChild = nodeWasHighlighted || isParentHighlighted;
					const domElement = buildDomTree(child, parentIframe, passHighlightStatusToChild, childScope, xpath);
					if (domElement) nodeData.children.push(domElement);
				}
			}
		}

		// Skip empty anchor tags only if they have no dimensions and no children
		if (nodeData.tagName === 'a' && nodeData.children.length === 0 && !nodeData.attributes.href) {
			// Check if the anchor has actual dimensions
			const rect = getCachedBoundingRect(node);
			const hasSize = (rect && rect.width > 0 && rect.height > 0) || (propertyOf(node, "offsetWidth") > 0 || propertyOf(node, "offsetHeight") > 0);

			if (!hasSize) {
				return null;
			}
		}

		const id = `${ID.current++}`;
		DOM_HASH_MAP[id] = nodeData;
		return id;
	}

	const rootId = buildDomTree(BODY);

	// Clear the cache before starting
	DOM_CACHE.clearCache();

	// The payload is returned as a JSON string: transferring one string is much faster than letting
	// Playwright serialise the node map value by value.
	const payload = JSON.stringify({ rootId, map: DOM_HASH_MAP });
	return ELEMENTS ? { payload, elements: ELEMENTS } : payload;
};
