import { defineComponent } from "vue";

export default defineComponent({
  name: "UiButton",
  props: {
    variant: { type: String, default: "secondary" },
    size: { type: String, default: "md" },
    type: { type: String, default: "button" },
    disabled: Boolean,
    loading: Boolean,
    block: Boolean,
  },
  emits: ["click"],
  template: `
    <button
      :type="type"
      :disabled="disabled || loading"
      :class="['btn', 'btn--' + variant, size === 'sm' ? 'btn--sm' : size === 'lg' ? 'btn--lg' : '', block ? 'btn--block' : '']"
      @click="$emit('click', $event)"
    >
      <span v-if="loading" class="spinner" aria-hidden="true"></span>
      <slot />
    </button>
  `,
});
