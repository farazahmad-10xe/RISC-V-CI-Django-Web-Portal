document.querySelectorAll("tr[data-href]").forEach((row) => {
  row.addEventListener("click", () => window.location.assign(row.dataset.href));
  row.setAttribute("tabindex", "0");
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter") window.location.assign(row.dataset.href);
  });
});

if (document.querySelector(".status-running")) {
  window.setTimeout(() => window.location.reload(), 30000);
}
