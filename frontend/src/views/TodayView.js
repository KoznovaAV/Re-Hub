import { computed, defineComponent, reactive } from "vue";
import { clientMetrics, formatDate, TODAY } from "../mock/data.js";
import { takeClient } from "../mock/api.js";
import { pushToast } from "../composables/useToast.js";
import UiStat from "../components/UiStat.js";
import UiCard from "../components/UiCard.js";
import UiBadge from "../components/UiBadge.js";
import UiButton from "../components/UiButton.js";
import UiEmpty from "../components/UiEmpty.js";

export default defineComponent({
  name: "TodayView",
  components: { UiStat, UiCard, UiBadge, UiButton, UiEmpty },
  props: {
    clients: { type: Array, required: true },
    actor: { type: String, required: true },
  },
  emits: ["open-client", "navigate"],
  setup(props) {
    const rows = computed(() => props.clients.map((client) => ({ client, metrics: clientMetrics(client) })));
    const actionRows = computed(() =>
      rows.value
        .filter(({ client, metrics }) => !metrics.missing && client.stage !== "Закрыт" && (metrics.needsRepeat || metrics.overdue))
        .sort((a, b) => b.metrics.overdueDays - a.metrics.overdueDays),
    );
    const freeRows = computed(() => rows.value.filter(({ metrics }) => metrics.free).slice(0, 4));
    const missingRows = computed(() => rows.value.filter(({ metrics }) => metrics.missing));
    const shares = computed(() => rows.value.map(({ metrics }) => metrics.share).filter((value) => value != null));
    const averageShare = computed(() =>
      shares.value.length ? Math.round(shares.value.reduce((sum, value) => sum + value, 0) / shares.value.length) : 0,
    );
    const loading = reactive({});
    const isAdmin = computed(() => props.actor === "admin");

    function plural(value, forms) {
      const mod10 = value % 10;
      const mod100 = value % 100;
      if (mod10 === 1 && mod100 !== 11) return forms[0];
      if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
      return forms[2];
    }

    async function take(client) {
      loading[client.id] = true;
      const result = await takeClient(client.id, props.actor);
      loading[client.id] = false;
      if (result.ok) pushToast("Клиент взят в работу", `${client.name} закреплён за ${result.ownerName}.`);
      else pushToast("Не удалось взять клиента", result.message, "error");
    }

    return {
      TODAY,
      actionRows,
      freeRows,
      missingRows,
      averageShare,
      loading,
      isAdmin,
      take,
      formatDate,
      plural,
    };
  },
  template: `
    <div class="page">
      <div class="page__header">
        <div class="page__header-copy">
          <h1>Сегодня</h1>
          <p class="page__subtitle">Клиенты, по которым наступил срок, и свободный пул. Без поиска по таблицам.</p>
        </div>
        <div class="row">
          <UiBadge :tone="isAdmin ? 'accent' : 'info'" dot>{{ isAdmin ? 'Администратор' : 'Оператор' }}</UiBadge>
          <UiButton variant="primary" @click="$emit('navigate', 'clients')">Составить список</UiButton>
        </div>
      </div>

      <div class="grid grid--4 section">
        <UiStat label="Пора действовать" :value="actionRows.length" hint="Срок обещания истёк" tone="warning" />
        <UiStat label="Свободные клиенты" :value="freeRows.length" hint="Можно взять в работу" />
        <UiStat label="Без наблюдения" :value="missingRows.length" hint="Нет в последнем срезе" tone="danger" />
        <UiStat label="Средняя доля" :value="averageShare + '%'" hint="По всем клиентам" tone="accent" />
      </div>

      <div v-if="actionRows.length" class="callout callout--warning section">
        <div class="callout__icon">!</div>
        <div>
          <div class="callout__title">{{ actionRows.length }} {{ plural(actionRows.length, ['клиент', 'клиента', 'клиентов']) }} {{ actionRows.length === 1 ? 'требует' : 'требуют' }} повторного контакта</div>
          <div>Срок обещания прошёл, долг не закрыт. Решение о втором звонке принимает оператор.</div>
        </div>
      </div>

      <section class="section">
        <div class="section__header">
          <div class="section__title">
            <h2>Пора действовать</h2>
            <span class="section__count">{{ actionRows.length }}</span>
          </div>
          <span class="small muted">Сортировка по длительности просрочки</span>
        </div>
        <div class="card">
          <div class="table-wrap">
            <table class="table table--wide table--compact">
              <thead>
                <tr>
                  <th>Клиент</th>
                  <th>Динамика</th>
                  <th>Долг</th>
                  <th>Обещание</th>
                  <th>Просрочка</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in actionRows" :key="row.client.id" class="is-clickable" @click="$emit('open-client', row.client.id)">
                  <td>
                    <div class="table__primary">{{ row.client.name }}</div>
                    <div class="table__secondary mono">{{ row.client.externalId }} · {{ row.metrics.ownerName }}</div>
                    <div v-if="row.metrics.needsRepeat" class="table__secondary">Нужен повторный контакт</div>
                  </td>
                  <td><UiBadge :tone="row.metrics.dynamics === 'Уменьшается' ? 'warning' : 'danger'">{{ row.metrics.dynamics }}</UiBadge></td>
                  <td class="table__num">
                    <div class="table__primary">{{ row.metrics.unsent }} из {{ row.metrics.total }}</div>
                    <div class="table__secondary">{{ row.metrics.share }}%</div>
                  </td>
                  <td class="table__num">{{ formatDate(row.client.promise) }}</td>
                  <td><span class="badge badge--danger">{{ row.metrics.overdueDays }} {{ plural(row.metrics.overdueDays, ['день', 'дня', 'дней']) }}</span></td>
                  <td class="text-right">
                    <UiButton size="sm" variant="secondary" @click.stop="$emit('open-client', row.client.id)">Открыть</UiButton>
                  </td>
                </tr>
                <tr v-if="!actionRows.length">
                  <td colspan="6"><UiEmpty icon="✓" title="Нет просроченных обещаний" text="Все обещания либо в срок, либо закрыты." /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <div class="grid grid--2 section">
        <UiCard title="Свободные клиенты" subtitle="Можно взять в работу прямо из списка">
          <div v-if="freeRows.length" class="stack stack--sm">
            <div v-for="row in freeRows" :key="row.client.id" class="row row--between">
              <div>
                <div class="table__primary">{{ row.client.name }}</div>
                <div class="table__secondary">{{ row.metrics.unsent }} из {{ row.metrics.total }} · {{ row.metrics.share }}%</div>
              </div>
              <UiButton size="sm" :loading="loading[row.client.id]" :disabled="isAdmin" @click="take(row.client)">
                {{ isAdmin ? 'Только оператор' : 'Взять' }}
              </UiButton>
            </div>
          </div>
          <UiEmpty v-else icon="▤" title="Свободных клиентов нет" text="Все клиенты закреплены за операторами." />
        </UiCard>

        <UiCard title="Без наблюдения" subtitle="Клиент не удалён, но исключён из автосписка">
          <div v-if="missingRows.length" class="stack stack--sm">
            <div v-for="row in missingRows" :key="row.client.id" class="row row--between">
              <div>
                <div class="table__primary">{{ row.client.name }}</div>
                <div class="table__secondary">Последний срез: {{ row.metrics.last ? row.metrics.last.period : '—' }}</div>
              </div>
              <UiButton size="sm" variant="secondary" @click="$emit('open-client', row.client.id)">Открыть</UiButton>
            </div>
          </div>
          <UiEmpty v-else icon="✓" title="Все клиенты в последнем срезе" text="Пропусков нет." />
        </UiCard>
      </div>
    </div>
  `,
});
