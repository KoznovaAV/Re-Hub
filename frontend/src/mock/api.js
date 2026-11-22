import {mutateClient,request,reloadWorkspace,actorIDs} from "../composables/live-api.js";
import { eligibleForCall } from "../composables/call-list.mjs";
import { store, users, TODAY, LATEST_PERIOD } from "./data.js";

const wait = (ms = 650) => new Promise((resolve) => setTimeout(resolve, ms));

function userOf(actorId) {
  return users[actorId] ?? users.admin;
}

export async function takeClient(clientId, actorId) {
 if(store.live)return mutateClient(clientId,"/take",{},actorId);
  await wait(420);
  const client = store.clients.find((item) => item.id === clientId);
  if (!client) return { ok: false, code: "NOT_FOUND", message: "Клиент не найден." };
  if (actorId === "admin") {
    return { ok: false, code: "ADMIN_CANNOT_TAKE", message: "Администратор готовит список; оператор берёт клиента сам." };
  }
  if (!client.pool || !eligibleForCall(client, store.reportPeriod,store.periodDates?.[store.reportPeriod])) return {ok:false,message:"Клиент недоступен в подготовленном пуле."};
  if (client.stage === "Закрыт") {
    return { ok: false, code: "CLOSED", message: "Цикл закрыт, взять клиента в работу нельзя." };
  }
  if (client.owner) {
    return {
      ok: false,
      code: "ALREADY_TAKEN",
      message: `Клиент уже в работе. Ответственный: ${userOf(client.owner).name}.`,
      ownerName: userOf(client.owner).name,
    };
  }
  client.owner = actorId;
  client.stage = "В работе";
  client.pool = false;
  client.events.unshift({
    id: `ev-${Date.now()}`,
    type: "system",
    date: TODAY,
    title: "Взятие в работу",
    text: `Ответственный: ${userOf(actorId).name}.`,
    author: userOf(actorId).name,
  });
  return { ok: true, client, ownerName: userOf(actorId).name };
}

export async function takeOverClient(clientId, actorId) {
 if(store.live)return mutateClient(clientId,"/take-over",{},actorId);
  await wait(420);
  if (actorId === "admin") {
    return { ok: false, code: "ADMIN_CANNOT_TAKE", message: "Администратор готовит список; оператор забирает клиента сам." };
  }
  const client = store.clients.find((item) => item.id === clientId);
  if (!client) return { ok: false, code: "NOT_FOUND", message: "Клиент не найден." };
  if (client.stage === "Закрыт") return { ok: false, code: "CLOSED", message: "Цикл закрыт." };
  if (!client.owner || client.active === false || client.excluded) return {ok:false,message:"Для свободного клиента используйте взятие из пула."};
  if (client.owner === actorId) return { ok: true, client, ownerName: userOf(actorId).name };
  const previous = client.owner ? userOf(client.owner).name : "свободен";
  client.owner = actorId;
  client.stage = "В работе";
  client.pool = false;
  client.events.unshift({
    id: `ev-${Date.now()}`,
    type: "system",
    date: TODAY,
    title: "Клиент забран в работу",
    text: `Было: ${previous}. Стало: ${userOf(actorId).name}.`,
    author: userOf(actorId).name,
  });
  return { ok: true, client, ownerName: userOf(actorId).name };
}

