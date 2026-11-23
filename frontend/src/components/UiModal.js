import { defineComponent } from "vue";

export default defineComponent({
  name: "UiModal",
  props: {
    open: Boolean,
    title: { type: String, default: "" },
    subtitle: { type: String, default: "" },
    size: { type: String, default: "md" },
  },
  emits: ["close"],
  template: `
    <Teleport to="body">
      <div v-if="open" class="modal-backdrop" @click.self="$emit('close')">
        <div :class="['modal', size === 'lg' ? 'modal--lg' : '']" role="dialog" aria-modal="true">
          <header class="modal__header">
            <div>
              <div class="modal__title">{{ title }}</div>
              <div v-if="subtitle" class="modal__subtitle">{{ subtitle }}</div>
            </div>
            <button type="button" class="btn btn--icon btn--ghost" aria-label="Закрыть" @click="$emit('close')">×</button>
          </header>
          <div class="modal__body"><slot /></div>
          <footer v-if="$slots.footer" class="modal__footer"><slot name="footer" /></footer>
        </div>
      </div>
    </Teleport>
  `,
});
