import { computed, defineComponent } from "vue";
import { chartBucket, clientMetrics, formatDate, periods } from "../mock/data.js";
import UiStat from "../components/UiStat.js";
import UiCard from "../components/UiCard.js";
import UiBadge from "../components/UiBadge.js";
import UiButton from "../components/UiButton.js";
import UiEmpty from "../components/UiEmpty.js";

export default defineComponent({
  name: "DashboardView",
  components: { UiStat, UiCard, UiBadge, UiButton, UiEmpty },
  props: {
    clients: { type: Array, required: true },
    actor: { type: String, required: true },
  },
  emits: ["open-client", "navigate"],
  setup(props) {
    const rows = computed(() => props.clients.map((client) => ({ client, metrics: clientMetrics(client) })));
    const total = computed(() => props.clients.length);
    const withUnsent = computed(() => rows.value.filter(({ metrics }) => metrics.unsent > 0 && !metrics.missing).length);
    const inWork = computed(() => props.clients.filter((client) => client.stage === "В работе").length);
    const claimClients = computed(() => props.clients.filter((client) => (client.claims ?? []).length > 0).length);

    const chart = computed(() => {
      const data = periods.map((period) => {
        let plan = 0;
        let unsent = 0;
        let observed = 0;
        for (const client of props.clients) {
          let knownTotal = null;
          for (const entry of client.history) {
            if (periods.findIndex((item) => item.code === entry.period) <= periods.findIndex((item) => item.code === period.code)) {
              knownTotal = entry.total ?? knownTotal;
            }
          }
          const item = client.history.find((entry) => entry.period === period.code);
          if (!item) continue;
          plan += item.total ?? knownTotal ?? 0;
          unsent += item.unsent;
          observed += 1;
        }
        return { ...period, plan, unsent, observed, share: plan ? Math.round((unsent / plan) * 100) : null };
      }).filter((item) => item.observed > 0);
      const max = Math.max(...data.map((item) => item.unsent), 1);
      return data.map((item) => ({ ...item, height: chartBucket(item.unsent, max) }));
    });

    const lastTwo = computed(() => chart.value.slice(-2));
    const difference = computed(() => {
      if (lastTwo.value.length < 2) return null;
      return lastTwo.value[1].unsent - lastTwo.value[0].unsent;
    });
    const improved = computed(() => rows.value.filter(({ metrics }) => metrics.delta != null && metrics.delta < 0).length);
    const worsened = computed(() => rows.value.filter(({ metrics }) => metrics.delta != null && metrics.delta > 0).length);

    const attention = computed(() =>
      rows.value
        .filter(({ client, metrics }) => metrics.missing || metrics.needsRepeat || (client.claims ?? []).length > 0)
        .slice(0, 6),
    );

    const lastEvents = computed(() => {
      const events = [];
      for (const client of props.clients) {
        for (const event of client.events.slice(0, 2)) {
          events.push({ ...event, clientName: client.name, clientId: client.id });
        }
      }
      return events.sort((a, b) => b.date.localeCompare(a.date)).slice(0, 6);
    });

    function plural(value, forms) {
      const tail = value % 100;
      const last = value % 10;
      if (last === 1 && tail !== 11) return forms[0];
      if ([2, 3, 4].includes(last) && ![12, 13, 14].includes(tail)) return forms[1];
      return forms[2];
    }

    function attentionReason({ client, metrics }) {
      if (metrics.missing) return "Нет в последнем срезе";
      if (metrics.needsRepeat) return "Просрочено обещание";
      if ((client.claims ?? []).length) return "Есть претензия";
      return "Требует внимания";
    }

    return {
      total,
      withUnsent,
      inWork,
      claimClients,
      chart,
      lastTwo,
      difference,
      improved,
      worsened,
      attention,
      lastEvents,
      attentionReason,
      plural,
      formatDate,
    };
  },
  template: `
    <div class="page">
      <div class="page__header">
        <div class="page__header-copy">
          <div class="row">
            <h1>Главная</h1>
            <UiBadge tone="info" dot>Тестовые данные</UiBadge>
          </div>
          <p class="page__subtitle">Общая ситуация по клиентской базе, документам и взаимодействиям.</p>
        </div>
        <div class="row">
          <UiButton variant="secondary" @click="$emit('navigate', 'work')">Работа с клиентами</UiButton>
          <UiButton v-if="actor === 'admin'" variant="primary" @click="$emit('navigate', 'import')">Импорт данных</UiButton>
        </div>
      </div>

      <div class="grid grid--4 section">
        <UiStat label="Всего клиентов" :value="total" hint="В демонстрационной базе" />
        <UiStat label="С неотправленными" :value="withUnsent" hint="Есть долг по документам" tone="warning" />
        <UiStat label="В работе" :value="inWork" hint="Закреплены за операторами" tone="accent" />
        <UiStat label="С претензиями" :value="claimClients" hint="Требуют контроля" tone="danger" />
      </div>

      <div class="grid grid--2 section">
        <UiCard title="Динамика передачи документов" subtitle="Не передано по периодам, демо-данные">
          <div class="chart">
            <div v-for="item in chart" :key="item.code" class="chart__column">
              <div class="chart__value">{{ item.unsent }}</div>
              <div class="chart__track">
                <div class="chart__bar" :class="'chart__bar--' + item.height"></div>
              </div>
              <div class="chart__label">{{ item.label }}</div>
              <div class="chart__caption">{{ item.share == null ? '—' : item.share + '%' }}</div>
            </div>
          </div>
        </UiCard>

        <UiCard title="Между последними срезами" subtitle="Сравнение агрегатов">
          <div v-if="lastTwo.length === 2" class="stack">
            <div class="compare">
              <div>
                <div class="compare__label">{{ lastTwo[0].label }}</div>
                <div class="compare__value">{{ lastTwo[0].unsent }}</div>
              </div>
              <div class="compare__arrow">→</div>
              <div>
                <div class="compare__label">{{ lastTwo[1].label }}</div>
                <div class="compare__value">{{ lastTwo[1].unsent }}</div>
              </div>
              <div class="compare__delta" :class="difference < 0 ? 'change--good' : difference > 0 ? 'change--bad' : ''">
                {{ difference > 0 ? '+' : '' }}{{ difference }}
              </div>
            </div>
            <div class="grid grid--2">
              <div class="mini-stat"><span class="mini-stat__value change--good">{{ improved }}</span><span class="mini-stat__label">{{ plural(improved, ['клиент уменьшил', 'клиента уменьшили', 'клиентов уменьшили']) }} долг</span></div>
              <div class="mini-stat"><span class="mini-stat__value change--bad">{{ worsened }}</span><span class="mini-stat__label">{{ plural(worsened, ['клиент увеличил', 'клиента увеличили', 'клиентов увеличили']) }} долг</span></div>
            </div>
            <UiButton variant="secondary" block @click="$emit('navigate', 'history')">Открыть историю и аналитику</UiButton>
          </div>
          <UiEmpty v-else icon="▤" title="Недостаточно срезов" text="Для сравнения нужно минимум два периода." />
        </UiCard>
      </div>

      <div class="grid grid--2 section">
        <UiCard title="Требуют внимания" :subtitle="attention.length + ' ' + plural(attention.length, ['клиент', 'клиента', 'клиентов'])">
          <div v-if="attention.length" class="stack stack--sm">
            <button v-for="row in attention" :key="row.client.id" type="button" class="attention-item" @click="$emit('open-client', row.client.id)">
              <div>
                <div class="table__primary">{{ row.client.name }}</div>
                <div class="table__secondary">{{ attentionReason(row) }} · {{ row.metrics.ownerName }}</div>
              </div>
              <UiBadge :tone="row.metrics.missing ? 'warning' : 'danger'">{{ row.metrics.unsent }} / {{ row.metrics.total ?? '—' }}</UiBadge>
            </button>
          </div>
          <UiEmpty v-else icon="✓" title="Нет проблемных клиентов" text="Все показатели в норме." />
        </UiCard>

        <UiCard title="Последние события" subtitle="История взаимодействий">
          <div v-if="lastEvents.length" class="stack stack--sm">
            <button v-for="event in lastEvents" :key="event.id" type="button" class="event-link" @click="$emit('open-client', event.clientId)">
              <div class="row row--between">
                <div class="table__primary">{{ event.clientName }}</div>
                <span class="small muted">{{ formatDate(event.date) }}</span>
              </div>
              <div class="table__secondary">{{ event.title }} · {{ event.author }}</div>
              <div class="event__text">{{ event.text }}</div>
            </button>
          </div>
          <UiEmpty v-else icon="☎" title="Событий пока нет" text="Звонки и комментарии появятся здесь." />
        </UiCard>
      </div>
    </div>
  `,
});