export async function addEvent(clientId, payload, actorId) {
 if(store.live)return mutateClient(clientId,"/events",{event_type:payload.type,result:payload.result,comment:payload.comment,event_date:payload.date,period_code:payload.type==='call'?store.reportPeriod:undefined,promised_at:payload.promise,promise_label:payload.promiseLabel,callback_on:payload.callbackOn},actorId);

  await wait(100);
  const client=store.clients.find(c=>c.id===clientId);
  if(!client)return {ok:false,message:"Клиент не найден."};
  if(actorId==='admin'||client.owner!==actorId)return {ok:false,message:"Взаимодействие фиксирует назначенный оператор."};
  if(payload.stage)return {ok:false,message:"Результат звонка не меняет этап работы автоматически."};
  const call=payload.type==='call';
  if(!['call','email','comment'].includes(payload.type))return {ok:false,message:"Неизвестный тип события."};
  if(!call&&(payload.result||payload.promise||payload.callbackOn))return {ok:false,message:'Поля звонка не относятся к письму или комментарию.'};
  if(call&&!['Дозвон','Недозвон','Перенос','Не тот контакт','Обещание','Отказ'].includes(payload.result))return {ok:false,message:"Укажите статус звонка."};
  const validDate=value=>/^\d{4}-\d{2}-\d{2}$/.test(value||'')&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
  const eventDate=payload.date||TODAY;
  if(!validDate(eventDate)||eventDate>TODAY)return {ok:false,message:'Укажите корректную дату события не позже сегодня.'};
  if(call&&payload.result==='Перенос'&&(!validDate(payload.callbackOn)||payload.callbackOn<eventDate))return {ok:false,message:"Укажите дату повторного звонка не раньше сегодня."};
  if(call&&payload.result==='Обещание'&&(!validDate(payload.promise)||payload.promise<eventDate))return {ok:false,message:"Укажите срок передачи документов."};
  const event={id:crypto.randomUUID(),type:payload.type,date:eventDate,promiseLabel:payload.promiseLabel||null,
    title:call?'Звонок':payload.type==='email'?'Письмо':'Комментарий',
    text:payload.comment||(call?payload.result:'Без комментария'),author:userOf(actorId).name,
    result:call?payload.result:null,promise:call&&payload.result==='Обещание'?payload.promise:null,
    callbackOn:call&&payload.result==='Перенос'?payload.callbackOn:null,period:call?store.reportPeriod:null};
  client.events.unshift(event);
 client.events.sort((a,b)=>String(b.date).localeCompare(String(a.date)));
  if(event.promise&&!client.events.some(e=>e!==event&&e.promise&&e.date>event.date))client.promise=event.promise;
  return {ok:true,event};
}

export async function addToPool(ids,actor=store.actor) {
 if(actor!=='admin')return {ok:false,message:'Только администратор готовит пул'};
 if(store.live){try{const result=await request('/pool',{method:'POST',body:{ids:ids.map(id=>store.clients.find(c=>c.id===id)?.externalId).filter(Boolean),period:store.reportPeriod},actor});await reloadWorkspace();return {ok:true,...result};}catch(e){return {ok:false,message:e.message};}}

  await wait(380);
  let changed = 0;
  for (const id of ids) {
    const client = store.clients.find((item) => item.id === id);
    if (client && !client.owner && eligibleForCall(client,store.reportPeriod,store.periodDates?.[store.reportPeriod])) {
      client.pool = true;
      changed += 1;
    }
  }
  return { ok: true, changed };
}

export async function importClients(kind) {
  await wait(900);
  if (kind === "duplicate") {
    return {
      kind: "clients",
      fatal: false,
      fileName: "clients_duplicate.xlsx",
      counters: { created: 1, updated: 0, errors: 2, total: 3 },
      rows: [
        { row: 3, externalId: "1045001", name: "ООО «Альфа»", inn: "7701111111", action: "create" },
        { row: 4, externalId: "1045009", name: "ООО «Прайд»", inn: "7702222222", action: "error", status: "error" },
        { row: 7, externalId: "1045009", name: "ООО «Прайд» (дубль)", inn: "7702222222", action: "error", status: "error" },
      ],
      errors: [
        { row: 4, column: "A", code: "DUPLICATE_KCR", message: "Неоднозначный код КЦР: строки 4 и 7.", value: "1045009" },
        { row: 7, column: "A", code: "DUPLICATE_KCR", message: "Код КЦР 1045009 уже встречается в строке 4.", value: "1045009" },
      ],
      notes: ["Строки с дублями отклонены. Корректные строки можно принять отдельно."],
    };
  }
  return {
    kind: "clients",
    fatal: false,
    fileName: "clients_november.xlsx",
    counters: { created: 3, updated: 2, errors: 0, total: 5 },
    rows: [
      { row: 3, externalId: "1045001", name: "ООО «Альфа»", inn: "7701111111", action: "create" },
      { row: 4, externalId: "1045002", name: "ООО «Бета»", inn: "7702222222", action: "create" },
      { row: 5, externalId: "1045003", name: "ООО «Гамма»", inn: "7703333333", action: "create" },
      { row: 6, externalId: "1029384", name: "ООО «Вектор»", inn: "7701234567", action: "update" },
      { row: 7, externalId: "1000002", name: "АО «Северный путь»", inn: "7802345678", action: "update" },
    ],
    errors: [],
    notes: ["Клиенты, которых нет в файле, не удаляются."],
  };
}

