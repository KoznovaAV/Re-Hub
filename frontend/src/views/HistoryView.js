import { computed, defineComponent } from "vue";
import { chartBucket, clientMetrics, formatDate, periods } from "../mock/data.js";
import UiCard from "../components/UiCard.js";
import UiStat from "../components/UiStat.js";
import UiBadge from "../components/UiBadge.js";
import UiButton from "../components/UiButton.js";
import UiEmpty from "../components/UiEmpty.js";

const periodIndex = (code) => periods.findIndex((item) => item.code === code);

export default defineComponent({
  name: "HistoryView",
  components: { UiCard, UiStat, UiBadge, UiButton, UiEmpty },
  props: { clients: { type: Array, required: true } },
  emits: ["open-client", "navigate"],
  setup(props) {
    const slices = computed(() => {
      const data = [];
      let previousUnsent = null;
      for (const period of periods) {
        let plan = 0;
        let unsent = 0;
        let clients = 0;
        let date = null;
        for (const client of props.clients) {
          let knownTotal = null;
          for (const entry of client.history) {
            if (periodIndex(entry.period) <= periodIndex(period.code)) knownTotal = entry.total ?? knownTotal;
          }
          const item = client.history.find((entry) => entry.period === period.code);
          if (!item) continue;
          plan += item.total ?? knownTotal ?? 0;
          unsent += item.unsent;
          clients += 1;
          if (!date || item.date > date) date = item.date;
        }
        if (!clients) continue;
        const share = plan ? Math.round((unsent / plan) * 100) : null;
        data.push({
          ...period,
          plan,
          unsent,
          clients,
          date,
          share,
          delta: previousUnsent == null ? null : unsent - previousUnsent,
        });
        previousUnsent = unsent;
      }
      const max = Math.max(...data.map((item) => item.unsent), 1);
      return data.map((item) => ({ ...item, height: chartBucket(item.unsent, max) }));
    });

    const latest = computed(() => slices.value[slices.value.length - 1] ?? null);
    const previous = computed(() => slices.value[slices.value.length - 2] ?? null);
    const totalDelta = computed(() => (latest.value && previous.value ? latest.value.unsent - previous.value.unsent : null));

    const changes = computed(() =>
      props.clients
        .map((client) => ({ client, metrics: clientMetrics(client) }))
        .filter(({ metrics }) => metrics.delta != null)
        .sort((a, b) => Math.abs(b.metrics.delta) - Math.abs(a.metrics.delta)),
    );

    return { slices, latest, previous, totalDelta, changes, formatDate };
  },
  template: `
    <div class="page">
      <div class="page__header">
        <div class="page__header-copy">
          <div class="row">
            <h1>История и аналитика</h1>
            <UiBadge tone="info" dot>Тестовые данные</UiBadge>
          </div>
          <p class="page__subtitle">Загруженные срезы, динамика передачи документов и изменения по клиентам.</p>
        </div>
        <UiButton variant="secondary" @click="$emit('navigate', 'dashboard')">На главную</UiButton>
      </div>

      <div class="grid grid--3 section">
        <UiStat label="Не передано сейчас" :value="latest ? latest.unsent : '—'" hint="По последнему срезу" tone="warning" />
        <UiStat
          label="Изменение к прошлому"
          :value="totalDelta == null ? '—' : (totalDelta > 0 ? '+' : '') + totalDelta"
          hint="Минус — долг уменьшился"
          :tone="totalDelta > 0 ? 'danger' : totalDelta < 0 ? 'success' : ''"
        />
        <UiStat label="Клиентов с изменениями" :value="changes.length" hint="Есть предыдущий срез" tone="accent" />
      </div>

      <div class="grid grid--2 section">
        <UiCard title="Динамика по периодам" subtitle="Сумма не переданных документов">
          <div class="chart">
            <div v-for="item in slices" :key="item.code" class="chart__column">
              <div class="chart__value">{{ item.unsent }}</div>
              <div class="chart__track">
                <div class="chart__bar" :class="'chart__bar--' + item.height"></div>
              </div>
              <div class="chart__label">{{ item.label }}</div>
              <div class="chart__caption">{{ item.share == null ? '—' : item.share + '%' }}</div>
            </div>
          </div>
        </UiCard>

        <UiCard title="Сравнение срезов" subtitle="Текущий и предыдущий">
          <div v-if="latest && previous" class="stack">
            <div class="compare">
              <div>
                <div class="compare__label">{{ previous.label }}</div>
                <div class="compare__value">{{ previous.unsent }}</div>
              </div>
              <div class="compare__arrow">→</div>
              <div>
                <div class="compare__label">{{ latest.label }}</div>
                <div class="compare__value">{{ latest.unsent }}</div>
              </div>
              <div class="compare__delta" :class="totalDelta < 0 ? 'change--good' : totalDelta > 0 ? 'change--bad' : ''">
                {{ totalDelta > 0 ? '+' : '' }}{{ totalDelta }}
              </div>
            </div>
            <div class="kv">
              <div class="kv__key">Клиентов в срезе</div><div class="kv__value">{{ latest.clients }}</div>
              <div class="kv__key">План документов</div><div class="kv__value">{{ latest.plan }}</div>
              <div class="kv__key">Доля долга</div><div class="kv__value">{{ latest.share == null ? '—' : latest.share + '%' }}</div>
              <div class="kv__key">Дата среза</div><div class="kv__value">{{ formatDate(latest.date) }}</div>
            </div>
          </div>
          <UiEmpty v-else icon="▤" title="Недостаточно данных" text="Нужно минимум два среза." />
        </UiCard>
      </div>

      <UiCard class="section" title="Загруженные срезы" subtitle="История импорта">
        <div class="table-wrap">
          <table class="table table--wide table--compact">
            <thead>
              <tr><th>Период</th><th>Дата</th><th>Клиентов</th><th>План</th><th>Не передано</th><th>Доля долга</th><th>Изменение</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in slices" :key="item.code">
                <td class="table__primary">{{ item.label }}</td>
                <td>{{ formatDate(item.date) }}</td>
                <td class="table__num">{{ item.clients }}</td>
                <td class="table__num">{{ item.plan }}</td>
                <td class="table__num">{{ item.unsent }}</td>
                <td class="table__num">{{ item.share == null ? '—' : item.share + '%' }}</td>
                <td class="table__num">
                  <span v-if="item.delta == null" class="muted">—</span>
                  <span v-else :class="item.delta < 0 ? 'change--good' : item.delta > 0 ? 'change--bad' : ''">{{ item.delta > 0 ? '+' : '' }}{{ item.delta }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>

      <UiCard title="Изменения по клиентам" subtitle="Нажмите на клиента, чтобы открыть карточку">
        <div class="table-wrap">
          <table class="table table--wide table--compact">
            <thead>
              <tr><th>Клиент</th><th>Прошлый срез</th><th>Текущий срез</th><th>Изменение</th><th>Динамика</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="row in changes" :key="row.client.id" class="is-clickable" @click="$emit('open-client', row.client.id)">
                <td>
                  <div class="table__primary">{{ row.client.name }}</div>
                  <div class="table__secondary mono">{{ row.client.externalId }}</div>
                </td>
                <td class="table__num">{{ row.metrics.previous ? row.metrics.previous.unsent : '—' }}</td>
                <td class="table__num">{{ row.metrics.unsent }}</td>
                <td class="table__num">
                  <span :class="row.metrics.delta < 0 ? 'change--good' : row.metrics.delta > 0 ? 'change--bad' : ''">{{ row.metrics.delta > 0 ? '+' : '' }}{{ row.metrics.delta }}</span>
                </td>
                <td><UiBadge :tone="row.metrics.delta < 0 ? 'success' : row.metrics.delta > 0 ? 'danger' : 'neutral'">{{ row.metrics.dynamics }}</UiBadge></td>
                <td class="text-right"><UiButton size="sm" variant="secondary" @click.stop="$emit('open-client', row.client.id)">Открыть</UiButton></td>
              </tr>
              <tr v-if="!changes.length">
                <td colspan="6"><UiEmpty icon="▤" title="Нет данных для сравнения" text="Загрузите минимум два среза." /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </UiCard>
    </div>
  `,
});
