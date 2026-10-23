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

		const rect = element.getBoundingClientRect();

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

		const rects = element.getClientRects();

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
		const value = element.getAttribute(name);
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
		const tagName = element.tagName.toLowerCase();
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
		} else if (element.isContentEditable) {
			state.value = truncateStateValue(element.innerText || "", state);
		}
		if (state.checked === undefined) {
			// role="checkbox" / "switch" / "radio" / "menuitemcheckbox" widgets
			const ariaChecked = element.getAttribute("aria-checked");
			if (ariaChecked === "true" || ariaChecked === "false") state.checked = ariaChecked === "true";
			else if (ariaChecked === "mixed") state.mixed = true;
		}
		const expanded = parseAriaBoolean(element, "aria-expanded");
		if (expanded !== undefined) state.expanded = expanded;
		const selected = parseAriaBoolean(element, "aria-selected");
		if (selected !== undefined) state.selected = selected;
		const pressed = parseAriaBoolean(element, "aria-pressed");
		if (pressed !== undefined) state.pressed = pressed;
		else if (element.getAttribute("aria-pressed") === "mixed") state.pressed = "mixed";
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
		const explicit = (element.getAttribute("role") || "").trim().split(/\s+/)[0].toLowerCase();
		if (explicit) return explicit;
		const tagName = element.localName;
		if (tagName === "a" || tagName === "area") return element.hasAttribute("href") ? "link" : "";
		if (tagName === "select") return element.multiple || element.size > 1 ? "listbox" : "combobox";
		if (tagName === "input") {
			const type = (element.getAttribute("type") || "text").toLowerCase();
			const role = INPUT_ROLES[type] ?? "";
			return element.hasAttribute("list") && (role === "textbox" || role === "searchbox") ? "combobox" : role;
		}
		if (element.isContentEditable && !element.parentElement?.isContentEditable) return "textbox";
		return IMPLICIT_ROLES[tagName] ?? "";
	}

	function isHiddenForName(element) {
		if (element.getAttribute("aria-hidden") === "true") return true;
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
		const tagName = element.localName;
		const role = getRole(element);

		// aria-labelledby, not followed from a labelledby target
		if (!step.labelledBy && element.hasAttribute("aria-labelledby")) {
			const scope = element.getRootNode();
			const parts = [];
			for (const id of element.getAttribute("aria-labelledby").trim().split(/\s+/)) {
				const target = id && scope.getElementById?.(id);
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

		const ariaLabel = element.getAttribute("aria-label");
		if (ariaLabel && ariaLabel.trim()) return ariaLabel;

		// host language labels: `<label>` first, even for input buttons, which then fall back to their value
		if (element.labels && element.labels.length > 0) {
			const text = Array.from(element.labels, (label) => {
				context.visited.delete(label);
				return textAlternative(label, context, { root: false, labelledBy: step.labelledBy, content: true, hidden: step.hidden });
			}).join(" ");
			if (text.trim()) return text;
		}
		if (tagName === "input") {
			const type = (element.getAttribute("type") || "text").toLowerCase();
			if (type === "button" || type === "submit" || type === "reset") {
				const value = element.getAttribute("value");
				if (value && value.trim()) return value;
				if (type !== "button") return type === "submit" ? "Submit" : "Reset";
			}
			if (type === "image") {
				const text = element.getAttribute("alt") || element.getAttribute("value") || element.getAttribute("title");
				return text && text.trim() ? text : "Submit";
			}
		}
		if (tagName === "img" || tagName === "area") {
			const alt = element.getAttribute("alt");
			if (alt && alt.trim()) return alt;
		} else if (tagName === "fieldset") {
			const legend = Array.from(element.children).find((child) => child.localName === "legend");
			const text = legend ? textAlternative(legend, context, { ...step, root: false, content: true }) : "";
			if (text.trim()) return text;
		} else if (tagName === "svg") {
			const title = Array.from(element.children).find((child) => child.localName === "title");
			if (title && title.textContent.trim()) return title.textContent;
		}

		// name from content: roles named by their text, and every descendant of a label
		if (step.content || NAME_FROM_CONTENT_ROLES.has(role)) {
			const text = contentText(element, context, step);
			if (text.trim()) return text;
		}

		// tooltips name the element itself only (not its ancestors), and never a generic element
		if (!step.root || (role === "" && GENERIC_TAGS.has(tagName))) return "";
		const title = element.getAttribute("title");
		if (title && title.trim()) return title;
		const placeholder = element.getAttribute("placeholder") || element.getAttribute("aria-placeholder");
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
		let children = element.shadowRoot ? element.shadowRoot.childNodes : element.childNodes;
		if (element.localName === "slot") {
			const assigned = element.assignedNodes({ flatten: true });
			if (assigned.length > 0) children = assigned;
		}
		let text = "";
		for (const child of children) {
			if (context.budget <= 0) break;
			if (child.nodeType === Node.TEXT_NODE) {
				text += transformText(child.data, child.parentElement);
				// formatting whitespace is collapsed away: it does not use up the budget
				context.budget -= child.data.trim().length;
			} else if (child.localName === "br") {
				text += " ";
			} else if (child.nodeType === Node.ELEMENT_NODE) {
				const childText = textAlternative(child, context, childStep);
				text += isInline(child) ? childText : ` ${childText} `;
			}
		}
		return text;
	}

	// Add a WeakMap cache for XPath strings
	const xpathCache = new WeakMap();

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
		const rect = node.getBoundingClientRect();
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
	 * Gets the position of an element in its parent.
	 *
	 * @param {HTMLElement} currentElement - The element to get the position for.
	 * @returns {number} The position of the element in its parent.
	 */
	function getElementPosition(currentElement) {
		if (!currentElement.parentElement) {
			return 0; // No parent means no siblings
		}

		const tagName = currentElement.nodeName.toLowerCase();

		const siblings = Array.from(currentElement.parentElement.children)
			.filter((sib) => sib.nodeName.toLowerCase() === tagName);

		if (siblings.length === 1) {
			return 0; // Only element of its type
		}

		const index = siblings.indexOf(currentElement) + 1; // 1-based index
		return index;
	}


	function getXPathTree(element, stopAtBoundary = true) {
		if (xpathCache.has(element)) return xpathCache.get(element);

		const segments = [];
		let currentElement = element;

		while (currentElement && currentElement.nodeType === Node.ELEMENT_NODE) {
			// Stop if we hit a shadow root or iframe
			if (
				stopAtBoundary &&
				(currentElement.parentNode instanceof ShadowRoot ||
					currentElement.parentNode instanceof HTMLIFrameElement)
			) {
				break;
			}

			const position = getElementPosition(currentElement);
			const tagName = currentElement.nodeName.toLowerCase();
			const xpathIndex = position > 0 ? `[${position}]` : "";
			segments.unshift(`${tagName}${xpathIndex}`);

			currentElement = currentElement.parentNode;
		}

		const result = segments.join("/");
		xpathCache.set(element, result);
		return result;
	}

	/**
	 * What hides the content of an element, inherited down the tree (see `contentScope`).
	 *
	 * - `ariaHidden`: inside `aria-hidden="true"`, and not inside focusable content
	 * - `clipped`: inside an element that clips its overflow to an empty box (`height: 0; overflow: hidden`)
	 * - `inControl`: inside a highlighted or disabled element, whose text is its label
	 */
	const VISIBLE_SCOPE = { ariaHidden: false, clipped: false, inControl: false };

	/**
	 * Checks if an element can be reached with the Tab key. Focusable content stays visible inside an
	 * `aria-hidden` subtree.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element is focusable.
	 */
	function isFocusable(element) {
		return element.tabIndex >= 0 && !element.matches(':disabled');
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
	 * The scope of an element's children: what hides them, given the element and its own scope.
	 *
	 * @param {HTMLElement} element - The element.
	 * @param {Object} scope - The scope of the element.
	 * @param {boolean} isControl - Whether the element is highlighted or disabled.
	 * @returns {Object} The scope of its children.
	 */
	function contentScope(element, scope, isControl) {
		let ariaHidden = scope.ariaHidden;
		if (element.getAttribute("aria-hidden") === "true") ariaHidden = !isFocusable(element);
		else if (ariaHidden && isFocusable(element)) ariaHidden = false;
		let clipped = scope.clipped;
		const position = getCachedComputedStyle(element)?.position;
		// a positioned element may be laid out outside the clipping box: assume it is not clipped
		if (position === "fixed" || position === "absolute") clipped = false;
		if (clipsToNothing(element)) clipped = true;
		const inControl = scope.inControl || isControl;
		if (ariaHidden === scope.ariaHidden && clipped === scope.clipped && inControl === scope.inControl) return scope;
		return { ariaHidden, clipped, inControl };
	}

	/**
	 * Checks if an element is rendered: not under `display: none`, `visibility: hidden` or a skipped
	 * `content-visibility` (`hidden="until-found"`, a closed `<details>`), nor `opacity: 0` when
	 * `checkOpacity` is set. The options of a `<select>` and `display: contents` elements have no box
	 * of their own, which `checkVisibility` reads as hidden: they are rendered when the select (the
	 * parent) is, and `visibility`, which they pass on to their content, is not `hidden`.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @param {boolean} checkOpacity - Whether `opacity: 0` hides the element.
	 * @returns {boolean} Whether the element is rendered.
	 */
	function isRendered(element, checkOpacity) {
		if (element.localName === "option" || element.localName === "optgroup") {
			element = element.closest("select") ?? element;
		}
		let boxed = element;
		while (boxed.parentElement && getCachedComputedStyle(boxed)?.display === "contents") {
			boxed = boxed.parentElement;
		}
		if (boxed !== element && getCachedComputedStyle(element)?.visibility !== "visible") return false;
		if (typeof boxed.checkVisibility !== "function") return true;
		return boxed.checkVisibility({ checkOpacity, checkVisibilityCSS: true });
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
		if (scope.clipped) return true;
		const parent = textNode.parentElement;
		if (!isRendered(parent, false)) return true;
		// the content a rendered parent skips (`hidden="until-found"`, a closed `<details>`): its
		// elements are not rendered, but its own text nodes have a box
		if (getCachedComputedStyle(parent)?.contentVisibility === "hidden" || (parent.localName === "details" && !parent.open)) {
			return true;
		}
		const range = document.createRange();
		range.selectNodeContents(textNode);
		const rects = Array.from(range.getClientRects());
		// no box at all (the text of a `<textarea>`): nothing says it is hidden
		if (rects.length === 0) return false;
		if (rects.every((rect) => rect.width === 0 || rect.height === 0)) return true;
		if (!rects.some(isOnScreen)) return false;
		if (scope.ariaHidden && !scope.inControl) return true;
		return !isRendered(parent, true);
	}

	function isOnScreen(rect) {
		return rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth;
	}

	/**
	 * Checks if a highlight candidate (a visible element) is hidden: clipped away, or on screen with
	 * `opacity: 0` (see `isTextNodeHidden`). A form control with `opacity: 0` is still a control
	 * (custom checkboxes and file inputs are drawn over by their label): it is hidden only when its
	 * parent is. `aria-hidden` does not hide a control the user can see and click (Google Flights'
	 * previous / next day buttons are `aria-hidden`).
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @param {Object} scope - The scope of the element.
	 * @returns {boolean} Whether the element is hidden.
	 */
	function isElementHidden(element, scope) {
		const position = getCachedComputedStyle(element)?.position;
		if (scope.clipped && position !== "fixed" && position !== "absolute") return true;
		if (!isOnScreen(getCachedBoundingRect(element))) return false;
		const isFormControl = DISABLEABLE_TAGS.has(element.localName);
		return !isRendered(isFormControl && element.parentElement ? element.parentElement : element, true);
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
					return parentElement.checkVisibility({
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

			const range = document.createRange();
			range.selectNodeContents(textNode);
			const rects = range.getClientRects(); // Use getClientRects for Range

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
				return parentElement.checkVisibility({
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
		for (const child of element.children) {
			const rect = getCachedBoundingRect(child);
			if (!rect) continue;
			if (rect.width === 0 || rect.height === 0) {
				if (hasVisibleSizedChild(child)) return true;
				continue;
			}
			if (typeof child.checkVisibility !== 'function' ||
				child.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) {
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
		if (!element || !element.tagName) return false;

		// Always accept body and common container elements
		const alwaysAccept = new Set([
			"body", "div", "main", "article", "section", "nav", "header", "footer"
		]);
		const tagName = element.tagName.toLowerCase();

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
			element.offsetWidth > 0 &&
			element.offsetHeight > 0 &&
			style?.visibility !== "hidden" &&
			style?.display !== "none"
		);
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
		if (!element || element.nodeType !== Node.ELEMENT_NODE) {
			return {
				normalCursor: null,
				hoverCursor: null,
				hasHoverRule: false,
				isInteractive: false,
				isHoverInteractive: false
			};
		}

		// Cache the tagName and style lookups
		const tagName = element.tagName.toLowerCase();
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

		// Parse CSS rules to find hover states
		let hoverCursor = null;
		let foundHoverRule = false;

		// Get all stylesheets
		const stylesheets = Array.from(document.styleSheets);

		for (let stylesheet of stylesheets) {
			try {
				const rules = Array.from(stylesheet.cssRules || []);

				for (let rule of rules) {
					if (!rule.selectorText) continue;

					// Check if this rule has :hover and matches our element
					if (rule.selectorText.includes(':hover')) {
						// Remove :hover from selector to test match
						const baseSelector = rule.selectorText.replace(/:hover/g, '');

						try {
							// Check if element matches the base selector
							if (element.matches(baseSelector)) {
								const cursorValue = rule.style.cursor;
								if (cursorValue && cursorValue !== '') {
									hoverCursor = cursorValue;
									foundHoverRule = true;
									break;
								}
							}
						} catch (e) {
							// Skip invalid selectors
							continue;
						}
					}
				}

				if (foundHoverRule) break;

			} catch (e) {
				// Skip CORS-protected stylesheets
				continue;
			}
		}

		// Exclude HTML element
		if (element.tagName.toLowerCase() === "html") {
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

	/**
	 * Checks if an element has a pointer cursor (clickable/interactive cursor),
	 * including hover states. This function focuses specifically on cursor-based detection.
	 *
	 * @param {HTMLElement} element - The element to check.
	 * @returns {boolean} Whether the element has a pointer cursor (normal or hover).
	 */
	function isPointerElementWithHover(element) {
		const cursorStates = getElementCursorStates(element);

		// Element is interactive if it has pointer cursor in normal state OR hover state
		return cursorStates.isInteractive || cursorStates.isHoverInteractive;
	}

	const NON_INTERACTIVE_CURSORS = new Set(['not-allowed', 'no-drop', 'wait', 'progress']);

	function getDisabledReason(element, style) {
		if (style?.cursor && NON_INTERACTIVE_CURSORS.has(style.cursor)) {
			return 'DISABLED_CURSOR';
		}
		if (
			element.hasAttribute('disabled') ||
			element.getAttribute('disabled') === 'true' ||
			element.getAttribute('disabled') === '' ||
			element.getAttribute('aria-disabled') === 'true'
		) {
			return 'DISABLED_ATTRIBUTE';
		}
		// `:disabled` also matches the controls of a disabled `<fieldset>`, whose `.disabled` is false
		if (element.disabled || element.matches(':disabled')) {
			return 'DISABLED_PROPERTY';
		}
		if (element.inert || element.hasAttribute('inert') || element.getAttribute('aria-inert') === 'true') {
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
	 */
	function isInteractiveElement(element) {
		if (!element || element.nodeType !== Node.ELEMENT_NODE) {
			return false;
		}

		// Cache the tagName and style lookups
		const tagName = element.tagName.toLowerCase();
		const style = getCachedComputedStyle(element);

		const disabledReason = getDisabledReason(element, style);
		if (disabledReason !== null) {
			return disabledReason;
		}

		// Check if element has pointer cursor using the dedicated function
		let isInteractiveCursor = isPointerElementWithHover(element);

		// Genius fix for almost all interactive elements
		if (isInteractiveCursor && enable_pointer_elements) {
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
				if (element.hasAttribute(disableTag) ||
					element.getAttribute(disableTag) === 'true' ||
					element.getAttribute(disableTag) === '') {
					return 'DISABLED_ATTRIBUTE';
				}
			}

			// Check for disabled property on form elements
			if (element.disabled) {
				return 'DISABLED_PROPERTY';
			}

			// Check for inert property
			if (element.inert) {
				return 'DISABLED_INERT';
			}

			return true;
		}

		const role = element.getAttribute("role");
		const ariaRole = element.getAttribute("aria-role");

		// Check for contenteditable attribute
		if (element.getAttribute("contenteditable") === "true" || element.isContentEditable) {
			return true;
		}

		// Added enhancement to capture dropdown interactive elements
		if (element.classList && (
			element.classList.contains("button") ||
			element.classList.contains('dropdown-toggle') ||
			element.getAttribute('data-index') ||
			element.getAttribute('data-toggle') === 'dropdown' ||
			element.getAttribute('aria-haspopup') === 'true'
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

			const getEventListenersForNode = element?.ownerDocument?.defaultView?.getEventListenersForNode || window.getEventListenersForNode;
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
			const commonMouseAttrs = ['onclick', 'onmousedown', 'onmouseup', 'ondblclick'];
			for (const attr of commonMouseAttrs) {
				if (element.hasAttribute(attr) || typeof element[attr] === 'function') {
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
		let doc = element.ownerDocument;

		// If we're in an iframe, elements are considered top by default
		if (doc !== window.document) {
			return true;
		}

		// For shadow DOM, we need to check within its own root context
		const shadowRoot = element.getRootNode();
		if (shadowRoot instanceof ShadowRoot) {
			const centerX = rects[Math.floor(rects.length / 2)].left + rects[Math.floor(rects.length / 2)].width / 2;
			const centerY = rects[Math.floor(rects.length / 2)].top + rects[Math.floor(rects.length / 2)].height / 2;

			try {
				const topEl = shadowRoot.elementFromPoint(centerX, centerY);
				if (!topEl) return false;

				let current = topEl;
				while (current && current !== shadowRoot) {
					if (current === element) return true;
					current = current.parentElement;
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
			const topEl = document.elementFromPoint(centerX, centerY);
			if (!topEl) return false;

			let current = topEl;
			while (current && current !== document.documentElement) {
				if (current === element) return true;
				current = current.parentElement;
			}
			return false;
		} catch (e) {
			return true;
		}
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

		const rects = element.getClientRects(); // Use getClientRects

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
		if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;

		const tagName = element.tagName.toLowerCase();

		// Fast-path for common interactive elements
		const interactiveElements = new Set([
			"a", "button", "input", "select", "textarea", "details", "summary", "label"
		]);

		if (interactiveElements.has(tagName)) return true;

		// Quick attribute checks without getting full lists
		const hasQuickInteractiveAttr = element.hasAttribute("onclick") ||
			element.hasAttribute("role") ||
			element.hasAttribute("tabindex") ||
			element.hasAttribute("aria-") ||
			element.hasAttribute("data-action") ||
			element.getAttribute("contenteditable") === "true";

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
		if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;

		// Skip non-visible elements early for performance
		if (!isElementVisible(element)) return false;

		// Check for common attributes that often indicate interactivity
		const hasInteractiveAttributes =
			element.hasAttribute('role') ||
			element.hasAttribute('tabindex') ||
			element.hasAttribute('onclick') ||
			typeof element.onclick === 'function';

		// Check for semantic class names suggesting interactivity
		const hasInteractiveClass = /\b(btn|clickable|menu|item|entry|link)\b/i.test(element.className || '');

		// Determine whether the element is inside a known interactive container
		const isInKnownContainer = Boolean(
			element.closest('button,a,[role="button"],.menu,.dropdown,.list,.toolbar')
		);

		// Ensure the element has at least one visible child (to avoid marking empty wrappers)
		const hasVisibleChildren = [...element.children].some(isElementVisible);

		// Avoid highlighting elements whose parent is <body> (top-level wrappers)
		const isParentBody = element.parentElement && element.parentElement.isSameNode(document.body);

		return (
			(isInteractiveElement(element) || hasInteractiveAttributes || hasInteractiveClass) &&
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
		if (!element || element.nodeType !== Node.ELEMENT_NODE) {
			return false;
		}

		if (!ignoreDisabled && getDisabledReason(element, getCachedComputedStyle(element)) !== null) {
			return false;
		}

		const tagName = element.tagName.toLowerCase();
		const role = element.getAttribute('role');

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
		// Check contenteditable
		if (element.isContentEditable || element.getAttribute('contenteditable') === 'true') {
			return true;
		}
		// Check for common testing/automation attributes
		if (element.hasAttribute('data-testid') || element.hasAttribute('data-cy') || element.hasAttribute('data-test')) {
			return true;
		}
		// Check for explicit onclick handler (attribute or property)
		if (element.hasAttribute('onclick') || typeof element.onclick === 'function') {
			return true;
		}

		// return false

		// Check for other common interaction event listeners
		try {
			const getEventListenersForNode = element?.ownerDocument?.defaultView?.getEventListenersForNode || window.getEventListenersForNode;
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
			if (commonEventAttrs.some(attr => element.hasAttribute(attr))) {
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
	 * @returns {boolean} Whether the element was highlighted.
	 */
	function handleHighlighting(nodeData, node, parentIframe, isParentHighlighted) {
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
			if (nodeData.isInViewport || viewportExpansion === -1) {
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
			} else {
				// console.log(`Skipping highlight for ${nodeData.tagName} (outside viewport)`);
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
		const tagName = element.tagName.toLowerCase();
		if (DISABLEABLE_TAGS.has(tagName) && element.matches(':disabled')) return true;
		if (element.getAttribute('aria-disabled') !== 'true') return false;
		const role = element.getAttribute('role');
		return DISABLEABLE_TAGS.has(tagName) ||
			(tagName === 'a' && element.hasAttribute('href')) ||
			(role !== null && INTERACTIVE_ROLES.has(role));
	}

	/**
	 * Marks a disabled control as `disabled` when it would be highlighted if it were enabled (same
	 * nesting and viewport rules). It gets no highlight index: it is described, but offers no action.
	 *
	 * @param {Object} nodeData - The node data object.
	 * @param {HTMLElement} node - The node to check.
	 * @param {boolean} isParentHighlighted - Whether the parent node is highlighted.
	 * @returns {boolean} Whether the node was marked.
	 */
	function handleDisabledControl(nodeData, node, isParentHighlighted) {
		if (!isDisabledControl(node)) return false;
		if (isParentHighlighted && !isElementDistinctInteraction(node, true)) return false;
		if (!isInExpandedViewport(node, viewportExpansion)) return false;
		nodeData.disabled = true;
		return true;
	}

	/**
	 * Creates a node data object for a given node and its descendants.
	 *
	 * @param {HTMLElement} node - The node to process.
	 * @param {HTMLElement | null} parentIframe - The parent iframe node.
	 * @param {boolean} isParentHighlighted - Whether the parent node is highlighted.
	 * @param {Object} scope - What hides the node (see `VISIBLE_SCOPE`).
	 * @returns {string | null} The ID of the node data object, or null if the node is not processed.
	 */
	function buildDomTree(node, parentIframe = null, isParentHighlighted = false, scope = VISIBLE_SCOPE) {
		// Fast rejection checks first
		if (!node || node.id === HIGHLIGHT_CONTAINER_ID ||
			(node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.TEXT_NODE)) {
			return null;
		}

		if (!node || node.id === HIGHLIGHT_CONTAINER_ID) {
			return null;
		}

		// Special handling for root node (body)
		if (node === document.body) {
			const nodeData = {
				tagName: 'body',
				attributes: {},
				xpath: '/body',
				children: [],
			};

			// Process children of body
			for (const child of node.childNodes) {
				const domElement = buildDomTree(child, parentIframe, false); // Body's children have no highlighted parent initially
				if (domElement) nodeData.children.push(domElement);
			}

			const id = `${ID.current++}`;
			DOM_HASH_MAP[id] = nodeData;
			return id;
		}

		// Early bailout for non-element nodes except text
		if (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.TEXT_NODE) {
			return null;
		}

		// Process text nodes
		if (node.nodeType === Node.TEXT_NODE) {
			const textContent = node.textContent?.trim();
			if (!textContent) {
				return null;
			}

			// Only check visibility for text nodes that might be visible
			const parentElement = node.parentElement;
			if (!parentElement || parentElement.tagName.toLowerCase() === 'script') {
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
		if (node.nodeType === Node.ELEMENT_NODE && !isElementAccepted(node)) {
			return null;
		}

		// Early viewport check - only filter out elements clearly outside viewport
		// The getBoundingClientRect() of the Shadow DOM host element may return width/height = 0
		if (viewportExpansion !== -1 && !node.shadowRoot) {
			const rect = getCachedBoundingRect(node); // Keep for initial quick check
			const style = getCachedComputedStyle(node);

			// Skip viewport check for fixed/sticky elements as they may appear anywhere
			const isFixedOrSticky = style && (style.position === 'fixed' || style.position === 'sticky');

			// Check if element has actual dimensions using offsetWidth/Height (quick check)
			const hasSize = node.offsetWidth > 0 || node.offsetHeight > 0;

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
		const nodeData = {
			tagName: node.tagName.toLowerCase(),
			attributes: {},
			xpath: getXPathTree(node, true),
			children: [],
		};

		// Get attributes for interactive elements or potential text containers
		if (isInteractiveCandidate(node) || node.tagName.toLowerCase() === 'iframe' || node.tagName.toLowerCase() === 'body') {
			const attributeNames = node.getAttributeNames?.() || [];
			for (const name of attributeNames) {
				const value = node.getAttribute(name);
				nodeData.attributes[name] = value;
			}
		}

		let nodeWasHighlighted = false;
		// Perform visibility, interactivity, and highlighting checks
		if (node.nodeType === Node.ELEMENT_NODE) {
			nodeData.isVisible = isElementVisible(node); // isElementVisible uses offsetWidth/Height, which is fine
			if (nodeData.isVisible) {
				nodeData.isTopElement = isTopElement(node);

				// Special handling for ARIA menu containers - check interactivity even if not top element
				const role = node.getAttribute('role');
				const isMenuContainer = role === 'menu' || role === 'menubar' || role === 'listbox';

				if ((nodeData.isTopElement || isMenuContainer) && !isElementHidden(node, scope)) {
					const interactiveResult = isInteractiveElement(node);

					// Parse interactive result for disabled state
					if (typeof interactiveResult === 'string') {
						nodeData.isInteractive = false;
						nodeData.disabledReason = interactiveResult.startsWith('DISABLED_') ? interactiveResult : null;
					} else {
						nodeData.isInteractive = interactiveResult;
						nodeData.disabledReason = null;
					}

					// Add pointer element detection using dedicated function
					nodeData.pointerElement = isPointerElementWithHover(node);
					// Call the dedicated highlighting function
					nodeWasHighlighted = handleHighlighting(nodeData, node, parentIframe, isParentHighlighted);
					const isDisabled = nodeData.disabledReason && handleDisabledControl(nodeData, node, isParentHighlighted);
					if (nodeData.highlightIndex !== undefined || isDisabled) {
						const state = getLiveState(node);
						if (state !== undefined) nodeData.state = state;
						const accessibleName = getAccessibleName(node);
						if (accessibleName !== undefined) nodeData.accessibleName = accessibleName;
					}
				}
			}
		}

		const childScope = contentScope(node, scope, nodeData.highlightIndex !== undefined || nodeData.disabled === true);

		// Process children, with special handling for iframes and rich text editors
		if (node.tagName) {
			const tagName = node.tagName.toLowerCase();

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
						x: rect.left + node.clientLeft + (parseFloat(style.paddingLeft) || 0),
						y: rect.top + node.clientTop + (parseFloat(style.paddingTop) || 0),
					};
				}
			}
			// Handle rich text editors and contenteditable elements
			else if (
				node.isContentEditable ||
				node.getAttribute("contenteditable") === "true" ||
				node.id === "tinymce" ||
				node.classList.contains("mce-content-body") ||
				(tagName === "body" && node.getAttribute("data-id")?.startsWith("mce_"))
			) {
				// Process all child nodes to capture formatted text
				for (const child of node.childNodes) {
					const domElement = buildDomTree(child, parentIframe, nodeWasHighlighted, childScope);
					if (domElement) nodeData.children.push(domElement);
				}
			}
			else {
				// Handle shadow DOM
				if (node.shadowRoot) {
					nodeData.shadowRoot = true;
					for (const child of node.shadowRoot.childNodes) {
						const domElement = buildDomTree(child, parentIframe, nodeWasHighlighted, childScope);
						if (domElement) nodeData.children.push(domElement);
					}
				}
				// Handle regular elements
				for (const child of node.childNodes) {
					// Pass the highlighted status of the *current* node to its children
					const passHighlightStatusToChild = nodeWasHighlighted || isParentHighlighted;
					const domElement = buildDomTree(child, parentIframe, passHighlightStatusToChild, childScope);
					if (domElement) nodeData.children.push(domElement);
				}
			}
		}

		// Skip empty anchor tags only if they have no dimensions and no children
		if (nodeData.tagName === 'a' && nodeData.children.length === 0 && !nodeData.attributes.href) {
			// Check if the anchor has actual dimensions
			const rect = getCachedBoundingRect(node);
			const hasSize = (rect && rect.width > 0 && rect.height > 0) || (node.offsetWidth > 0 || node.offsetHeight > 0);

			if (!hasSize) {
				return null;
			}
		}

		const id = `${ID.current++}`;
		DOM_HASH_MAP[id] = nodeData;
		return id;
	}

	const rootId = buildDomTree(document.body);

	// Clear the cache before starting
	DOM_CACHE.clearCache();

	// The payload is returned as a JSON string: transferring one string is much faster than letting
	// Playwright serialise the node map value by value.
	const payload = JSON.stringify({ rootId, map: DOM_HASH_MAP });
	return ELEMENTS ? { payload, elements: ELEMENTS } : payload;
};
