(() => {
    const storageKey = "hacktoverse-theme";
    const root = document.documentElement;
    const savedTheme = localStorage.getItem(storageKey);

    function setTheme(theme) {
        const selectedTheme = theme === "dark" ? "dark" : "light";
        root.dataset.theme = selectedTheme;
        if (document.body) document.body.dataset.theme = selectedTheme;
        localStorage.setItem(storageKey, selectedTheme);

        document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
            button.textContent = selectedTheme === "dark" ? "☀ Light" : "☾ Dark";
            button.setAttribute(
                "aria-label",
                selectedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme"
            );
            button.setAttribute("aria-pressed", String(selectedTheme === "dark"));
        });
    }

    setTheme(savedTheme === "dark" ? "dark" : "light");

    document.addEventListener("click", (event) => {
        const button = event.target.closest("[data-theme-toggle]");
        if (!button) return;
        setTheme(root.dataset.theme === "dark" ? "light" : "dark");
    });
})();
