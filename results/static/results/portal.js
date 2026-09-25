document.querySelectorAll("tr[data-href]").forEach((row) => {
  row.addEventListener("click", (event) => {
    if (event.target.closest("a, button, input, select, textarea, form")) return;
    window.location.assign(row.dataset.href);
  });
  row.setAttribute("tabindex", "0");
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter") window.location.assign(row.dataset.href);
  });
});

if (document.querySelector(".status-running")) {
  window.setTimeout(() => window.location.reload(), 30000);
}

document.querySelectorAll("[data-dialog-open]").forEach((button) => {
  button.addEventListener("click", () => {
    const dialog = document.getElementById(button.dataset.dialogOpen);
    if (dialog) dialog.showModal();
  });
});

document.querySelectorAll("[data-dialog-close]").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog")?.close());
});

document.querySelectorAll("dialog.confirm-dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});
