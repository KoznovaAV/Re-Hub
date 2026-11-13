const root = document.documentElement;
const key = "rehub-theme";

try {
  const saved = localStorage.getItem(key) ?? localStorage.getItem("rehub-assistant-theme");
  if (saved === "dark" || saved === "light") root.dataset.theme = saved;
} catch {
  // Страница остаётся доступной, если хранилище браузера отключено.
}

export function connectThemeToggle(button) {
  function updateLabel() {
    const light = root.dataset.theme === "light";
    button.textContent = light ? "Тёмная тема" : "Светлая тема";
  }

  updateLabel();
  button.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
    updateLabel();
    try {
      localStorage.setItem(key, root.dataset.theme);
    } catch {
      // Тема уже применена к текущей странице.
    }
  });
}
