import { defineComponent } from "vue";

export default defineComponent({
  name: "UiSelect",
  props: {
    modelValue: { type: [String, Number], default: "" },
    label: { type: String, default: "" },
    hint: { type: String, default: "" },
    error: { type: String, default: "" },
    options: { type: Array, default: () => [] },
    required: Boolean,
    id: { type: String, default: "" },
  },
  emits: ["update:modelValue"],
  template: `
    <label class="field">
      <span v-if="label" class="field__label">
        {{ label }} <span v-if="required" class="field__required">*</span>
      </span>
      <select
        :id="id"
        :value="modelValue"
        :class="['select', error ? 'is-invalid' : '']"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <option v-for="option in options" :key="option.value ?? option" :value="option.value ?? option">
          {{ option.label ?? option }}
        </option>
      </select>
      <span v-if="error" class="field__error">{{ error }}</span>
      <span v-else-if="hint" class="field__hint">{{ hint }}</span>
    </label>
  `,
});
