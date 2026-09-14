// Cart sidebar: every cart form works as a plain POST, this only upgrades it
// to a fetch() that re-renders the sidebar without leaving the page.
(function () {
  const sidebar = document.getElementById('cartSidebar');
  const body = document.getElementById('cart-sidebar-body');
  const counter = document.getElementById('cart-counter');
  if (!sidebar || !body) return;

  function open() {
    if (window.bootstrap && bootstrap.Offcanvas) {
      bootstrap.Offcanvas.getOrCreateInstance(sidebar).show();
    }
  }

  function flash(text) {
    if (!text) return;
    const note = document.createElement('div');
    note.className = 'alert alert-info alert-dismissible fade show m-3 py-2';
    note.setAttribute('role', 'alert');
    note.textContent = text;
    note.insertAdjacentHTML('afterbegin',
      '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>');
    body.insertAdjacentElement('beforebegin', note);
    setTimeout(() => note.remove(), 4000);
  }

  function render(data) {
    body.innerHTML = data.html;
    if (counter) counter.textContent = data.count;
    flash(data.message);
  }

  function send(form) {
    fetch(form.action, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: new FormData(form),
      credentials: 'same-origin',
    }).then(response => {
      if (!response.ok) throw new Error(response.status);
      return response.json();
    }).then(data => {
      render(data);
      open();
    }).catch(() => {
      // Something went wrong server side: let the browser post the form itself
      // so the customer still gets a working cart and a real error page.
      form.submit();
    });
  }

  document.addEventListener('submit', function (event) {
    const form = event.target.closest('form[data-cart-form]');
    if (!form) return;
    event.preventDefault();
    send(form);
  });

  // /orders/cart/ has no page of its own, it sends visitors here with the
  // sidebar opened instead.
  if (new URLSearchParams(window.location.search).get('cart') === 'open') open();
})();
