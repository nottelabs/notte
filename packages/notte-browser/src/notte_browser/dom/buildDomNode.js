// file taken from: https://github.com/browser-use/browser-use/blob/main/browser_use/dom/buildDomTree.js
(
	{ highlight_elements, focus_element, viewport_expansion, enable_pointer_elements }
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

	const ID = { current: 0 };

	const HIGHLIGHT_CONTAINER_ID = "playwright-highlight-container";

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
	 * Checks if a text node is visible.
	 *
	 * @param {Text} textNode - The text node to check.
	 * @returns {boolean} Whether the text node is visible.
	 */
	function isTextNodeVisible(textNode) {
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
			'progress',    // In progress
			'initial',     // Initial value
			'inherit'      // Inherited value
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
			'readonly',          // Read-only state
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

			// Check for readonly property on form elements
			if (element.readOnly) {
				return 'DISABLED_READONLY';
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
	 * @returns {boolean} Whether the element is a distinct interaction.
	 */
	function isElementDistinctInteraction(element) {
		if (!element || element.nodeType !== Node.ELEMENT_NODE) {
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

	/**
	 * Creates a node data object for a given node and its descendants.
	 *
	 * @param {HTMLElement} node - The node to process.
	 * @param {HTMLElement | null} parentIframe - The parent iframe node.
	 * @param {boolean} isParentHighlighted - Whether the parent node is highlighted.
	 * @returns {string | null} The ID of the node data object, or null if the node is not processed.
	 */
	function buildDomTree(node, parentIframe = null, isParentHighlighted = false) {
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

			const id = `${ID.current++}`;
			DOM_HASH_MAP[id] = {
				type: "TEXT_NODE",
				text: textContent,
				isVisible: isTextNodeVisible(node),
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
			))) {
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

				if (nodeData.isTopElement || isMenuContainer) {
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
				}
			}
		}

		// Process children, with special handling for iframes and rich text editors
		if (node.tagName) {
			const tagName = node.tagName.toLowerCase();

			// Handle iframes
			if (tagName === "iframe") {
				try {
					const iframeDoc = node.contentDocument || node.contentWindow?.document;
					if (iframeDoc) {
						for (const child of iframeDoc.childNodes) {
							const domElement = buildDomTree(child, node, false);
							if (domElement) nodeData.children.push(domElement);
						}
					}
				} catch (e) {
					console.warn("Unable to access iframe:", e);
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
					const domElement = buildDomTree(child, parentIframe, nodeWasHighlighted);
					if (domElement) nodeData.children.push(domElement);
				}
			}
			else {
				// Handle shadow DOM
				if (node.shadowRoot) {
					nodeData.shadowRoot = true;
					for (const child of node.shadowRoot.childNodes) {
						const domElement = buildDomTree(child, parentIframe, nodeWasHighlighted);
						if (domElement) nodeData.children.push(domElement);
					}
				}
				// Handle regular elements
				for (const child of node.childNodes) {
					// Pass the highlighted status of the *current* node to its children
					const passHighlightStatusToChild = nodeWasHighlighted || isParentHighlighted;
					const domElement = buildDomTree(child, parentIframe, passHighlightStatusToChild);
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

	return { rootId, map: DOM_HASH_MAP };
};
