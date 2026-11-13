import { computed, defineComponent, onMounted, ref } from "vue";
import { connectThemeToggle } from "../composables/theme.js";
import { TODAY, users } from "../mock/data.js";

export default defineComponent({
  name: "AppTopbar",
  props: {
    view: { type: String, required: true },
    clientName: { type: String, default: "" },
    actor: { type: String, required: true },
  },
  emits: ["update:actor", "navigate"],
  setup(props) {
    const themeToggle = ref(null);
    onMounted(() => connectThemeToggle(themeToggle.value));
    const todayLabel = computed(() =>
      new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(
        new Date(`${TODAY}T00:00:00`),
      ),
    );
    const title = computed(() => {
      if (props.view === "client") return props.clientName || "Карточка клиента";
      if (props.view === "clients") return "Клиенты";
      if (props.view === "work") return "Работа с клиентами";
      if (props.view === "import") return "Импорт данных";
      if (props.view === "history") return "История и аналитика";
      return "Главная";
    });
    return { todayLabel, themeToggle, title, users };
  },
  template: `
    <header class="topbar">
      <div class="topbar__crumbs">
        <span>Контур</span>
        <span>/</span>
        <span v-if="view === 'client'">Клиенты /</span>
        <strong>{{ title }}</strong>
      </div>
      <div class="topbar__right">
        <span class="topbar__date">{{ todayLabel }}</span>
        <button ref="themeToggle" type="button" class="btn btn--secondary theme-toggle">Светлая тема</button>
        <div class="actor">
          <div class="actor__avatar">{{ users[actor].short }}</div>
          <select :value="actor" aria-label="Текущий пользователь" @change="$emit('update:actor', $event.target.value)">
            <option v-for="user in users" :key="user.id" :value="user.id">{{ user.name }}</option>
          </select>
        </div>
      </div>
    </header>
  `,
});
