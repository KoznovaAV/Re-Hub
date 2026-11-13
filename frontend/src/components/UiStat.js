import { defineComponent } from "vue";

export default defineComponent({
  name: "UiStat",
  props: {
    label: { type: String, required: true },
    value: { type: [String, Number], required: true },
    hint: { type: String, default: "" },
    tone: { type: String, default: "" },
  },
  template: `
    <div :class="['stat', tone ? 'stat--' + tone : '']">
      <div>
        <div class="stat__label">{{ label }}</div>
        <div class="stat__value">{{ value }}</div>
      </div>
      <div v-if="hint" class="stat__hint">{{ hint }}</div>
    </div>
  `,
});
