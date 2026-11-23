import { defineComponent } from "vue";

export default defineComponent({
  name: "UiBadge",
  props: {
    tone: { type: String, default: "neutral" },
    dot: Boolean,
  },
  template: `
    <span :class="['badge', tone !== 'neutral' ? 'badge--' + tone : '']">
      <span v-if="dot" class="badge__dot"></span>
      <slot />
    </span>
  `,
});
