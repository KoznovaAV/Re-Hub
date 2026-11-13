import { computed, defineComponent, reactive, ref } from "vue";
import {
  LATEST_PERIOD,
  TODAY,
  clientMetrics,
  formatDate,
  periodLabel,
  users,
} from "../mock/data.js";
import { addEvent, reassignClient, takeClient, takeOverClient } from "../mock/api.js";
import { pushToast } from "../composables/useToast.js";
import UiCard from "../components/UiCard.js";
import UiBadge from "../components/UiBadge.js";
import UiButton from "../components/UiButton.js";
import UiEmpty from "../components/UiEmpty.js";
import UiInput from "../components/UiInput.js";
import UiSelect from "../components/UiSelect.js";
import UiModal from "../components/UiModal.js";

const EVENT_ICONS = { call: "☎", email: "✉", comment: "✎", system: "⚙", slice: "▤", claim: "!" };

export default defineComponent({
  name: "ClientCardView",
  components: { UiCard, UiBadge, UiButton, UiEmpty, UiInput, UiSelect, UiModal },
  props: {
    clientId: { type: String, required: true },
    clients: { type: Array, required: true },
    actor: { type: String, required: true },
  },
  emits: ["back", "open-client"],
  setup(props) {
    const client = computed(() => props.clients.find((item) => item.id === props.clientId) ?? null);
    const metrics = computed(() => (client.value ? clientMetrics(client.value) : null));
    const isAdmin = computed(() => props.actor === "admin");
    const canAct = computed(() => Boolean(client.value && (isAdmin.value || client.value.owner === props.actor)));
    const loading = reactive({});
    const callOpen = ref(false);
    const reassignOpen = ref(false);
    const aiOpen = ref(false);
    const reassignTarget = ref("operator-a");
    const operatorOptions = [
      { value: "operator-a", label: "Оператор А" },
      { value: "operator-b", label: "Оператор Б" },
    ];
    const form = reactive({ type: "call", result: "Дозвон", promise: "", stage: "", comment: "" });
    const errors = reactive({ result: "", promise: "" });

    const claims = computed(() => client.value?.claims ?? []);
    const sanctions = computed(() => client.value?.sanctions ?? []);

    const timeline = computed(() => {
      if (!metrics.value) return [];
      let previousTotal = null;
      const items = metrics.value.history.map((item, index) => {
        const total = item.total ?? previousTotal;
        const share = total > 0 ? Math.round((item.unsent / total) * 100) : null;
        const row = { ...item, total, share, inherited: item.total == null && previousTotal != null, current: index === metrics.value.history.length - 1 };
        previousTotal = total;
        return row;
      });
      if (metrics.value.missing) {
        items.push({
          period: LATEST_PERIOD,
          date: null,
          total: previousTotal,
          unsent: null,
          share: null,
          missing: true,
          current: false,
        });
      }
      return items;
    });

    const stageOptions = [
      { value: "Не в работе", label: "Не в работе" },
      { value: "В работе", label: "В работе" },
      { value: "Ожидание", label: "Ожидание" },
      { value: "Закрыт", label: "Закрыт" },
    ];
    const resultOptions = [
      { value: "Дозвон", label: "Дозвон" },
      { value: "Обещание", label: "Обещание" },
      { value: "Отказ", label: "Отказ" },
      { value: "Недозвон", label: "Недозвон" },
    ];
    const typeOptions = [
      { value: "call", label: "Звонок" },
      { value: "email", label: "Письмо" },
      { value: "comment", label: "Комментарий" },
    ];

    function openCall() {
      form.type = "call";
      form.result = "Дозвон";
      form.promise = "";
      form.stage = client.value?.stage ?? "В работе";
      form.comment = "";
      errors.result = "";
      errors.promise = "";
      callOpen.value = true;
    }

    async function saveCall() {
      errors.result = form.type === "call" && !form.result ? "Укажите итог звонка." : "";
      errors.promise = form.result === "Обещание" && !form.promise ? "Укажите дату обещания." : "";
      if (form.promise && form.promise < TODAY) errors.promise = "Дата обещания не может быть в прошлом.";
      if (errors.result || errors.promise) return;
      loading.call = true;
      const result = await addEvent(client.value.id, { ...form }, props.actor);
      loading.call = false;
      if (!result.ok) {
        pushToast("Не удалось сохранить", result.message, "error");
        return;
      }
      callOpen.value = false;
      pushToast("Событие добавлено", "Звонок и итог сохранены в истории клиента.");
    }

    async function take() {
      loading.take = true;
      const result = await takeClient(client.value.id, props.actor);
      loading.take = false;
      if (result.ok) pushToast("Клиент в работе", `${client.value.name} закреплён за ${result.ownerName}.`);
      else pushToast("Клиент недоступен", result.message, "error");
    }

    async function takeOver() {
      loading.takeOver = true;
      const result = await takeOverClient(client.value.id, props.actor);
      loading.takeOver = false;
      if (result.ok) pushToast("Клиент забран в работу", `${client.value.name}. Ответственный: ${result.ownerName}.`);
      else pushToast("Не удалось забрать", result.message, "error");
    }

    async function reassign() {
      loading.reassign = true;
      const result = await reassignClient(client.value.id, props.actor, reassignTarget.value);
      loading.reassign = false;
      if (result.ok) {
        reassignOpen.value = false;
        pushToast("Ответственный изменён", `Клиент закреплён за ${result.ownerName}.`);
      } else {
        pushToast("Не удалось переназначить", result.message, "error");
      }
    }

    function plural(value, forms) {
      const tail = value % 100;
      const last = value % 10;
      if (last === 1 && tail !== 11) return forms[0];
      if ([2, 3, 4].includes(last) && ![12, 13, 14].includes(tail)) return forms[1];
      return forms[2];
    }

    function eventWord(count) {
      if (count % 10 === 1 && count % 100 !== 11) return "запись";
      if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return "записи";
      return "записей";
    }

    function badgeToneFor(dynamics) {
      if (dynamics === "Уменьшается") return "success";
      if (dynamics === "Растёт") return "danger";
      if (dynamics === "Нет наблюдения") return "warning";
      if (dynamics === "Повторный") return "info";
      return "neutral";
    }

    return {
      client,
      metrics,
      isAdmin,
      canAct,
      loading,
      callOpen,
      reassignOpen,
      aiOpen,
      reassignTarget,
      operatorOptions,
      form,
      errors,
      claims,
      sanctions,
      timeline,
      stageOptions,
      resultOptions,
      typeOptions,
      openCall,
      saveCall,
      take,
      takeOver,
      reassign,
      badgeToneFor,
      eventWord,
      plural,
      formatDate,
      periodLabel,
      users,
      TODAY,
      EVENT_ICONS,
    };
  },
  template: `
    <div v-if="client" class="page client-page">
      <div class="page__header client-heading">
        <div>
          <button type="button" class="btn btn--ghost btn--sm" @click="$emit('back')">← Назад</button>
          <div class="row row--wrap page__title-row">
            <h1>{{ client.name }}</h1>
            <UiBadge :tone="client.stage === 'В работе' ? 'accent' : client.stage === 'Закрыт' ? 'neutral' : 'warning'">{{ client.stage }}</UiBadge>
            <UiBadge :tone="badgeToneFor(metrics.dynamics)">{{ metrics.dynamics }}</UiBadge>
            <UiBadge v-if="metrics.missing" tone="warning" dot>Нет в последнем срезе</UiBadge>
          </div>
          <p class="page__subtitle mono">КЦР {{ client.externalId }} · ИНН {{ client.inn }} · КПП {{ client.kpp }}</p>
        </div>
        <div class="row row--wrap">
          <UiButton v-if="metrics.free && !isAdmin" variant="secondary" :loading="loading.take" @click="take">Взять в работу</UiButton>
          <UiButton v-if="canAct && client.stage !== 'Закрыт'" variant="primary" @click="openCall">Зафиксировать взаимодействие</UiButton>
          <UiButton v-if="!canAct && metrics.owner && !isAdmin" variant="secondary" :loading="loading.takeOver" @click="takeOver">Забрать в работу</UiButton>
          <UiButton v-if="isAdmin" variant="secondary" @click="reassignOpen = true">Переназначить</UiButton>
          <UiButton variant="secondary" @click="aiOpen = true">ИИ-помощник</UiButton>
        </div>
      </div>

      <div v-if="metrics.missing" class="callout callout--warning section">
        <div class="callout__icon">!</div>
        <div>
          <div class="callout__title">Клиента нет в последнем срезе</div>
          <div>Последний известный срез: {{ metrics.last ? periodLabel(metrics.last.period) : '—' }}, {{ metrics.unsent }} из {{ metrics.total }}. Клиент не удалён и не попадает в автоматический список. Отсутствие в выгрузке не означает отсутствие долга — правило В-30 требует уточнения.</div>
        </div>
      </div>

      <div v-if="metrics.overdue" class="callout callout--danger section">
        <div class="callout__icon">!</div>
        <div>
          <div class="callout__title">Срок обещания истёк {{ metrics.overdueDays }} дн. назад</div>
          <div>Долг: {{ metrics.unsent }} из {{ metrics.total }} ({{ metrics.share }}%). Признак «нужен повторный контакт» установлен. Решение о втором звонке принимает человек — правило В-28.</div>
        </div>
      </div>

      <div v-if="metrics.inherited" class="callout callout--accent section">
        <div class="callout__icon">i</div>
        <div>
          <div class="callout__title">Всего документов унаследовано</div>
          <div>В последнем срезе нет поля «Всего». Использовано значение {{ metrics.total }} из предыдущего среза. Доля рассчитана как {{ metrics.share }}%.</div>
        </div>
      </div>

      <div v-if="client.cycle === 'repeat'" class="callout callout--info section">
        <div class="callout__icon">↻</div>
        <div>
          <div class="callout__title">Повторный цикл</div>
          <div>Предыдущий цикл закрыт. Прежний ответственный: {{ client.previousOwner ? users[client.previousOwner].name : '—' }}. Предположение В-29: предлагать прежнего оператора и пометку о прошлой претензии; в макете показаны оба признака.</div>
        </div>
      </div>

      <div class="grid grid--sidebar">
        <div class="stack stack--lg">
          <UiCard class="client-overview" title="Документы и сроки" :subtitle="metrics.last ? 'Последний срез: ' + periodLabel(metrics.last.period) : 'Нет наблюдений'">
            <div class="grid grid--2">
              <div class="stat">
                <div class="stat__label">Всего документов</div>
                <div class="stat__value">{{ metrics.total ?? '—' }}</div>
                <div v-if="metrics.inherited" class="stat__hint">Унаследовано</div>
              </div>
              <div class="stat stat--warning">
                <div class="stat__label">Не передано</div>
                <div class="stat__value">{{ metrics.last ? metrics.unsent : '—' }}</div>
                <div class="stat__hint">{{ metrics.share == null ? 'Доля не рассчитана' : metrics.share + '% от всего' }}</div>
              </div>
              <div class="stat">
                <div class="stat__label">Динамика</div>
                <div class="stat__value">{{ metrics.dynamics }}</div>
                <div class="stat__hint">{{ metrics.delta == null ? 'Нет предыдущего среза' : (metrics.delta > 0 ? '+' : '') + metrics.delta + ' документов' }}</div>
              </div>
              <div class="stat">
                <div class="stat__label">Обещание</div>
                <div class="stat__value">{{ client.promise ? formatDate(client.promise) : '—' }}</div>
                <div class="stat__hint">{{ client.promise ? (metrics.overdue ? 'Просрочено' : 'В срок') : 'Не зафиксировано' }}</div>
              </div>
            </div>
            <div class="divider"></div>
            <div v-if="metrics.transferredPercent != null" class="client-progress">
              <div class="row row--between">
                <span>Передано оригиналов</span>
                <strong>{{ metrics.transferred }} из {{ metrics.total }}</strong>
              </div>
              <progress :value="metrics.transferredPercent" max="100" aria-label="Доля переданных оригиналов"></progress>
            </div>
            <p v-else class="muted small">Долю переданных оригиналов пока нельзя рассчитать.</p>
          </UiCard>

          <UiCard title="История срезов" subtitle="Данные и звонки прошлых циклов сохранены">
            <div class="timeline">
              <div
                v-for="item in timeline"
                :key="item.period"
                :class="['timeline__item', item.current ? 'is-current' : '', item.missing ? 'is-missing' : '']"
              >
                <div class="timeline__dot"></div>
                <div class="timeline__line"></div>
                <div class="timeline__body">
                  <div class="timeline__head">
                    <div class="timeline__period">{{ periodLabel(item.period) }}</div>
                    <div class="row">
                      <UiBadge v-if="item.missing" tone="warning">Нет в срезе</UiBadge>
                      <UiBadge v-else-if="item.closed" tone="success">Цикл закрыт</UiBadge>
                      <UiBadge v-else-if="item.current" tone="accent">Текущий</UiBadge>
                      <span class="small muted">{{ formatDate(item.date) }}</span>
                    </div>
                  </div>
                  <div v-if="!item.missing" class="timeline__values">
                    <div class="timeline__value">Всего<strong>{{ item.total ?? '—' }}</strong></div>
                    <div class="timeline__value">Не передано<strong>{{ item.unsent }}</strong></div>
                    <div class="timeline__value">Доля<strong>{{ item.share == null ? '—' : item.share + '%' }}</strong></div>
                    <div v-if="item.inherited" class="timeline__value"><UiBadge tone="accent">Всего унаследовано</UiBadge></div>
                  </div>
                  <div v-else class="event__text">Последний известный срез сохранён. Клиент исключён из автоматического списка.</div>
                </div>
              </div>
            </div>
          </UiCard>

          <UiCard title="События" :subtitle="client.events.length + ' ' + eventWord(client.events.length)">
            <template #actions>
              <UiButton v-if="canAct && client.stage !== 'Закрыт'" size="sm" variant="secondary" @click="openCall">Добавить</UiButton>
            </template>
            <div v-if="client.events.length">
              <div v-for="event in client.events" :key="event.id" class="event">
                <div class="event__icon">{{ EVENT_ICONS[event.type] || '•' }}</div>
                <div>
                  <div class="event__head">
                    <div class="event__title">{{ event.title }}</div>
                    <div class="event__date">{{ formatDate(event.date) }}</div>
                  </div>
                  <div class="event__text">{{ event.text }}</div>
                  <div v-if="event.promise" class="event__text">Обещание: {{ formatDate(event.promise) }} · {{ event.author }}</div>
                  <div v-else class="event__text">{{ event.author }}</div>
                </div>
              </div>
            </div>
            <UiEmpty v-else icon="☎" title="Событий пока нет" text="Первый звонок появится здесь." />
          </UiCard>
        </div>

        <div class="stack stack--lg">
          <UiCard title="Контакт">
            <div class="kv">
              <div class="kv__key">Контактное лицо</div><div class="kv__value">{{ client.contact.name }}</div>
              <div class="kv__key">Телефон</div><div class="kv__value">{{ client.contact.phone }}</div>
              <div class="kv__key">Email</div><div class="kv__value">{{ client.contact.email }}</div>
              <div class="kv__key">Ответственный</div><div class="kv__value">{{ metrics.ownerName }}</div>
              <div class="kv__key">Этап</div><div class="kv__value">{{ client.stage }}</div>
              <div class="kv__key">Обещание</div><div class="kv__value">{{ client.promise ? formatDate(client.promise) : '—' }}</div>
            </div>
            <div class="divider"></div>
            <div class="stack stack--sm">
              <UiButton v-if="canAct && client.stage !== 'Закрыт'" variant="primary" block @click="openCall">☎ Зафиксировать взаимодействие</UiButton>
              <UiButton v-if="metrics.free && !isAdmin" variant="secondary" block :loading="loading.take" @click="take">Взять в работу</UiButton>
              <UiButton v-if="isAdmin" variant="secondary" block @click="reassignOpen = true">Переназначить оператора</UiButton>
              <UiButton v-if="!canAct && !isAdmin" variant="secondary" block :loading="loading.takeOver" @click="takeOver">Забрать в работу</UiButton>
            </div>
          </UiCard>

          <UiCard title="Претензии и санкции" :subtitle="claims.length + sanctions.length ? claims.length + ' ' + plural(claims.length, ['претензия', 'претензии', 'претензий']) + ' · ' + sanctions.length + ' ' + plural(sanctions.length, ['санкция', 'санкции', 'санкций']) : 'Нет записей'">
            <div v-if="claims.length" class="stack stack--sm section">
              <div v-for="claim in claims" :key="claim.id" class="attention-item">
                <div>
                  <div class="table__primary">Претензия № {{ claim.number }}</div>
                  <div class="table__secondary">{{ formatDate(claim.date) }} · {{ claim.reason }}</div>
                </div>
                <UiBadge :tone="claim.status === 'Закрыта' ? 'success' : 'danger'">{{ claim.status }}</UiBadge>
              </div>
            </div>
            <div v-if="sanctions.length" class="stack stack--sm section">
              <div v-for="sanction in sanctions" :key="sanction.id" class="attention-item">
                <div>
                  <div class="table__primary">{{ sanction.type }}</div>
                  <div class="table__secondary">{{ formatDate(sanction.date) }} · {{ sanction.amount }}</div>
                </div>
                <UiBadge :tone="sanction.status === 'Списана' ? 'success' : 'warning'">{{ sanction.status }}</UiBadge>
              </div>
            </div>
            <UiEmpty v-if="!claims.length && !sanctions.length" icon="✓" title="Претензий нет" text="История претензий и санкций пуста." />
          </UiCard>

          <UiCard title="Что важно знать" soft>
            <div class="stack stack--sm small">
              <div v-if="client.previousClaim" class="callout callout--warning">
                <div class="callout__icon">!</div>
                <div><strong>Прошлая претензия.</strong> В прошлом цикле была претензия. Проверьте историю перед звонком.</div>
              </div>
              <div v-if="metrics.overdue" class="callout callout--danger">
                <div class="callout__icon">!</div>
                <div><strong>Срок прошёл.</strong> Сравните долг с обещанием: даже частичное уменьшение не закрывает вопрос автоматически.</div>
              </div>
              <div v-if="metrics.missing" class="callout callout--warning">
                <div class="callout__icon">?</div>
                <div><strong>Нет в выгрузке.</strong> Не интерпретируйте пропуск как «долга нет».</div>
              </div>
              <div v-if="metrics.inherited" class="callout callout--accent">
                <div class="callout__icon">i</div>
                <div><strong>Неполный срез.</strong> «Всего» взято из предыдущего периода, доля пересчитана.</div>
              </div>
            </div>
          </UiCard>
        </div>
      </div>

      <UiModal :open="callOpen" title="Зафиксировать событие" :subtitle="client.name" @close="callOpen = false">
        <div class="stack">
          <UiSelect v-model="form.type" :options="typeOptions" label="Тип события" />
          <template v-if="form.type === 'call'">
            <UiSelect v-model="form.result" :options="resultOptions" label="Итог звонка" required :error="errors.result" />
            <UiInput v-if="form.result === 'Обещание'" v-model="form.promise" type="date" label="Дата обещания" required :error="errors.promise" :min="TODAY" />
          </template>
          <UiSelect v-model="form.stage" :options="stageOptions" label="Этап после контакта" />
          <label class="field">
            <span class="field__label">Комментарий</span>
            <textarea v-model="form.comment" class="textarea" placeholder="Что обсудили, что обещал клиент"></textarea>
          </label>
        </div>
        <template #footer>
          <UiButton variant="secondary" @click="callOpen = false">Отмена</UiButton>
          <UiButton variant="primary" :loading="loading.call" @click="saveCall">Сохранить</UiButton>
        </template>
      </UiModal>

      <UiModal :open="reassignOpen" title="Переназначить клиента" subtitle="Доступно только администратору" @close="reassignOpen = false">
        <div class="stack">
          <div class="callout callout--accent">
            <div class="callout__icon">i</div>
            <div>Текущий ответственный: <strong>{{ metrics.ownerName }}</strong>. Переназначение попадёт в историю.</div>
          </div>
          <UiSelect
            v-model="reassignTarget"
            :options="operatorOptions"
            label="Новый ответственный"
          />
        </div>
        <template #footer>
          <UiButton variant="secondary" @click="reassignOpen = false">Отмена</UiButton>
          <UiButton variant="primary" :loading="loading.reassign" @click="reassign">Назначить</UiButton>
        </template>
      </UiModal>

      <UiModal :open="aiOpen" title="ИИ-помощник" subtitle="Только чтение · демонстрационная выжимка" size="lg" @close="aiOpen = false">
        <div class="stack">
          <div class="callout callout--accent">
            <div class="callout__icon">i</div>
            <div>Помощник анализирует только имеющиеся данные. Он не меняет статусы, не принимает решения и не выполняет действия.</div>
          </div>

          <div>
            <h3>Краткая выжимка</h3>
            <p class="muted small section">{{ client.name }} · {{ metrics.dynamics }} · {{ client.stage }}. Ответственный: {{ metrics.ownerName }}. Долг: {{ metrics.unsent }} из {{ metrics.total ?? '—' }} ({{ metrics.share == null ? '—' : metrics.share + '%' }}).</p>
          </div>

          <div class="grid grid--2">
            <div class="kv">
              <div class="kv__key">Последний срез</div><div class="kv__value">{{ metrics.last ? periodLabel(metrics.last.period) : '—' }}</div>
              <div class="kv__key">Передано</div><div class="kv__value">{{ metrics.transferred ?? '—' }}</div>
              <div class="kv__key">Не передано</div><div class="kv__value">{{ metrics.unsent }}</div>
              <div class="kv__key">Обещание</div><div class="kv__value">{{ client.promise ? formatDate(client.promise) : '—' }}</div>
            </div>
            <div class="kv">
              <div class="kv__key">Претензии</div><div class="kv__value">{{ claims.length }}</div>
              <div class="kv__key">Санкции</div><div class="kv__value">{{ sanctions.length }}</div>
              <div class="kv__key">Просрочка</div><div class="kv__value">{{ metrics.overdue ? metrics.overdueDays + ' дн.' : 'нет' }}</div>
              <div class="kv__key">Пропуск среза</div><div class="kv__value">{{ metrics.missing ? 'да' : 'нет' }}</div>
            </div>
          </div>

          <div>
            <h3>Последние взаимодействия</h3>
            <div v-if="client.events.length" class="stack stack--sm section">
              <div v-for="event in client.events.slice(0, 3)" :key="event.id" class="event-link">
                <div class="row row--between"><span class="table__primary">{{ event.title }}</span><span class="small muted">{{ formatDate(event.date) }}</span></div>
                <div class="table__secondary">{{ event.text }}</div>
              </div>
            </div>
            <div v-else class="muted small">Событий нет.</div>
          </div>

          <div v-if="claims.length">
            <h3>Претензии</h3>
            <div class="stack stack--sm section">
              <div v-for="claim in claims" :key="claim.id" class="table__secondary">№ {{ claim.number }} от {{ formatDate(claim.date) }} · {{ claim.status }} · {{ claim.reason }}</div>
            </div>
          </div>
        </div>
        <template #footer>
          <UiButton variant="secondary" @click="aiOpen = false">Закрыть</UiButton>
        </template>
      </UiModal>
    </div>

    <div v-else class="page">
      <UiEmpty icon="⌕" title="Клиент не найден" text="Вернитесь к списку и выберите клиента.">
        <UiButton variant="secondary" @click="$emit('back')">К списку</UiButton>
      </UiEmpty>
    </div>
  `,
});
