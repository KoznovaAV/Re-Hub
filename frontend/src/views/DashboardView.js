import {computed,defineComponent} from 'vue';
import {store,periods,clientMetrics,periodLabel} from '../mock/data.js';
import {eligibleForCall} from '../composables/call-list.mjs';
import UiCard from '../components/UiCard.js';
import UiStat from '../components/UiStat.js';
import UiButton from '../components/UiButton.js';
import UiSelect from '../components/UiSelect.js';
export default defineComponent({
 name:'DashboardView',components:{UiCard,UiStat,UiButton,UiSelect},props:{clients:{type:Array,required:true},actor:{type:String,required:true}},emits:['navigate','open-client'],
 setup(props){
  const period=computed({get:()=>store.reportPeriod,set:v=>{store.reportPeriod=v;}});
  const options=periods.map(p=>({value:p.code,label:p.label}));
  const rows=computed(()=>props.clients.map(client=>clientMetrics(client,period.value)));
  const candidates=computed(()=>props.clients.filter(c=>!c.owner&&eligibleForCall(c,period.value)).length);
  const missing=computed(()=>rows.value.filter(m=>m.missing).length);
  const unsent=computed(()=>rows.value.filter(m=>!m.missing).reduce((sum,m)=>sum+m.unsent,0));
  return {period,options,candidates,missing,unsent,periodLabel};
 },
 template:`<div class="page"><div class="page__header"><div><h1>Подготовить обзвон</h1><p class="page__subtitle">Выберите период, проверьте данные и сформируйте список для операторов.</p></div><UiSelect v-model="period" :options="options" label="Период документов" /></div>
 <div class="grid grid--3 section"><UiStat label="Кандидатов на обзвон" :value="candidates" :hint="periodLabel(period)" /><UiStat label="Непереданных документов" :value="unsent" hint="Только наблюдения выбранного периода" /><UiStat label="Клиентов без среза" :value="missing" hint="Нет среза не означает нулевой долг" /></div>
 <div class="grid grid--2 section"><UiCard title="1. Подготовить данные"><p>Загрузите клиентов и срез. Корректные строки можно принять отдельно от ошибочных.</p><UiButton @click="$emit('navigate','import')">Открыть импорт</UiButton></UiCard>
 <UiCard title="2. Сформировать список"><p>Период сохраняется. Задайте количество документов, долю и историю звонков. Включите кандидатов на обзвон и проверьте результат.</p><UiButton @click="$emit('navigate','clients')">Настроить список обзвона</UiButton></UiCard>
 <UiCard title="3. Работа операторов"><p>Мои клиенты, свободный пул и общий список для передачи работы.</p><UiButton @click="$emit('navigate','work')">Открыть работу с клиентами</UiButton></UiCard>
 <UiCard title="Аналитика по периодам"><p>Сравнение срезов вынесено отдельно от ежедневной работы.</p><UiButton @click="$emit('navigate','history')">Сравнить периоды</UiButton></UiCard></div></div>`
});
