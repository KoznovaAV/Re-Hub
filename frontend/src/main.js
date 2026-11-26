import { createApp, watch } from "vue";
import App from "./App.js";
import {store,setToday,periods} from './mock/data.js';
import {reloadWorkspace} from './composables/live-api.js';
import {pushToast} from './composables/useToast.js';

const requestedPeriod=new URLSearchParams(window.location.search).get('period');
try {
 const config=await fetch('/app-config').then(r=>{if(!r.ok)throw new Error('Не удалось загрузить конфигурацию');return r.json()});
 store.live=config.live;
 if(store.live){setToday(new Date().toISOString().slice(0,10));store.clients=[];await reloadWorkspace();}
}catch(error){store.live=true;store.clients=[];pushToast('Не удалось загрузить данные',error.message,'error');}
if(requestedPeriod&&periods.some(p=>p.code===requestedPeriod))store.reportPeriod=requestedPeriod;
createApp(App).mount('#app');
watch(()=>store.reportPeriod,value=>{
 if(!value)return;
 const url=new URL(window.location.href);url.searchParams.set('period',value);window.history.replaceState(null,'',url);
});
