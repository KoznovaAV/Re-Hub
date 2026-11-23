import { defineComponent } from "vue";

export default defineComponent({
  name: "UiTabs",
  props: {
    modelValue: { type: String, required: true },
    tabs: { type: Array, default: () => [] },
  },
  emits: ["update:modelValue"],
  template: `
    <div class="tabs" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        type="button"
        role="tab"
        :aria-selected="modelValue === tab.value"
        :class="['tab', modelValue === tab.value ? 'is-active' : '']"
        @click="$emit('update:modelValue', tab.value)"
      >
        {{ tab.label }}
      </button>
    </div>
  `,
});
