import { defineComponent } from "vue";

export default defineComponent({
  name: "UiCard",
  props: {
    title: { type: String, default: "" },
    subtitle: { type: String, default: "" },
    soft: Boolean,
    accent: Boolean,
    flush: Boolean,
  },
  template: `
    <section :class="['card', soft ? 'card--soft' : '', accent ? 'card--accent' : '']">
      <header v-if="title || $slots.header || $slots.actions" class="card__header">
        <slot name="header">
          <div>
            <div class="card__title">{{ title }}</div>
            <div v-if="subtitle" class="card__subtitle">{{ subtitle }}</div>
          </div>
        </slot>
        <div v-if="$slots.actions" class="row"><slot name="actions" /></div>
      </header>
      <div :class="['card__body', flush ? 'card__body--flush' : '']">
        <slot />
      </div>
      <footer v-if="$slots.footer" class="card__footer"><slot name="footer" /></footer>
    </section>
  `,
});
