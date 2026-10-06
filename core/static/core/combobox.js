/**
 * shadcn/ui Inspired Combobox / Searchable Select Controller
 * Automatically enhances <select data-combobox> elements or configured forms.
 */
(() => {
  const CHECK_ICON_SVG = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
  const CHEVRON_SVG = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shadcn-combobox-icon"><path d="m6 9 6 6 6-6"/></svg>`;
  const SEARCH_SVG = `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shadcn-combobox-search-icon"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;

  function setupCombobox(select) {
    if (!select || select.dataset.shadcnInitialized) return;
    select.dataset.shadcnInitialized = 'true';

    // Hide native select visually while keeping it in form DOM
    select.classList.add('shadcn-hidden-native');

    let placeholder = select.getAttribute('data-placeholder');
    if (!placeholder) {
      const firstOpt = select.options[0];
      if (firstOpt && firstOpt.value === '' && !firstOpt.text.trim().startsWith('---')) {
        placeholder = firstOpt.text;
      } else {
        const fieldName = select.name || select.id || 'option';
        const cleanName = fieldName.replace(/^(id_)/, '').replace(/_/g, ' ');
        placeholder = `Select ${cleanName}...`;
      }
    }

    // Wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'shadcn-combobox';
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);

    // Trigger button
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'shadcn-combobox-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');

    const valueSpan = document.createElement('span');
    valueSpan.className = 'shadcn-combobox-value';
    trigger.appendChild(valueSpan);

    const iconSpan = document.createElement('span');
    iconSpan.innerHTML = CHEVRON_SVG;
    trigger.appendChild(iconSpan.firstChild);

    wrapper.appendChild(trigger);

    // Popover container
    const popover = document.createElement('div');
    popover.className = 'shadcn-combobox-popover';
    popover.setAttribute('role', 'listbox');

    // Search header
    const searchWrap = document.createElement('div');
    searchWrap.className = 'shadcn-combobox-search-wrap';
    searchWrap.innerHTML = SEARCH_SVG;

    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.className = 'shadcn-combobox-search-input';
    searchInput.placeholder = select.getAttribute('data-search-placeholder') || 'Search...';
    searchInput.autocomplete = 'off';
    searchWrap.appendChild(searchInput);
    popover.appendChild(searchWrap);

    // List container
    const list = document.createElement('div');
    list.className = 'shadcn-combobox-list';
    popover.appendChild(list);

    // Empty state
    const emptyState = document.createElement('div');
    emptyState.className = 'shadcn-combobox-empty';
    emptyState.textContent = 'No matching options found.';
    emptyState.style.display = 'none';
    list.appendChild(emptyState);

    wrapper.appendChild(popover);

    let items = [];

    function buildOptions() {
      // Clear existing items (except emptyState)
      Array.from(list.children).forEach(child => {
        if (child !== emptyState) list.removeChild(child);
      });
      items = [];

      Array.from(select.options).forEach((opt, idx) => {
        // Skip empty placeholder option if intended as blank or dashes
        const isPlaceholder = opt.value === '' && (
          opt.text.toLowerCase().includes('select') ||
          opt.text.trim().startsWith('---') ||
          idx === 0
        );
        if (isPlaceholder) {
          return;
        }

        const item = document.createElement('div');
        item.className = 'shadcn-combobox-item';
        item.setAttribute('role', 'option');
        item.setAttribute('data-value', opt.value);
        item.setAttribute('data-text', opt.text.trim());
        item.innerHTML = `<span>${opt.text}</span><span class="shadcn-combobox-item-check">${CHECK_ICON_SVG}</span>`;

        item.addEventListener('click', () => {
          selectValue(opt.value, true);
          close();
          trigger.focus();
        });

        list.appendChild(item);
        items.push({ element: item, text: opt.text.trim().toLowerCase(), value: opt.value });
      });

      updateSelectionVisuals();
    }

    function updateSelectionVisuals() {
      const currentVal = select.value;
      const selectedOpt = select.selectedOptions[0];

      if (selectedOpt && selectedOpt.value !== '') {
        valueSpan.innerHTML = `<span>${selectedOpt.text}</span>`;
        valueSpan.classList.remove('shadcn-combobox-placeholder');
      } else {
        valueSpan.innerHTML = `<span class="shadcn-combobox-placeholder">${placeholder}</span>`;
        valueSpan.classList.add('shadcn-combobox-placeholder');
      }

      items.forEach(it => {
        const isSelected = it.value === currentVal;
        it.element.setAttribute('data-selected', String(isSelected));
      });
    }

    function selectValue(val, triggerChange = true) {
      if (select.value !== val) {
        select.value = val;
        updateSelectionVisuals();
        if (triggerChange) {
          select.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    }

    function filterOptions(query) {
      const q = query.trim().toLowerCase();
      let matchCount = 0;

      items.forEach(it => {
        const matches = !q || it.text.includes(q);
        it.element.style.display = matches ? 'flex' : 'none';
        if (matches) matchCount++;
      });

      emptyState.style.display = matchCount === 0 ? 'block' : 'none';
    }

    function open() {
      if (trigger.disabled || select.disabled) return;
      wrapper.setAttribute('data-state', 'open');
      trigger.setAttribute('aria-expanded', 'true');
      searchInput.value = '';
      filterOptions('');
      setTimeout(() => searchInput.focus(), 20);
      document.addEventListener('click', handleOutsideClick);
    }

    function close() {
      wrapper.removeAttribute('data-state');
      trigger.setAttribute('aria-expanded', 'false');
      document.removeEventListener('click', handleOutsideClick);
    }

    function handleOutsideClick(e) {
      if (!wrapper.contains(e.target)) {
        close();
      }
    }

    trigger.addEventListener('click', (e) => {
      e.preventDefault();
      if (wrapper.getAttribute('data-state') === 'open') {
        close();
      } else {
        open();
      }
    });

    searchInput.addEventListener('input', (e) => {
      filterOptions(e.target.value);
    });

    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        close();
        trigger.focus();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        // Pick first visible item
        const firstVisible = items.find(it => it.element.style.display !== 'none');
        if (firstVisible) {
          selectValue(firstVisible.value, true);
          close();
          trigger.focus();
        }
      }
    });

    trigger.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        open();
      }
    });

    // Handle outside changes to select
    select.addEventListener('change', () => {
      updateSelectionVisuals();
    });

    buildOptions();
  }

  // Auto-init on DOMContentLoaded & support dynamic additions
  function initAllComboboxes() {
    document.querySelectorAll('select[data-combobox], select.shadcn-select').forEach(setupCombobox);
  }

  window.setupCombobox = setupCombobox;
  window.initAllComboboxes = initAllComboboxes;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAllComboboxes);
  } else {
    initAllComboboxes();
  }
})();