export async function confirmClients(result) {
  await wait(700);
  if (result.fatal) return { ok: false, message: "Импорт остановлен." };
  let created = 0;
  let updated = 0;
  for (const row of result.rows.filter(row=>row.status !== "error")) {
    const existing = store.clients.find((item) => item.externalId === row.externalId);
    if (existing) {
      existing.name = row.name;
      existing.inn = row.inn;
      updated += 1;
    } else {
      store.clients.push({
        id: `c-${row.externalId}`,
        externalId: row.externalId,
        name: row.name,
        inn: row.inn,
        kpp: "—",
        stage: "Не в работе",
        owner: null,
        active: true,
        cycle: "current",
        tags: ["Новый"],
        contact: { name: "Не указан", phone: "—", email: "—" },
        promise: null,
        pool: false,
        history: [],
        events: [{ id: `ev-${row.externalId}`, type: "system", date: TODAY, title: "Импорт клиентов", text: "Клиент создан при импорте.", author: "Система" }],
      });
      created += 1;
    }
  }
  store.importLog.unshift({
    id: `imp-${Date.now()}`,
    date: TODAY,
    kind: "Клиенты",
    file: result.fileName,
    created,
    updated,
    errors: result.errors.length,
  });
  store.lastImport = store.importLog[0];
  return { ok: true, created, updated };
}

export async function importSlice(kind) {
  await wait(950);
  const base = {
    kind: "slice",
    fatal: false,
    fileName: "slice_2026Q3.xlsx",
    counters: { accepted: 4, errors: 0, total: 4 },
    rows: [
      { row: 3, externalId: "1000002", name: "АО «Северный путь»", total: 100, unsent: 40, status: "update" },
      { row: 4, externalId: "1000003", name: "ООО «Гранит»", total: 100, unsent: 25, status: "update" },
      { row: 5, externalId: "1000005", name: "ООО «Меридиан»", total: 100, unsent: 30, status: "update" },
      { row: 6, externalId: "1000006", name: "ООО «Полярная звезда»", total: 120, unsent: 35, status: "update" },
    ],
    errors: [],
    notes: ["Период определён по вкладке файла: III кв. 2026."],
  };

  if (kind === "errors") {
    return {
      ...base,
      fileName: "slice_with_errors.xlsx",
      counters: { accepted: 2, errors: 2, total: 4 },
      rows: [
        { row: 3, externalId: "1000002", name: "АО «Северный путь»", total: 100, unsent: 40, status: "update" },
        { row: 4, externalId: "9999999", name: "Неизвестный клиент", total: 80, unsent: 12, status: "error" },
        { row: 5, externalId: "#N/A", name: "Строка с ошибкой Excel", total: 50, unsent: 5, status: "error" },
        { row: 6, externalId: "1000003", name: "ООО «Гранит»", total: 100, unsent: 25, status: "update" },
      ],
      errors: [
        { row: 4, column: "A", code: "CLIENT_UNKNOWN", message: "Код КЦР 9999999 отсутствует в справочнике клиентов.", value: "9999999" },
        { row: 5, column: "A", code: "EXCEL_CELL_ERROR", message: "В ячейке #N/A. Поведение не описано в ТЗ — строка отклонена.", value: "#N/A" },
      ],
      notes: ["Валидные строки можно принять. Ошибочные строки не попадут в срез.", "Для #N/A требуется уточнение правила у заказчика."],
    };
  }

  if (kind === "missing-total") {
    return {
      ...base,
      fileName: "slice_no_total.xlsx",
      counters: { accepted: 2, errors: 0, total: 2 },
      rows: [
        { row: 3, externalId: "1000005", name: "ООО «Меридиан»", total: null, inheritedTotal: 100, unsent: 30, status: "update" },
        { row: 4, externalId: "1000009", name: "ООО «Импульс»", total: 50, unsent: 10, status: "update" },
      ],
      notes: ["Для строки 3 поле «Всего» отсутствует. Унаследовано значение 100 из предыдущего среза.", "Доля рассчитана как 30%."],
    };
  }

  if (kind === "missing-client") {
    return {
      ...base,
      fileName: "slice_missing_client.xlsx",
      counters: { accepted: 3, errors: 0, total: 3 },
      rows: [
        { row: 3, externalId: "1000002", name: "АО «Северный путь»", total: 100, unsent: 40, status: "update" },
        { row: 4, externalId: "1000003", name: "ООО «Гранит»", total: 100, unsent: 25, status: "update" },
        { row: 5, externalId: "1000009", name: "ООО «Импульс»", total: 50, unsent: 10, status: "update" },
      ],
      missingClient: { id: "c4", externalId: "1000004", name: "ООО «Лагуна»" },
      notes: ["Клиента ООО «Лагуна» нет в новом срезе. Он не удаляется: сохраняется последний известный срез."],
    };
  }

  return base;
}

