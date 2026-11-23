import { createApp } from "vue";
import App from "./App.js";
import {store,setToday} from './mock/data.js';
import {reloadWorkspace} from './composables/live-api.js';
import {pushToast} from './composables/useToast.js';
try {
 const config=await fetch('/app-config').then(r=>{if(!r.ok)throw new Error('Не удалось загрузить конфигурацию');return r.json()});
 store.live=config.live;
 if(store.live){setToday(new Date().toISOString().slice(0,10));store.clients=[];await reloadWorkspace();}
}catch(error){store.live=true;store.clients=[];pushToast('Не удалось загрузить данные',error.message,'error');}
createApp(App).mount('#app');
