(() => {
  const guide = document.querySelector('[data-care-guide]');
  let hiddenForVisit = false;
  try {
    hiddenForVisit = sessionStorage.getItem('hmsCareGuideHidden') === 'true';
  } catch (_) {
    // Storage can be unavailable in locked-down browsers; the guide still works.
  }
  if (!guide || hiddenForVisit) {
    guide?.remove();
    return;
  }

  const toggle = guide.querySelector('[data-care-guide-toggle]');
  const panel = guide.querySelector('[data-care-guide-panel]');
  const closeButton = guide.querySelector('[data-care-guide-close]');
  const message = guide.querySelector('[data-care-guide-message]');
  const page = guide.dataset.page || '';

  const pageHelp = {
    patient_dashboard: 'From your dashboard you can review upcoming visits, prescriptions, reports, and invoices.',
    patient_appointment_book: 'Choose a doctor and available time. Review the details carefully before confirming.',
    patient_appointment_list: 'This page shows your appointments. You can review status or open a booking flow.',
    patient_document_list: 'Your released reports and documents appear here. Use Download only on a trusted device.',
    patient_prescription_history: 'This page contains prescriptions issued to your verified patient account.',
    patient_invoice_list: 'Review issued invoices and payment status here. Contact support if something looks incorrect.',
    patient_ticket_list: 'Track requests sent to the hospital. Private staff notes are never shown in this portal.',
    patient_ticket_create: 'Describe the administrative issue without entering passwords, OTPs, or unnecessary medical details.',
  };

  message.textContent = pageHelp[page] || 'Use the shortcuts below to reach common patient services.';

  const setOpen = (open) => {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    guide.classList.toggle('care-guide--open', open);
    if (open) closeButton.focus();
    else toggle.focus();
  };

  toggle.addEventListener('click', () => setOpen(panel.hidden));
  closeButton.addEventListener('click', () => setOpen(false));
  guide.querySelector('[data-care-guide-dismiss]').addEventListener('click', () => {
    try {
      sessionStorage.setItem('hmsCareGuideHidden', 'true');
    } catch (_) {
      // Dismissal remains effective for the current page without storage.
    }
    guide.remove();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) setOpen(false);
  });
})();
