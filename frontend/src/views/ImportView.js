import { computed, defineComponent, ref } from "vue";
import { importClients, importSlice, confirmClients, confirmSlice } from "../mock/api.js";
import { TODAY, formatDate } from "../mock/data.js";
import { pushToast } from "../composables/useToast.js";
import UiCard from "../components/UiCard.js";
import UiBadge from "../components/UiBadge.js";
import UiButton from "../components/UiButton.js";
import UiStat from "../components/UiStat.js";
import UiTabs from "../components/UiTabs.js";
import UiEmpty from "../components/UiEmpty.js";

export default defineComponent({
  name: "ImportView",
  components: { UiCard, UiBadge, UiButton, UiStat, UiTabs, UiEmpty },
  props: { actor: { type: String, required: true } },
  emits: ["navigate", "open-client"],
  setup(props, { emit }) {
    const tab = ref("clients");
    const step = ref("idle");
    const result = ref(null);
    const doneSummary = ref(null);
    const loading = ref(false);
    const dragOver = ref(false);
    const fileInput = ref(null);
    const isAdmin = computed(() => props.actor === "admin");
    const canConfirm = computed(() => step.value === "preview" && result.value && !result.value.fatal);

    const tabs = [
      { value: "clients", label: "Клиенты" },
      { value: "slice", label: "Срез" },
    ];

    const demos = computed(() =>
      tab.value === "clients"
        ? [
            { kind: "success", title: "Клиенты без ошибок", text: "3 новых, 2 обновления, 0 ошибок" },
            { kind: "duplicate", title: "Дубль кода КЦР", text: "Загрузка остановится с причиной" },
          ]
        : [
            { kind: "success", title: "Срез без ошибок", text: "4 строки приняты" },
            { kind: "errors", title: "Неизвестный код и #N/A", text: "2 ошибки, можно скачать список" },
            { kind: "missing-total", title: "Без поля «Всего»", text: "Значение унаследовано из прошлого среза" },
            { kind: "missing-client", title: "Клиента нет в срезе", text: "Клиент сохранится с пометкой" },
          ],
    );

    function switchTab(value) {
      tab.value = value;
      reset();
    }

    async function run(kind) {
      step.value = "loading";
      result.value = null;
      doneSummary.value = null;
      const data = tab.value === "clients" ? await importClients(kind) : await importSlice(kind);
      result.value = data;
      step.value = data.fatal ? "error" : "preview";
    }

    async function onFile(file) {
      if (!file) return;
      const name = file.name.toLowerCase();
      let kind = "success";
      if (tab.value === "clients" && name.includes("duplicate")) kind = "duplicate";
      if (tab.value === "slice") {
        if (name.includes("error") || name.includes("n/a")) kind = "errors";
        else if (name.includes("total")) kind = "missing-total";
        else if (name.includes("missing")) kind = "missing-client";
      }
      await run(kind);
      if (result.value) result.value.fileName = file.name;
    }

    function pickFile() {
      fileInput.value?.click();
    }

    function onDrop(event) {
      dragOver.value = false;
      const file = event.dataTransfer?.files?.[0];
      onFile(file);
    }

    async function confirm() {
      loading.value = true;
      const response =
        tab.value === "clients" ? await confirmClients(result.value) : await confirmSlice(result.value);
      loading.value = false;
      if (!response.ok) {
        pushToast("Импорт не выполнен", response.message, "error");
        return;
      }
      doneSummary.value = response;
      step.value = "done";
      if (tab.value === "clients") {
        pushToast("Клиенты импортированы", `Создано: ${response.created}, обновлено: ${response.updated}.`);
      } else {
        pushToast("Срез импортирован", `Принято строк: ${response.accepted}, ошибок: ${response.errors}.`);
      }
    }

    function reset() {
      step.value = "idle";
      result.value = null;
      doneSummary.value = null;
      if (fileInput.value) fileInput.value.value = "";
    }

    function downloadErrors() {
      const errors = result.value?.errors ?? [];
      const rows = [
        ["Строка", "Колонка", "Код", "Причина", "Значение"],
        ...errors.map((error) => [error.row, error.column, error.code, error.message, error.value]),
      ];
      const csv = rows
        .map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(";"))
        .join("\r\n");
      const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `errors-${result.value?.fileName ?? "import"}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      pushToast("Список ошибок скачан", "CSV с проблемными строками сохранён.");
    }

    return {
      tab,
      step,
      result,
      doneSummary,
      loading,
      dragOver,
      fileInput,
      isAdmin,
      canConfirm,
      tabs,
      demos,
      switchTab,
      run,
      onFile,
      pickFile,
      onDrop,
      confirm,
      reset,
      downloadErrors,
      formatDate,
      TODAY,
      emit,
    };
  },
  template: `
    <div class="page">
      <div class="page__header">
        <div class="page__header-copy">
          <h1>Импорт данных</h1>
          <p class="page__subtitle">Загрузите клиентов или срез. Сначала предпросмотр, затем подтверждение.</p>
        </div>
        <div class="row">
          <UiBadge tone="accent" dot>Администратор</UiBadge>
          <UiButton variant="secondary" @click="$emit('navigate', 'clients')">К клиентам</UiButton>
        </div>
      </div>

      <div v-if="!isAdmin" class="callout callout--warning section">
        <div class="callout__icon">!</div>
        <div>Импорт доступен только администратору. Переключите пользователя в правом верхнем углу.</div>
      </div>

      <template v-else>
        <div class="row row--between section">
          <UiTabs :model-value="tab" :tabs="tabs" @update:model-value="switchTab" />
          <span class="small muted">Шаблон: согласованный XLSX · период определяется по вкладке</span>
        </div>

        <div class="grid grid--sidebar section">
          <div class="stack stack--lg">
            <UiCard v-if="step === 'idle'" title="Загрузка файла" subtitle="Перетащите файл или выберите на диске">
              <div
                :class="['dropzone', dragOver ? 'is-over' : '']"
                @dragover.prevent="dragOver = true"
                @dragleave.prevent="dragOver = false"
                @drop.prevent="onDrop"
              >
                <div class="dropzone__icon">⇪</div>
                <div class="dropzone__title">Перетащите XLSX сюда</div>
                <div class="dropzone__text">Файл не отправляется на сервер: это демо на mock-данных. Для сценария ошибки выберите демо-файл ниже.</div>
                <div class="row dropzone__actions">
                  <UiButton variant="primary" @click="pickFile">Выбрать файл</UiButton>
                  <input ref="fileInput" class="sr-only" type="file" accept=".xlsx,.xls" @change="onFile($event.target.files[0])" />
                </div>
              </div>
            </UiCard>

            <UiCard v-if="step === 'loading'" title="Проверяем файл" subtitle="Валидация периода, кодов и дублей">
              <div class="row"><span class="spinner"></span><span class="muted">Читаем строки и сверяем справочник…</span></div>
              <div class="stack stack--sm upload-progress">
                <div class="skeleton skeleton--line skeleton--w70"></div>
                <div class="skeleton skeleton--line skeleton--w92"></div>
                <div class="skeleton skeleton--line skeleton--w54"></div>
              </div>
            </UiCard>

            <UiCard v-if="step === 'error' && result" title="Импорт остановлен" subtitle="Файл не применён">
              <div class="callout callout--danger">
                <div class="callout__icon">!</div>
                <div>
                  <div class="callout__title">{{ result.errors[0]?.message }}</div>
                  <div>Исправьте файл и загрузите его снова. Частичное применение для этой ошибки запрещено.</div>
                </div>
              </div>
              <div class="stack stack--sm section">
                <div v-for="error in result.errors" :key="error.row" class="row row--between">
                  <span>Строка {{ error.row }}, колонка {{ error.column }}</span>
                  <UiBadge tone="danger">{{ error.code }}</UiBadge>
                </div>
              </div>
              <template #footer>
                <UiButton variant="secondary" @click="reset">Выбрать другой файл</UiButton>
                <UiButton variant="primary" @click="downloadErrors">Скачать проблемные строки</UiButton>
              </template>
            </UiCard>

            <UiCard v-if="step === 'preview' && result" title="Предпросмотр импорта" :subtitle="result.fileName + ' · загружен ' + formatDate(TODAY)">
              <div class="grid grid--3 section">
                <UiStat v-if="tab === 'clients'" label="Будет создано" :value="result.counters.created" tone="accent" />
                <UiStat v-if="tab === 'clients'" label="Будет обновлено" :value="result.counters.updated" />
                <UiStat v-if="tab === 'slice'" label="Будет принято" :value="result.counters.accepted" tone="accent" />
                <UiStat label="Ошибок" :value="result.counters.errors" :tone="result.counters.errors ? 'danger' : ''" />
                <UiStat label="Строк в файле" :value="result.counters.total" />
              </div>

              <div v-if="result.notes?.length" class="stack stack--sm section">
                <div v-for="note in result.notes" :key="note" class="callout callout--accent">
                  <div class="callout__icon">i</div>
                  <div>{{ note }}</div>
                </div>
              </div>

              <div v-if="result.missingClient" class="callout callout--warning section">
                <div class="callout__icon">!</div>
                <div><strong>{{ result.missingClient.name }}</strong> отсутствует в новом срезе. После подтверждения клиент не удалится, а получит пометку «нет в последнем срезе».</div>
              </div>

              <div class="table-wrap section">
                <table class="table">
                  <thead>
                    <tr>
                      <th>Строка</th>
                      <th>Код КЦР</th>
                      <th>Клиент</th>
                      <th>Всего</th>
                      <th>Не передано</th>
                      <th>Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in result.rows" :key="row.row">
                      <td class="mono">{{ row.row }}</td>
                      <td class="mono">{{ row.externalId }}</td>
                      <td>
                        <div class="table__primary">{{ row.name }}</div>
                        <div v-if="row.inheritedTotal" class="table__secondary">Всего унаследовано: {{ row.inheritedTotal }}</div>
                      </td>
                      <td>{{ row.total ?? row.inheritedTotal ?? '—' }}</td>
                      <td>{{ row.unsent ?? '—' }}</td>
                      <td>
                        <UiBadge :tone="row.status === 'error' ? 'danger' : row.action === 'create' ? 'accent' : 'success'">
                          {{ row.status === 'error' ? 'Ошибка' : row.action === 'create' ? 'Создать' : 'Обновить' }}
                        </UiBadge>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div v-if="result.errors.length" class="section">
                <div class="section__header">
                  <div class="section__title"><h2>Ошибки</h2><span class="section__count">{{ result.errors.length }}</span></div>
                  <UiButton size="sm" variant="secondary" @click="downloadErrors">Скачать CSV</UiButton>
                </div>
                <div class="table-wrap">
                  <table class="table">
                    <thead><tr><th>Строка</th><th>Колонка</th><th>Код</th><th>Причина</th></tr></thead>
                    <tbody>
                      <tr v-for="error in result.errors" :key="error.row + error.code">
                        <td class="mono">{{ error.row }}</td>
                        <td>{{ error.column }}</td>
                        <td><UiBadge tone="danger">{{ error.code }}</UiBadge></td>
                        <td>{{ error.message }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <template #footer>
                <UiButton variant="secondary" @click="reset">Отменить</UiButton>
                <UiButton variant="primary" :loading="loading" :disabled="!canConfirm" @click="confirm">Подтвердить импорт</UiButton>
              </template>
            </UiCard>

            <UiCard v-if="step === 'done'" title="Импорт завершён" subtitle="Изменения применены к демо-базе">
              <div class="callout callout--accent section">
                <div class="callout__icon">✓</div>
                <div>
                  <div class="callout__title">{{ tab === 'clients' ? 'Клиенты обновлены' : 'Срез принят' }}</div>
                  <div v-if="tab === 'clients'">Создано: {{ doneSummary.created }}, обновлено: {{ doneSummary.updated }}. Клиенты, которых нет в файле, не удалены.</div>
                  <div v-else>Принято строк: {{ doneSummary.accepted }}, ошибок: {{ doneSummary.errors }}. Данные доступны в карточках клиентов.</div>
                </div>
              </div>
              <div class="row">
                <UiButton variant="primary" @click="reset">Загрузить ещё</UiButton>
                <UiButton variant="secondary" @click="$emit('navigate', 'clients')">Перейти к клиентам</UiButton>
              </div>
            </UiCard>
          </div>

          <div class="stack stack--lg">
            <UiCard title="Демо-сценарии" subtitle="Нажмите, чтобы воспроизвести сценарий из ТЗ">
              <div class="demo-list">
                <button v-for="demo in demos" :key="demo.kind" type="button" class="demo-item" @click="run(demo.kind)">
                  <span>
                    <span class="demo-item__title">{{ demo.title }}</span>
                    <span class="demo-item__text">{{ demo.text }}</span>
                  </span>
                  <span class="muted">→</span>
                </button>
              </div>
            </UiCard>

            <UiCard title="Правила импорта" soft>
              <div class="stack stack--sm small">
                <div class="row row--top"><span class="badge badge--danger">1</span><span>Дубль кода КЦР в одном файле останавливает загрузку.</span></div>
                <div class="row row--top"><span class="badge badge--warning">2</span><span>Неизвестный код — ошибка строки, валидные строки можно принять.</span></div>
                <div class="row row--top"><span class="badge badge--warning">3</span><span>#N/A отклоняется; поведение требует уточнения в ТЗ.</span></div>
                <div class="row row--top"><span class="badge badge--accent">4</span><span>Без поля «Всего» значение наследуется из прошлого среза.</span></div>
                <div class="row row--top"><span class="badge badge--success">5</span><span>Клиент, которого нет в срезе, не удаляется.</span></div>
              </div>
            </UiCard>

            <UiCard v-if="result" title="Текущий файл" soft>
              <div class="file-chip">▤ {{ result.fileName }}</div>
              <div class="small muted import-note">Дата загрузки: {{ formatDate(TODAY) }}</div>
              <div class="small muted import-note">Предпросмотр не меняет данные. Изменения применяются только по кнопке «Подтвердить импорт».</div>
            </UiCard>
          </div>
        </div>
      </template>
    </div>
  `,
});
