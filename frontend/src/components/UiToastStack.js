import { defineComponent } from "vue";

export default defineComponent({
  name: "UiToastStack",
  props: { toasts: { type: Array, default: () => [] } },
  emits: ["dismiss"],
  template: `
    <div class="toast-stack" aria-live="polite">
      <div v-for="toast in toasts" :key="toast.id" :class="['toast', 'toast--' + toast.tone]">
        <div class="toast__body">
          <div class="toast__title">{{ toast.title }}</div>
          <div v-if="toast.text" class="toast__text">{{ toast.text }}</div>
        </div>
        <button type="button" class="toast__close" aria-label="Закрыть" @click="$emit('dismiss', toast.id)">×</button>
      </div>
    </div>
  `,
});
