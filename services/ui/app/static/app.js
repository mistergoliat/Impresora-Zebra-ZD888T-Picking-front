document.addEventListener("DOMContentLoaded", () => {
  const addLineButtonSelector = "[data-add-line]";
  const lineItemsSelector = "[data-line-items]";
  const template = document.getElementById("line-row-template");

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.matches(addLineButtonSelector)) return;
    const container = target.closest("form")?.querySelector(lineItemsSelector);
    if (!container || !template) return;
    const clone = template.content.firstElementChild.cloneNode(true);
    container.appendChild(clone);
  });
});
