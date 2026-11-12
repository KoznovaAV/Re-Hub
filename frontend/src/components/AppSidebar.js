import { computed, defineComponent } from "vue";
import { users } from "../mock/data.js";

export default defineComponent({
  name: "AppSidebar",
  props: {
    view: { type: String, required: true },
    actor: { type: String, required: true },
    actionCount: { type: Number, default: 0 },
    clientCount: { type: Number, default: 0 },
  },
  emits: ["navigate"],
  setup(props) {
    const isAdmin = computed(() => props.actor === "admin");
    const items = computed(() => [
      { id: "dashboard", label: "Главная", icon: "⌂", count: 0 },
      { id: "clients", label: "Клиенты", icon: "▤", count: props.clientCount },
      { id: "work", label: "Работа с клиентами", icon: "☎", count: props.actionCount },
      ...(isAdmin.value ? [{ id: "import", label: "Импорт данных", icon: "⇪", count: 0 }] : []),
      { id: "history", label: "История и аналитика", icon: "◔", count: 0 },
    ]);
    return { items, users };
  },
  template: `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand__mark">К</div>
        <div>
          <div class="brand__name">Контур</div>
          <div class="brand__caption">Контроль документов</div>
        </div>
      </div>

      <div class="sidebar__label">Рабочее пространство</div>
      <nav class="sidebar__nav">
        <button
          v-for="item in items"
          :key="item.id"
          type="button"
          :class="['nav-item', view === item.id ? 'is-active' : '']"
          @click="$emit('navigate', item.id)"
        >
          <span class="nav-item__icon" aria-hidden="true">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
          <span v-if="item.count" class="nav-item__count">{{ item.count }}</span>
        </button>
      </nav>

      <div class="sidebar__footer">
        <div class="sidebar__footer-title">{{ users[actor].name }}</div>
        <div class="sidebar__footer-text">Демо-режим. Данные хранятся в памяти браузера и сбрасываются при перезагрузке.</div>
      </div>
    </aside>
  `,
});
