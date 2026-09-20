(() => {
    const cards = [...document.querySelectorAll("[data-agent]")];
    const note = document.querySelector("#agentPickerNote");
    if (!cards.length) return;

    const storageKey = "itbLastAgent";
    const labels = {
        "infinity-agent": "Infinity AI Agent"
    };
    const saved = localStorage.getItem(storageKey);

    const select = (id, announce = false) => {
        cards.forEach(card => card.classList.toggle("is-selected", card.dataset.agent === id));
        if (announce && note && labels[id]) note.textContent = `${labels[id]} selected. Opening your workspace…`;
    };

    if (saved && labels[saved]) select(saved);

    cards.forEach(card => {
        card.addEventListener("click", () => {
            localStorage.setItem(storageKey, card.dataset.agent);
            select(card.dataset.agent, true);
        });
    });
})();
