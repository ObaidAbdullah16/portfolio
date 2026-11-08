// Contact and free-scan forms: send to Web3Forms without leaving the page.
// Without JavaScript the forms still post normally and Web3Forms redirects to /thanks.html.
(function () {
  "use strict";
  document.querySelectorAll("form[data-web3forms]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var status = form.querySelector(".form-status");
      var button = form.querySelector("button[type=submit]");
      var data = Object.fromEntries(new FormData(form));
      delete data.redirect;
      if (data.botcheck) { return; } // a bot filled the hidden field
      button.disabled = true;
      status.className = "form-status";
      status.textContent = "Sending...";
      fetch(form.action, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(data)
      })
        .then(function (response) {
          return response.json().then(function (json) { return { ok: response.ok && json.success, json: json }; });
        })
        .then(function (result) {
          if (result.ok) {
            form.reset();
            status.className = "form-status ok";
            status.textContent = "Thank you - your message is on its way. I reply within one working day (IST).";
          } else {
            throw new Error((result.json && result.json.message) || "The form service returned an error.");
          }
        })
        .catch(function (error) {
          status.className = "form-status err";
          status.textContent = "Sorry, that did not go through (" + error.message + "). Please email me instead.";
        })
        .finally(function () { button.disabled = false; });
    });
  });
})();
