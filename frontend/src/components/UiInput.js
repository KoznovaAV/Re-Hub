import { defineComponent } from "vue";

export default defineComponent({
  name: "UiInput",
  props: {
    modelValue: { type: [String, Number], default: "" },
    label: { type: String, default: "" },
    hint: { type: String, default: "" },
    error: { type: String, default: "" },
    placeholder: { type: String, default: "" },
    type: { type: String, default: "text" },
    required: Boolean,
    id: { type: String, default: "" },
    min: { type: [String, Number], default: undefined },
    max: { type: [String, Number], default: undefined },
  },
  emits: ["update:modelValue"],
  template: `
    <label class="field">
      <span v-if="label" class="field__label">
        {{ label }} <span v-if="required" class="field__required">*</span>
      </span>
      <input
        :id="id"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :min="min"
        :max="max"
        :class="['input', error ? 'is-invalid' : '']"
        @input="$emit('update:modelValue', $event.target.value)"
      />
      <span v-if="error" class="field__error">{{ error }}</span>
      <span v-else-if="hint" class="field__hint">{{ hint }}</span>
    </label>
  `,
});
