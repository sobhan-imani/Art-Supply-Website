// Bootstrap 5 has no jQuery plugins: tooltips have to be constructed by hand.
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
    if (window.bootstrap) new bootstrap.Tooltip(element);
  });
});

$(document).ready(function () {  
  $(window).scroll(function () {
    if ($(this).scrollTop() > 60) {
      $('#toTopBtn').fadeIn();
    } else {
      $('#toTopBtn').fadeOut();
    }
  });

  $('#toTopBtn').click(function () {
    $("html, body").animate({
      scrollTop: 0
    }, 500);
    return false;
  });
});
