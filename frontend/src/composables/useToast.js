import { reactive } from "vue";

export const toasts = reactive([]);
let sequence = 0;

export function dismissToast(id) {
  const index = toasts.findIndex((item) => item.id === id);
  if (index >= 0) toasts.splice(index, 1);
}

export function pushToast(title, text = "", tone = "success") {
  const id = ++sequence;
  toasts.push({ id, title, text, tone });
  window.setTimeout(() => dismissToast(id), 4200);
  return id;
}

export function useToast() {
  return { toasts, pushToast, dismissToast };
}
