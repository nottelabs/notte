// file taken from: https://github.com/browser-use/browser-use/blob/main/browser_use/dom/buildDomTree.js
(
	{ highlight_elements, focus_element, viewport_expansion }
) => {

	let highlightIndex = 0; // Reset highlight index

	function highlightElement(node, parentIframe = null) {
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


	// Helper function to generate XPath as a tree
	function getXPathTree(element, stopAtBoundary = true) {
		const segments = [];
		let currentElement = element;

		while (currentElement && currentElement.nodeType === Node.ELEMENT_NODE) {
			// Stop if we hit a shadow root or iframe
			if (stopAtBoundary && (currentElement.parentNode instanceof ShadowRoot || currentElement.parentNode instanceof HTMLIFrameElement)) {
				break;
			}

			let index = 0;
			let sibling = currentElement.previousSibling;
			while (sibling) {
				if (sibling.nodeType === Node.ELEMENT_NODE &&
					sibling.nodeName === currentElement.nodeName) {
					index++;
				}
				sibling = sibling.previousSibling;
			}
			// should also iteratate over the next siblings look if there is a next sibling with the same tag name
			let moreSiblings = false;
			let nextSibling = currentElement.nextSibling;
			while (nextSibling) {
				if (nextSibling.nodeType === Node.ELEMENT_NODE &&
					nextSibling.nodeName === currentElement.nodeName) {
					moreSiblings = true;
				}
				nextSibling = nextSibling.nextSibling;
			}

			const tagName = currentElement.nodeName.toLowerCase();
			const xpathIndex = (index > 0 || moreSiblings) ? `[${index + 1}]` : '';
			segments.unshift(`${tagName}${xpathIndex}`);

			currentElement = currentElement.parentNode;
		}

		return segments.join('/');
	}

	// Helper function to check if element is accepted
	function isElementAccepted(element) {
		const leafElementDenyList = new Set(['svg', 'script', 'style', 'link', 'meta']);
		return !leafElementDenyList.has(element.tagName.toLowerCase());
	}


	// Add isEditable check
	function isEditableElement(element) {
		// Check if element is disabled
		if (element.disabled || element.getAttribute('aria-disabled') === 'true') {
			return false;
		}

		// Check for readonly attribute
		const isReadonly = element.hasAttribute('readonly') ||
			element.getAttribute('aria-readonly') === 'true';

		// For select, input, and textarea, check readonly attribute
		if (element.tagName.toLowerCase() in { 'select': 1, 'input': 1, 'textarea': 1 }) {
			return !isReadonly;
		}

		// Check contenteditable
		if (element.hasAttribute('contenteditable') &&
			element.getAttribute('contenteditable') !== 'false') {
			return !isReadonly;
		}

		return false;
	}

	// Helper function to check if element is interactive
	function isInteractiveElement(element) {

		// Get computed style
		const style = window.getComputedStyle(element);

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

		function doesElementHaveInteractivePointer(element) {
			if (element.tagName.toLowerCase() === "html") return false;

			if (style?.cursor && interactiveCursors.has(style.cursor)) return true;

			return false;
		}

		let isInteractiveCursor = doesElementHaveInteractivePointer(element);

		if (isInteractiveCursor) {
			return true;
		}

		// Base interactive elements and roles
		const interactiveElements = new Set([
			'a', 'button', 'details', 'embed', 'input', 'label',
			'menu', 'menuitem', 'object', 'select', 'textarea', 'summary'
		]);

		const interactiveRoles = new Set([
			'button', 'menu', 'menuitem', 'link', 'checkbox', 'radio',
			'slider', 'tab', 'tabpanel', 'textbox', 'combobox', 'grid',
			'listbox', 'option', 'progressbar', 'scrollbar', 'searchbox',
			'switch', 'tree', 'treeitem', 'spinbutton', 'tooltip', 'a-button-inner', 'a-dropdown-button', 'click',
			'menuitemcheckbox', 'menuitemradio', 'a-button-text', 'button-text', 'button-icon', 'button-icon-only', 'button-text-icon-only', 'dropdown', 'combobox'
		]);

		const tagName = element.tagName.toLowerCase();
		const role = element.getAttribute('role');
		const ariaRole = element.getAttribute('aria-role');
		const tabIndex = element.getAttribute('tabindex');

		// Add check for specific class
		const hasAddressInputClass = element.classList.contains('address-input__container__input');

		// Basic role/attribute checks
		const hasInteractiveRole = hasAddressInputClass ||
			interactiveElements.has(tagName) ||
			interactiveRoles.has(role) ||
			interactiveRoles.has(ariaRole) ||
			(tabIndex !== null && tabIndex !== '-1') ||
			element.getAttribute('data-action') === 'a-dropdown-select' ||
			element.getAttribute('data-action') === 'a-dropdown-button';

		if (hasInteractiveRole) return true;

		// Check if element has click-like styling
		// const hasClickStyling = style.cursor === 'pointer' ||
		//     element.style.cursor === 'pointer' ||
		//     style.pointerEvents !== 'none';

		// Check for event listeners
		const hasClickHandler = element.onclick !== null ||
			element.getAttribute('onclick') !== null ||
			element.hasAttribute('ng-click') ||
			element.hasAttribute('@click') ||
			element.hasAttribute('v-on:click');

		// Helper function to safely get event listeners
		function getEventListeners(el) {
			try {
				// Try to get listeners using Chrome DevTools API
				return window.getEventListeners?.(el) || {};
			} catch (e) {
				// Fallback: check for common event properties
				const listeners = {};

				// List of common event types to check
				const eventTypes = [
					'click', 'mousedown', 'mouseup',
					'touchstart', 'touchend',
					'keydown', 'keyup', 'focus', 'blur'
				];

				for (const type of eventTypes) {
					const handler = el[`on${type}`];
					if (handler) {
						listeners[type] = [{
							listener: handler,
							useCapture: false
						}];
					}
				}

				return listeners;
			}
		}

		// Check for click-related events on the element itself
		const listeners = getEventListeners(element);
		const hasClickListeners = listeners && (
			listeners.click?.length > 0 ||
			listeners.mousedown?.length > 0 ||
			listeners.mouseup?.length > 0 ||
			listeners.touchstart?.length > 0 ||
			listeners.touchend?.length > 0
		);

		// Check for ARIA properties that suggest interactivity
		const hasAriaProps = element.hasAttribute('aria-expanded') ||
			element.hasAttribute('aria-pressed') ||
			element.hasAttribute('aria-selected') ||
			element.hasAttribute('aria-checked');

		// Check for form-related functionality
		const isFormRelated = element.form !== undefined ||
			element.hasAttribute('contenteditable') ||
			style.userSelect !== 'none';

		// Check if element is draggable
		const isDraggable = element.draggable ||
			element.getAttribute('draggable') === 'true';

		return hasAriaProps ||
			// hasClickStyling ||
			hasClickHandler ||
			hasClickListeners ||
			// isFormRelated ||
			isDraggable;

	}

	// Helper function to check if element is visible
	function isElementVisible(element) {
		const style = window.getComputedStyle(element);
		return element.offsetWidth > 0 &&
			element.offsetHeight > 0 &&
			style.visibility !== 'hidden' &&
			style.display !== 'none';
	}

	// Helper function to check if element is the top element at its position
	function isTopElement(element) {
		// Find the correct document context and root element
		let doc = element.ownerDocument;

		// If we're in an iframe, elements are considered top by default
		if (doc !== window.document) {
			return true;
		}

		// For shadow DOM, we need to check within its own root context
		const shadowRoot = element.getRootNode();
		if (shadowRoot instanceof ShadowRoot) {
			const rect = element.getBoundingClientRect();
			const point = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };

			try {
				// Use shadow root's elementFromPoint to check within shadow DOM context
				const topEl = shadowRoot.elementFromPoint(point.x, point.y);
				if (!topEl) return false;

				// Check if the element or any of its parents match our target element
				let current = topEl;
				while (current && current !== shadowRoot) {
					if (current === element) return true;
					current = current.parentElement;
				}
				return false;
			} catch (e) {
				return true; // If we can't determine, consider it visible
			}
		}

		// Regular DOM elements
		const rect = element.getBoundingClientRect();

		// If viewportExpansion is -1, check if element is the top one at its position
		if (viewport_expansion === -1) {
			return true; // Consider all elements as top elements when expansion is -1
		}

		// Calculate expanded viewport boundaries including scroll position
		const scrollX = window.scrollX;
		const scrollY = window.scrollY;
		const viewportTop = -viewport_expansion + scrollY;
		const viewportLeft = -viewport_expansion + scrollX;
		const viewportBottom = window.innerHeight + viewport_expansion + scrollY;
		const viewportRight = window.innerWidth + viewport_expansion + scrollX;

		// Get absolute element position
		const absTop = rect.top + scrollY;
		const absLeft = rect.left + scrollX;
		const absBottom = rect.bottom + scrollY;
		const absRight = rect.right + scrollX;

		// Skip if element is completely outside expanded viewport
		if (absBottom < viewportTop ||
			absTop > viewportBottom ||
			absRight < viewportLeft ||
			absLeft > viewportRight) {
			return false;
		}

		// For elements within expanded viewport, check if they're the top element
		try {
			const centerX = rect.left + rect.width / 2;
			const centerY = rect.top + rect.height / 2;

			// Only clamp the point if it's outside the actual document
			const point = {
				x: centerX,
				y: centerY
			};

			if (point.x < 0 || point.x >= window.innerWidth ||
				point.y < 0 || point.y >= window.innerHeight) {
				return false; // Consider elements with center outside viewport as visible
			}

			const topEl = document.elementFromPoint(point.x, point.y);
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

	// Helper function to check if text node is visible
	function isTextNodeVisible(textNode) {
		const range = document.createRange();
		range.selectNodeContents(textNode);
		const rect = range.getBoundingClientRect();

		return rect.width !== 0 &&
			rect.height !== 0 &&
			rect.top >= 0 &&
			rect.top <= window.innerHeight &&
			textNode.parentElement?.checkVisibility({
				checkOpacity: true,
				checkVisibilityCSS: true
			});
	}


	// Function to traverse the DOM and create nested JSON
	function buildDomTree(node, parentIframe = null) {
		if (!node) return null;

		// Special case for text nodes
		if (node.nodeType === Node.TEXT_NODE) {
			const textContent = node.textContent.trim();
			if (textContent && isTextNodeVisible(node)) {
				return {
					type: "TEXT_NODE",
					text: textContent,
					isVisible: true,
				};
			}
			return null;
		}

		// Check if element is accepted
		if (node.nodeType === Node.ELEMENT_NODE && !isElementAccepted(node)) {
			return null;
		}

		const nodeData = {
			tagName: node.tagName ? node.tagName.toLowerCase() : null,
			attributes: {},
			xpath: node.nodeType === Node.ELEMENT_NODE ? getXPathTree(node, true) : null,
			children: [],
		};

		// Copy all attributes if the node is an element
		if (node.nodeType === Node.ELEMENT_NODE && node.attributes) {
			// Use getAttributeNames() instead of directly iterating attributes
			const attributeNames = node.getAttributeNames?.() || [];
			for (const name of attributeNames) {
				nodeData.attributes[name] = node.getAttribute(name);
			}
		}

		if (node.nodeType === Node.ELEMENT_NODE) {
			const isInteractive = isInteractiveElement(node);
			const isVisible = isElementVisible(node);
			const isTop = isTopElement(node);
			const isEditable = isEditableElement(node);

			nodeData.isInteractive = isInteractive;
			nodeData.isVisible = isVisible;
			nodeData.isTopElement = isTop;
			nodeData.isEditable = isEditable;

			// Highlight if element meets all criteria and highlighting is enabled
			if (isInteractive && isVisible && isTop) {
				nodeData.highlightIndex = highlightIndex++;
				if (highlight_elements) {
					if (focus_element >= 0) {
						if (focus_element === nodeData.highlightIndex) {
							nodeData.bbox = highlightElement(node, parentIframe);
						}
					} else {
						nodeData.bbox = highlightElement(node, parentIframe);
					}
				}
			}
		}

		// Only add iframeContext if we're inside an iframe
		// if (parentIframe) {
		//     nodeData.iframeContext = `iframe[src="${parentIframe.src || ''}"]`;
		// }

		// Only add shadowRoot field if it exists
		if (node.shadowRoot) {
			nodeData.shadowRoot = true;
		}

		// Handle shadow DOM
		if (node.shadowRoot && node.childNodes != undefined) {
			const shadowChildren = Array.from(node.shadowRoot.childNodes).map(child =>
				buildDomTree(child, parentIframe)
			);
			nodeData.children.push(...shadowChildren);
		}

		// Handle iframes
		if (node.tagName === 'IFRAME') {
			try {
				const iframeDoc = node.contentDocument || node.contentWindow.document;
				if (iframeDoc && node.childNodes != undefined) {
					const iframeChildren = Array.from(iframeDoc.body.childNodes).map(child =>
						buildDomTree(child, node)
					);
					nodeData.children.push(...iframeChildren);
				}
			} catch (e) {
				console.warn('Unable to access iframe:', node);
			}
		} else {
			if (node.childNodes != undefined) {
				const children = Array.from(node.childNodes).map(child =>
					buildDomTree(child, parentIframe)
				);
				nodeData.children.push(...children);
			}
		}

		return nodeData;
	}


	return buildDomTree(document.body);
}
