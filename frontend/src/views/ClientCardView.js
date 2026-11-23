import {callSummary} from "../composables/call-list.mjs";
import { computed, defineComponent, reactive, ref } from "vue";
import {
  store,
  TODAY,
  clientMetrics,
  formatDate,
  periodLabel,
  users,
} from "../mock/data.js";
import { addEvent, takeClient, takeOverClient, reassignClient, releaseClient, addClientAction } from "../mock/api.js";
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
    const metrics = computed(() => (client.value ? clientMetrics(client.value,store.reportPeriod) : null));
    const isAdmin = computed(() => props.actor === "admin");
    const canAct = computed(() => Boolean(client.value && (!isAdmin.value && client.value.owner === props.actor)));
    const loading = reactive({});
    const callOpen = ref(false);
    const transferOpen=ref(false),actionOpen=ref(false),target=ref('operator-b');
    const operatorOptions=Object.entries(users).filter(([key,u])=>u.role==='operator').map(([value,u])=>({value,label:u.name}));
    const actionForm=reactive({kind:'claim',number:'',date:TODAY,status:'Направлена',comment:''});
    const promiseOptions=[{value:'custom',label:'Своя дата'},{value:'month',label:'Конец текущего месяца'},{value:'next-month',label:'Конец следующего месяца'}];

    const form = reactive({ date:TODAY,promiseChoice:"custom", callbackOn: "", type: "call", result: "Дозвон", promise: "", comment: "" });
    const errors = reactive({ result: "", promise: "" });

    const lastCall=computed(()=>client.value?callSummary(client.value):{status:"Не звонили",count:0,missed:0});
    const claims = computed(() => client.value?.claims ?? []);
    const sanctions = computed(() => client.value?.sanctions ?? []);

    const interactions = computed(() => (client.value?.events ?? []).filter(e=>["call","email","comment"].includes(e.type)));
    const timeline = computed(() => {
      if (!metrics.value) return [];
      let previousTotal = null;
      const items = metrics.value.history.map((item, index) => {
        if(index===0||metrics.value.history[index-1].period!==item.period)previousTotal=null;
 const total = item.total ?? previousTotal;
        const share = total > 0 ? Math.round((item.unsent / total) * 100) : null;
        const row = { ...item, total, share, inherited: item.inherited || item.total == null && previousTotal != null, current: index === metrics.value.history.length - 1 };
        previousTotal = total;
        return row;
      });
      if (metrics.value.missing) {
        items.push({
          period: store.reportPeriod,
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

    const resultOptions = [
      { value: "Дозвон", label: "Дозвон" },
      { value: "Обещание", label: "Обещание" },
      { value: "Отказ", label: "Отказ" },
      {value:"Перенос",label:"Перенос звонка"},
      {value:"Не тот администратор",label:"Не тот администратор"},
      { value: "Недозвон", label: "Недозвон" },
    ];
    const typeOptions = [
      { value: "call", label: "Звонок" },
      { value: "email", label: "Письмо" },
      { value: "comment", label: "Комментарий" },
    ];

    function openCall() {
      form.type = "call";
 form.date=TODAY;form.promiseChoice="custom";
      form.result = "Дозвон";
      form.promise = "";
      form.callbackOn = "";
      form.comment = "";
      errors.result = "";
      errors.promise = "";
      callOpen.value = true;
    }

    async function saveCall() {
      if(form.type==='call'&&form.result==='Обещание'&&form.promiseChoice!=='custom'){
       const [y,m]=form.date.split('-').map(Number);const end=new Date(Date.UTC(y,m+(form.promiseChoice==='next-month'?1:0),0));form.promise=end.toISOString().slice(0,10);
      }

      errors.result = form.type === "call" && !form.result ? "Укажите итог звонка." : "";
      if (form.type === "call" && form.result === "Перенос" && (!form.callbackOn || form.callbackOn < form.date)) { errors.promise = "Укажите дату повторного звонка не раньше сегодня."; return; }
      errors.promise = form.type === "call" && form.result === "Обещание" && !form.promise ? "Укажите дату обещания." : "";
      if (form.type === "call" && form.result === "Обещание" && form.promise && form.promise < form.date) errors.promise = "Дата обещания не может быть в прошлом.";
      if (errors.result || errors.promise) return;
      loading.call = true;
      const payload = {type:form.type,comment:form.comment,date:form.date};
      if(form.type === 'call') {
        payload.result=form.result;
        if(form.result === 'Обещание'){payload.promise=form.promise;payload.promiseLabel=promiseOptions.find(o=>o.value===form.promiseChoice)?.label;}
        if(form.result === 'Перенос')payload.callbackOn=form.callbackOn;
      }
      const result = await addEvent(client.value.id, payload, props.actor);
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


    async function transfer(){const r=await reassignClient(client.value.id,props.actor,target.value);if(r.ok){transferOpen.value=false;pushToast('Клиент передан','Ответственный изменён');}else pushToast('Не удалось передать',r.message,'error');}
    async function release(){const r=await releaseClient(client.value.id,props.actor);if(r.ok)pushToast('Клиент освобождён','Освобождение записано в истории');else pushToast('Не удалось освободить',r.message,'error');}
    async function saveAction(){const r=await addClientAction(client.value.id,{...actionForm},props.actor);if(r.ok){actionOpen.value=false;pushToast('Запись сохранена','Реквизиты письма добавлены в историю');}else pushToast('Не удалось сохранить',r.message,'error');}

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
      metrics,lastCall,
      isAdmin,
      canAct,
      loading,
      callOpen, transferOpen, actionOpen,target,operatorOptions,transfer,release,actionForm,saveAction,promiseOptions,
      form,
      errors,
      claims,
      sanctions,
      timeline,
      resultOptions,
      typeOptions,
      openCall,
      saveCall,
      take,
      takeOver,
      badgeToneFor,
      eventWord,
      plural,
      formatDate,
      periodLabel,
      users,
      TODAY,
      EVENT_ICONS, interactions,
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
          <UiButton v-if="canAct" variant="secondary" @click="transferOpen=true">Передать оператору</UiButton>
 <UiButton v-if="canAct" variant="secondary" @click="release">Освободить</UiButton>
 <UiButton v-if="isAdmin" variant="secondary" @click="actionOpen=true">Претензия / санкция</UiButton>
 <UiButton v-if="metrics.free && !isAdmin" variant="secondary" :loading="loading.take" @click="take">Взять в работу</UiButton>
          <UiButton v-if="canAct && client.stage !== 'Закрыт'" variant="primary" @click="openCall">Зафиксировать взаимодействие</UiButton>
          <UiButton v-if="!canAct && metrics.owner && !isAdmin" variant="secondary" :loading="loading.takeOver" @click="takeOver">Забрать в работу</UiButton>
        </div>
      </div>

      <UiCard title="Связаться с клиентом" class="section">
        <div v-if="client.contact.details" class="section">{{ client.contact.details }}</div>
 <div class="grid grid--2"><div><strong>{{ client.contact.name }}</strong><p><a v-if="client.contact.phone && client.contact.phone !== '—'" :href="'tel:'+client.contact.phone">{{ client.contact.phone }}</a><span v-else>Телефон не указан</span></p><a v-if="client.contact.email && client.contact.email !== '—'" :href="'mailto:'+client.contact.email">{{ client.contact.email }}</a><span v-else>Почта не указана</span></div>
        <div><strong>Последний звонок</strong><p>{{ lastCall.status }}</p><p>Звонков: {{ lastCall.count }}. Недозвонов: {{ lastCall.missed }}.</p><p v-if="lastCall.lastDate">Дата звонка: {{ formatDate(lastCall.lastDate) }}</p><p v-if="lastCall.callbackOn">Перезвонить: {{ formatDate(lastCall.callbackOn) }}</p></div>
        </div>
      </UiCard>
      <div v-if="metrics.missing" class="callout callout--warning section">
        <div class="callout__icon">!</div>
        <div>
          <div class="callout__title">Клиента нет в последнем срезе</div>
          <div>Последний известный срез: {{ metrics.last ? periodLabel(metrics.last.period) : '—' }}, {{ metrics.unsent }} из {{ metrics.total }}. Клиент не удалён и не попадает в автоматический список. Отсутствие в выгрузке не означает отсутствие долга — правило В-30 требует уточнения.</div>
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
          <UiCard title="События" :subtitle="interactions.length + ' ' + eventWord(interactions.length)">
            <template #actions>
              <UiButton v-if="canAct && client.stage !== 'Закрыт'" size="sm" variant="secondary" @click="openCall">Добавить</UiButton>
            </template>
            <div v-if="interactions.length">
              <div v-for="event in interactions" :key="event.id" class="event">
                <div class="event__icon">{{ EVENT_ICONS[event.type] || '•' }}</div>
                <div>
                  <div class="event__head">
                    <div class="event__title">{{ event.title }}</div>
                    <div class="event__date">{{ formatDate(event.date) }}</div>
                  </div>
                  <div class="event__text">{{ event.text }}</div>
                  <div v-if="event.callbackOn">Перезвонить: {{ formatDate(event.callbackOn) }}</div>
                  <div v-if="event.promise" class="event__text">Обещание: {{ formatDate(event.promise) }} · {{ event.author }}</div>
                  <div v-else class="event__text">{{ event.author }}</div>
                </div>
              </div>
            </div>
            <UiEmpty v-else icon="☎" title="Событий пока нет" text="Первый звонок появится здесь." />
          </UiCard>
          <UiCard title="Документы выбранного периода" :subtitle="metrics.last ? periodLabel(metrics.last.period) : 'Нет наблюдения'">
            <div class="kv"><div class="kv__key">Всего</div><div class="kv__value">{{ metrics.total ?? '-' }}</div>
            <div class="kv__key">Не передано</div><div class="kv__value">{{ metrics.missing ? 'Нет среза' : metrics.unsent }}</div>
            <div class="kv__key">Доля долга</div><div class="kv__value">{{ metrics.missing || metrics.share == null ? '-' : metrics.share + '%' }}</div>
            <div class="kv__key">Срок передачи</div><div class="kv__value">{{ client.promise ? formatDate(client.promise) : 'Не указан' }}</div></div>
          </UiCard>

          <UiCard title="История срезов" subtitle="Данные и звонки прошлых циклов сохранены">
            <div class="timeline">
              <div
                v-for="item in timeline"
                :key="item.period + '-' + (item.date ?? 'missing')"
                :class="['timeline__item', item.current ? 'is-current' : '', item.missing ? 'is-missing' : '']"
              >
                <div class="timeline__dot"></div>
                <div class="timeline__line"></div>
                <div class="timeline__body">
                  <div class="timeline__head">
                    <div class="timeline__period">{{ periodLabel(item.period) }}<span v-if="item.date"> · {{ formatDate(item.date) }}</span></div>
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


        </div>

        <div class="stack stack--lg">
          <UiCard title="Работа с клиентом"><div class="kv">
            <div class="kv__key">Ответственный</div><div class="kv__value">{{ metrics.ownerName }}</div>
            <div class="kv__key">Этап обзвона</div><div class="kv__value">{{ client.stage }}</div></div>
            <p class="muted small">Клиента берёт оператор. Результат звонка сохраняется отдельно от этапа и активности клиента.</p>
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
                  <div class="table__primary">Санкция № {{ sanction.number ?? sanction.type }}</div>
                  <div class="table__secondary">{{ formatDate(sanction.date) }} · {{ sanction.comment ?? sanction.amount }}</div>
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
                <div><strong>Наступила дата звонка.</strong> Проверьте перенос последнего звонка.</div>
              </div>
              <div v-if="metrics.missing" class="callout callout--warning">
                <div class="callout__icon">?</div>
                <div><strong>Нет в выгрузке.</strong> Не интерпретируйте пропуск как «долга нет».</div>
              </div>
              <div v-if="metrics.inherited" class="callout callout--accent">
                <div class="callout__icon">i</div>
                <div><strong>Неполный срез.</strong> «Всего» взято из предыдущего среза того же периода, доля пересчитана.</div>
              </div>
            </div>
          </UiCard>
        </div>
      </div>

      <UiModal :open="callOpen" title="Зафиксировать событие" :subtitle="client.name" @close="callOpen = false">
        <UiInput v-if="form.type === 'call' && form.result === 'Перенос'" v-model="form.callbackOn" type="date" label="Дата повторного звонка" :error="errors.promise" />
        <div class="stack">
 <UiInput v-model="form.date" type="date" label="Дата события" :max="TODAY" required />
          <UiSelect v-model="form.type" :options="typeOptions" label="Тип события" />
          <template v-if="form.type === 'call'">
            <UiSelect v-model="form.result" :options="resultOptions" label="Итог звонка" required :error="errors.result" />
            <UiSelect v-if="form.result === 'Обещание'" v-model="form.promiseChoice" :options="promiseOptions" label="Срок передачи документов" />
 <UiInput v-if="form.result === 'Обещание' && form.promiseChoice === 'custom'" v-model="form.promise" type="date" label="Дата обещания" required :error="errors.promise" :min="form.date" />
          </template>
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

      <UiModal :open="transferOpen" title="Передать клиента" @close="transferOpen=false">
        <UiSelect v-model="target" :options="operatorOptions" label="Ответственный оператор" />
        <template #footer><UiButton variant="secondary" @click="transferOpen=false">Отмена</UiButton><UiButton @click="transfer">Передать</UiButton></template>
      </UiModal>
      <UiModal :open="actionOpen" title="Претензия или санкция" @close="actionOpen=false">
        <UiSelect v-model="actionForm.kind" :options="[{value:'claim',label:'Претензия'},{value:'sanction',label:'Санкция'}]" label="Вид" />
        <UiInput v-model="actionForm.number" label="Номер официального письма" required />
        <UiInput v-model="actionForm.date" type="date" label="Дата официального письма" required />
        <UiInput v-model="actionForm.status" label="Статус" required />
        <UiInput v-model="actionForm.comment" label="Комментарий" />
        <template #footer><UiButton variant="secondary" @click="actionOpen=false">Отмена</UiButton><UiButton @click="saveAction">Сохранить запись</UiButton></template>
      </UiModal>




    </div>

    <div v-else class="page">
      <UiEmpty icon="⌕" title="Клиент не найден" text="Вернитесь к списку и выберите клиента.">
        <UiButton variant="secondary" @click="$emit('back')">К списку</UiButton>
      </UiEmpty>
    </div>
  `,
});
