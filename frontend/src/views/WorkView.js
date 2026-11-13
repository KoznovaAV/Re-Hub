import { computed, defineComponent, reactive, ref } from "vue";
import { clientMetrics, formatDate } from "../mock/data.js";
import { takeClient, takeOverClient } from "../mock/api.js";
import { pushToast } from "../composables/useToast.js";
import UiCard from "../components/UiCard.js";
import UiBadge from "../components/UiBadge.js";
import UiButton from "../components/UiButton.js";
import UiEmpty from "../components/UiEmpty.js";
import UiTabs from "../components/UiTabs.js";

export default defineComponent({
  name: "WorkView",
  components: { UiCard, UiBadge, UiButton, UiEmpty, UiTabs },
  props: {
    clients: { type: Array, required: true },
    actor: { type: String, required: true },
  },
  emits: ["open-client"],
  setup(props) {
    const tab = ref("work");
    const loading = reactive({});
    const isAdmin = computed(() => props.actor === "admin");
    const tabs = [
      { value: "work", label: "В работе" },
      { value: "free", label: "Свободные" },
    ];

    const rows = computed(() => props.clients.map((client) => ({ client, metrics: clientMetrics(client) })));
    const workRows = computed(() => rows.value.filter(({ client }) => Boolean(client.owner)));
    const freeRows = computed(() => rows.value.filter(({ metrics }) => metrics.free));
    const current = computed(() => (tab.value === "work" ? workRows.value : freeRows.value));

    function lastInteraction(client) {
      return client.events[0]?.date ?? null;
    }

    function lastCall(client) {
      const call = client.events.find((event) => event.type === "call");
      return call ? call.result || call.title : "—";
    }

    async function take(row) {
      loading[row.client.id] = true;
      const result = await takeClient(row.client.id, props.actor);
      loading[row.client.id] = false;
      if (result.ok) pushToast("Клиент в работе", `${row.client.name}. Ответственный: ${result.ownerName}.`);
      else pushToast("Клиент недоступен", result.message, "error");
    }

    async function takeOver(row) {
      loading[row.client.id] = true;
      const result = await takeOverClient(row.client.id, props.actor);
      loading[row.client.id] = false;
      if (result.ok) pushToast("Клиент забран в работу", `${row.client.name}. Ответственный: ${result.ownerName}.`);
      else pushToast("Не удалось забрать", result.message, "error");
    }

    return {
      tab,
      tabs,
      loading,
      isAdmin,
      workRows,
      freeRows,
      current,
      lastInteraction,
      lastCall,
      take,
      takeOver,
      formatDate,
    };
  },
  template: `
    <div class="page">
      <div class="page__header">
        <div class="page__header-copy">
          <h1>Работа с клиентами</h1>
          <p class="page__subtitle">Клиенты в работе, последние взаимодействия и обещанные сроки. Демо-данные.</p>
        </div>
        <UiTabs v-model="tab" :tabs="tabs" />
      </div>

      <div v-if="tab === 'work'" class="card">
        <div class="table-wrap">
          <table class="table table--wide table--compact">
            <thead>
              <tr>
                <th>Клиент</th>
                <th>Ответственный</th>
                <th>Последнее взаимодействие</th>
                <th>Результат звонка</th>
                <th>Обещанный срок</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in workRows" :key="row.client.id" class="is-clickable" @click="$emit('open-client', row.client.id)">
                <td>
                  <div class="table__primary">{{ row.client.name }}</div>
                  <div class="table__secondary mono">{{ row.client.externalId }} · {{ row.metrics.unsent }} / {{ row.metrics.total ?? '—' }}</div>
                </td>
                <td>{{ row.metrics.ownerName }}</td>
                <td>{{ lastInteraction(row.client) ? formatDate(lastInteraction(row.client)) : '—' }}</td>
                <td>{{ lastCall(row.client) }}</td>
                <td class="table__num">
                  {{ row.client.promise ? formatDate(row.client.promise) : '—' }}
                  <div v-if="row.metrics.overdue" class="table__secondary change--bad">просрочено {{ row.metrics.overdueDays }} дн.</div>
                </td>
                <td><UiBadge :tone="row.client.stage === 'В работе' ? 'accent' : 'warning'">{{ row.client.stage }}</UiBadge></td>
                <td class="text-right">
                  <UiButton v-if="isAdmin" size="sm" variant="secondary" @click.stop="$emit('open-client', row.client.id)">Открыть</UiButton>
                  <UiButton
                    v-else-if="row.client.owner !== actor"
                    size="sm"
                    variant="secondary"
                    :loading="loading[row.client.id]"
                    @click.stop="takeOver(row)"
                  >Забрать</UiButton>
                  <UiButton v-else size="sm" variant="secondary" @click.stop="$emit('open-client', row.client.id)">Открыть</UiButton>
                </td>
              </tr>
              <tr v-if="!workRows.length">
                <td colspan="7"><UiEmpty icon="▤" title="Нет клиентов в работе" text="Возьмите клиента из свободного пула." /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else class="card">
        <div class="table-wrap">
          <table class="table table--wide table--compact">
            <thead>
              <tr>
                <th>Клиент</th>
                <th>План</th>
                <th>Передано</th>
                <th>Доля долга</th>
                <th>Обещанный срок</th>
                <th>Статус</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in freeRows" :key="row.client.id" class="is-clickable" @click="$emit('open-client', row.client.id)">
                <td>
                  <div class="table__primary">{{ row.client.name }}</div>
                  <div class="table__secondary mono">{{ row.client.externalId }} · ИНН {{ row.client.inn }}</div>
                </td>
                <td class="table__num">{{ row.metrics.total ?? '—' }}</td>
                <td class="table__num">{{ row.metrics.transferred ?? '—' }}</td>
                <td class="table__num">{{ row.metrics.share == null ? '—' : row.metrics.share + '%' }}</td>
                <td class="table__num">{{ row.client.promise ? formatDate(row.client.promise) : '—' }}</td>
                <td><UiBadge tone="warning">{{ row.client.stage }}</UiBadge></td>
                <td class="text-right">
                  <UiButton v-if="!isAdmin" size="sm" :loading="loading[row.client.id]" @click.stop="take(row)">Взять в работу</UiButton>
                  <UiButton v-else size="sm" variant="secondary" @click.stop="$emit('open-client', row.client.id)">Открыть</UiButton>
                </td>
              </tr>
              <tr v-if="!freeRows.length">
                <td colspan="7"><UiEmpty icon="✓" title="Свободных клиентов нет" text="Все клиенты закреплены." /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `,
});
