() => {
  // Each target has its own listener: retargeting across shadow boundaries cannot hide
  // a misresolved click. Repeated HTML ids in frames/roots are deliberately allowed.
  const targets = [];
  function visit(root) {
    for (const element of root.querySelectorAll('*')) {
      if (element.hasAttribute('data-probe')) targets.push(element);
      if (element.shadowRoot) visit(element.shadowRoot);
      if (element.tagName === 'IFRAME') visit(element.contentDocument);
    }
  }
  visit(document);
  window.characterizationEvents = [];
  for (const element of targets) {
    for (const type of ['click', 'input', 'change']) {
      element.addEventListener(type, () => {
        window.characterizationEvents.push({target: element.dataset.probe, type});
      });
    }
  }
  window.characterizationState = () => Object.fromEntries(targets.map(element => [
    element.dataset.probe,
    {
      value: element.value ?? null,
      checked: element.checked ?? null,
      text: element.isContentEditable ? element.textContent : null,
      ariaChecked: element.getAttribute('aria-checked'),
      ariaSelected: element.getAttribute('aria-selected'),
      selected: element.dataset.selected ?? null
    }
  ]));
}