export async function confirmSlice(result) {
  await wait(700);
  for (const row of result.rows.filter((item) => item.status === "update")) {
    const client = store.clients.find((item) => item.externalId === row.externalId);
    if (!client) continue;
    const period=row.period||result.period||store.reportPeriod;
    const date=result.sliceDate||TODAY;
    const prior=client.history.filter(h=>h.period===period&&h.date<=date&&h.observed!==false).sort((a,b)=>a.date.localeCompare(b.date));
    const total=row.total??prior.filter(h=>h.total!=null).at(-1)?.total??null;
    const existing=client.history.find(h=>h.period===period&&h.date===date);
    const observation={period,date,total,unsent:row.unsent,observed:true};
    if(existing)Object.assign(existing,observation);else client.history.push(observation);
    client.events.unshift({
      id: `ev-${client.id}-${Date.now()}`,
      type: "slice",
      date: TODAY,
      title: "Новый срез",
      text: `III кв. 2026: всего ${row.total ?? row.inheritedTotal ?? "—"}, не передано ${row.unsent}.`,
      author: "Система",
    });
  }
  if (result.missingClient) {
    const client = store.clients.find((item) => item.id === result.missingClient.id);
    if (client) {
      client.events.unshift({
        id: `ev-${client.id}-${Date.now()}`,
        type: "system",
        date: TODAY,
        title: "Клиент отсутствует в срезе",
        text: "Последний известный срез сохранён. Клиент исключён из автоматического списка обзвона.",
        author: "Система",
      });
    }
  }
  store.importLog.unshift({
    id: `imp-${Date.now()}`,
    date: TODAY,
    kind: "Срез",
    file: result.fileName,
    accepted: result.counters.accepted,
    errors: result.counters.errors,
  });
  store.lastImport = store.importLog[0];
  return { ok: true, accepted: result.counters.accepted, errors: result.counters.errors };
}

export async function reassignClient(clientId,actor,target){
 if(store.live)return mutateClient(clientId,'/reassign',{user_id:actorIDs[target]},actor);
 const c=store.clients.find(c=>c.id===clientId);
 if(!c||actor==='admin'||c.owner!==actor||users[target]?.role!=='operator')return {ok:false,message:'Передачу выполняет ответственный оператор'};
 const previous=c.owner;c.owner=target;c.events.unshift({id:crypto.randomUUID(),type:'system',date:TODAY,title:'Переназначение',text:previous+' -> '+target,author:users[actor].name});return {ok:true};
}
export async function releaseClient(clientId,actor){
 if(store.live)return mutateClient(clientId,'/release',{},actor);
 const c=store.clients.find(c=>c.id===clientId);
 if(!c||actor==='admin'||c.owner!==actor)return {ok:false,message:'Освободить клиента может его ответственный оператор'};
 c.owner=null;c.stage='Не в работе';c.pool=eligibleForCall(c,store.reportPeriod);c.events.unshift({id:crypto.randomUUID(),type:'system',date:TODAY,title:'Освобождение',text:'Клиент освобождён вручную',author:users[actor].name});return {ok:true};
}
export async function addClientAction(clientId,payload,actor){
 if(store.live)return mutateClient(clientId,'/actions',payload,actor);
 const c=store.clients.find(c=>c.id===clientId);
 if(actor!=='admin'||!c||!['claim','sanction'].includes(payload.kind)||!payload.number?.trim()||!payload.date||!payload.status?.trim())return {ok:false,message:'Укажите вид, номер, дату письма и статус'};
 const action={...payload,id:crypto.randomUUID(),reason:payload.comment};
 const key=payload.kind==='claim'?'claims':'sanctions';(c[key]??=[]).unshift(action);
 c.events.unshift({id:crypto.randomUUID(),type:'claim',date:payload.date,title:payload.kind==='claim'?'Претензия':'Санкция',text:payload.number+': '+payload.status,author:users[actor].name});return {ok:true};
}
