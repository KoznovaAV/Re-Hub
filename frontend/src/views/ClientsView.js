import { computed, defineComponent, reactive, ref } from "vue";
import { useClientFilters } from "../composables/useClientFilters.js";
import { addToPool, takeClient } from "../mock/api.js";
import { pushToast } from "../composables/useToast.js";
import { formatDate, meterClass } from "../mock/data.js";
import UiCard from "../components/UiCard.js";
import UiBadge from "../components/UiBadge.js";
import UiButton from "../components/UiButton.js";
import UiEmpty from "../components/UiEmpty.js";
import UiInput from "../components/UiInput.js";
import UiSelect from "../components/UiSelect.js";

export default defineComponent({
  name: "ClientsView",
  components: { UiCard, UiBadge, UiButton, UiEmpty, UiInput, UiSelect },
  props: {
    clients: { type: Array, required: true },
    actor: { type: String, required: true },
  },
  emits: ["open-client", "navigate"],
  setup(props) {
    const filters = useClientFilters(computed(() => props.clients));
    const selected = ref([]);
    const loading = reactive({});
    const isAdmin = computed(() => props.actor === "admin");

    const stageOptions = computed(() => [
      { value: "all", label: "Все этапы" },
      ...filters.stages.value.filter((item) => item !== "all").map((item) => ({ value: item, label: item })),
    ]);
    const tagOptions = computed(() => [
      { value: "all", label: "Все типы" },
      ...filters.tags.value.filter((item) => item !== "all").map((item) => ({ value: item, label: item })),
    ]);
    const shareOptions = [
      { value: "0", label: "Любая доля" },
      { value: "10", label: "от 10%" },
      { value: "20", label: "от 20%" },
      { value: "30", label: "от 30%" },
      { value: "50", label: "от 50%" },
    ];
    const ownerOptions = [
      { value: "all", label: "Все ответственные" },
      { value: "free", label: "Свободные" },
      { value: "mine", label: "Занятые" },
    ];

    const allSelected = computed(() => filters.filtered.value.length > 0 && selected.value.length === filters.filtered.value.length);
    function toggleAll() {
      selected.value = allSelected.value ? [] : filters.filtered.value.map((row) => row.client.id);
    }
    function toggle(id) {
      selected.value = selected.value.includes(id) ? selected.value.filter((item) => item !== id) : [...selected.value, id];
    }

    async function take(row) {
      if (isAdmin.value) {
        pushToast("Действие недоступно", "Администратор не берёт клиентов в работу. Откройте карточку и назначьте оператора.", "warning");
        return;
      }
      loading[row.client.id] = true;
      const result = await takeClient(row.client.id, props.actor);
      loading[row.client.id] = false;
      if (result.ok) pushToast("Клиент в работе", `${row.client.name} закреплён за ${result.ownerName}.`);
      else pushToast("Клиент недоступен", result.message, "error");
    }

    async function pool() {
      const result = await addToPool(selected.value);
      if (result.ok) {
        pushToast("Добавлено в пул", `${result.changed} клиентов доступны для обзвона.`);
        selected.value = [];
      }
    }

    function badgeTone(row) {
      if (row.metrics.missing) return "warning";
      if (row.metrics.dynamics === "Уменьшается") return "success";
      if (row.metrics.dynamics === "Растёт") return "danger";
      if (row.metrics.dynamics === "Повторный") return "info";
      return "neutral";
    }

    return {
      ...filters,
      selected,
      loading,
      isAdmin,
      stageOptions,
      tagOptions,
      shareOptions,
      ownerOptions,
      allSelected,
      toggleAll,
      toggle,
      take,
      pool,
      badgeTone,
      formatDate,
      meterClass,
    };
  },
  template: `
    <div class="page">
      <div class="page__header">
        <div class="page__header-copy">
          <h1>Клиенты</h1>
          <p class="page__subtitle">Поиск по ИНН или коду КЦР, фильтры по доле, этапу и типу. Список собирается без Excel.</p>
        </div>
        <div class="row">
          <UiButton variant="secondary" @click="reset">Сбросить фильтры</UiButton>
          <UiButton v-if="isAdmin" variant="primary" @click="$emit('navigate', 'import')">Импорт</UiButton>
        </div>
      </div>

      <UiCard class="section">
        <div class="grid grid--4">
          <div class="search">
            <span class="search__icon">⌕</span>
            <UiInput v-model="search" label="Поиск" placeholder="Название, ИНН или код КЦР" />
          </div>
          <UiSelect v-model="minShare" :options="shareOptions" label="Доля долга" />
          <UiSelect v-model="stage" :options="stageOptions" label="Этап" />
          <UiSelect v-model="tag" :options="tagOptions" label="Тип" />
        </div>
        <div class="row row--wrap row--between filters-actions">
          <div class="row row--wrap">
            <UiSelect v-model="owner" :options="ownerOptions" />
            <label class="row small muted">
              <input v-model="includeMissing" type="checkbox" />
              Показывать клиентов без наблюдения
            </label>
          </div>
          <div class="row">
            <span class="small muted">Найдено: {{ filtered.length }}</span>
            <UiButton size="sm" variant="secondary" :disabled="!selected.length" @click="pool">Добавить в пул ({{ selected.length }})</UiButton>
          </div>
        </div>
      </UiCard>

      <div class="card">
        <div class="table-wrap">
          <table class="table table--wide table--compact table--clients">
            <thead>
              <tr>
                <th>
                  <input type="checkbox" :checked="allSelected" aria-label="Выбрать всех" @change="toggleAll" />
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('code')">Код КЦР <span v-if="sortKey === 'code'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('name')">Клиент <span v-if="sortKey === 'name'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('plan')">План <span v-if="sortKey === 'plan'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('transferred')">Передано <span v-if="sortKey === 'transferred'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('percent')">% передачи <span v-if="sortKey === 'percent'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('delta')">Изменение <span v-if="sortKey === 'delta'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('stage')">Статус <span v-if="sortKey === 'stage'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('owner')">Оператор <span v-if="sortKey === 'owner'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th>
                  <button type="button" class="table__sort" @click="sortBy('promise')">Обещанный срок <span v-if="sortKey === 'promise'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
                </th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filtered" :key="row.client.id" class="is-clickable" @click="$emit('open-client', row.client.id)">
                <td @click.stop><input type="checkbox" :checked="selected.includes(row.client.id)" :aria-label="'Выбрать ' + row.client.name" @change="toggle(row.client.id)" /></td>
                <td class="mono">{{ row.client.externalId }}</td>
                <td>
                  <div class="table__primary">{{ row.client.name }}</div>
                  <div class="table__secondary">ИНН {{ row.client.inn }}</div>
                </td>
                <td class="table__num">{{ row.metrics.total ?? '—' }}</td>
                <td class="table__num">
                  <div class="table__primary">{{ row.metrics.transferred ?? '—' }}</div>
                  <div class="table__secondary">не передано {{ row.metrics.unsent }}</div>
                </td>
                <td class="table__num">
                  <div class="table__primary">{{ row.metrics.transferredPercent == null ? '—' : row.metrics.transferredPercent + '%' }}</div>
                  <div class="meter">
                    <div class="meter__fill" :class="meterClass(row.metrics.transferredPercent)"></div>
                  </div>
                </td>
                <td class="table__num">
                  <div v-if="row.metrics.delta != null" :class="row.metrics.delta < 0 ? 'change change--good' : row.metrics.delta > 0 ? 'change change--bad' : 'change'">
                    {{ row.metrics.delta > 0 ? '+' : '' }}{{ row.metrics.delta }}
                  </div>
                  <div v-else class="muted">—</div>
                  <UiBadge :tone="badgeTone(row)">{{ row.metrics.dynamics }}</UiBadge>
                </td>
                <td><UiBadge :tone="row.client.stage === 'В работе' ? 'accent' : row.client.stage === 'Закрыт' ? 'neutral' : 'warning'">{{ row.client.stage }}</UiBadge></td>
                <td>
                  <div class="table__primary">{{ row.metrics.ownerName }}</div>
                  <div v-if="row.metrics.overdue" class="table__secondary change--bad">обещание просрочено</div>
                </td>
                <td class="table__num">{{ row.client.promise ? formatDate(row.client.promise) : '—' }}</td>
                <td class="text-right">
                  <UiButton v-if="isAdmin" size="sm" variant="secondary" @click.stop="$emit('open-client', row.client.id)">Открыть</UiButton>
                  <UiButton
                    v-else-if="!row.metrics.owner && row.client.stage !== 'Закрыт'"
                    size="sm"
                    :loading="loading[row.client.id]"
                    @click.stop="take(row)"
                  >Взять</UiButton>
                  <UiButton v-else-if="row.client.owner === actor" size="sm" variant="secondary" @click.stop="$emit('open-client', row.client.id)">Открыть</UiButton>
                  <UiButton v-else size="sm" variant="secondary" @click.stop="take(row)">Занят</UiButton>
                </td>
              </tr>
              <tr v-if="!filtered.length">
                <td colspan="11">
                  <UiEmpty icon="⌕" title="Клиенты не найдены" text="Измените запрос или сбросьте фильтры.">
                    <UiButton size="sm" variant="secondary" @click="reset">Сбросить фильтры</UiButton>
                  </UiEmpty>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `,
});
