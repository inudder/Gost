document.body.addEventListener("htmx:responseError", () => {
  console.error("HTMX request failed.");
});
