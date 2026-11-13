import { defineComponent } from "vue";

export default defineComponent({
  name: "UiEmpty",
  props: {
    icon: { type: String, default: "○" },
    title: { type: String, default: "Ничего не найдено" },
    text: { type: String, default: "" },
  },
  template: `
    <div class="empty">
      <div class="empty__icon">{{ icon }}</div>
      <div class="empty__title">{{ title }}</div>
      <div v-if="text" class="empty__text">{{ text }}</div>
      <div v-if="$slots.default" class="empty__actions"><slot /></div>
    </div>
  `,
});
