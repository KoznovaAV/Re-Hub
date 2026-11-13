import { store, users, TODAY, LATEST_PERIOD } from "./data.js";

const wait = (ms = 650) => new Promise((resolve) => setTimeout(resolve, ms));

function userOf(actorId) {
  return users[actorId] ?? users.admin;
}

export async function takeClient(clientId, actorId) {
  await wait(420);
  const client = store.clients.find((item) => item.id === clientId);
  if (!client) return { ok: false, code: "NOT_FOUND", message: "Клиент не найден." };
  if (actorId === "admin") {
    return { ok: false, code: "ADMIN_CANNOT_TAKE", message: "Администратор не берёт клиентов в работу. Используйте «Переназначить»." };
  }
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
  await wait(420);
  if (actorId === "admin") {
    return { ok: false, code: "ADMIN_CANNOT_TAKE", message: "Администратор распределяет клиентов через переназначение." };
  }
  const client = store.clients.find((item) => item.id === clientId);
  if (!client) return { ok: false, code: "NOT_FOUND", message: "Клиент не найден." };
  if (client.stage === "Закрыт") return { ok: false, code: "CLOSED", message: "Цикл закрыт." };
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

export async function reassignClient(clientId, actorId, targetId) {
  await wait(420);
  if (actorId !== "admin") {
    return { ok: false, code: "FORBIDDEN", message: "Переназначить клиента может только администратор." };
  }
  const client = store.clients.find((item) => item.id === clientId);
  if (!client) return { ok: false, code: "NOT_FOUND", message: "Клиент не найден." };
  const previous = client.owner ? userOf(client.owner).name : "свободен";
  client.owner = targetId;
  client.stage = "В работе";
  client.events.unshift({
    id: `ev-${Date.now()}`,
    type: "system",
    date: TODAY,
    title: "Переназначение",
    text: `Было: ${previous}. Стало: ${userOf(targetId).name}.`,
    author: userOf(actorId).name,
  });
  return { ok: true, client, ownerName: userOf(targetId).name };
}

export async function addEvent(clientId, payload, actorId) {
  await wait(520);
  const client = store.clients.find((item) => item.id === clientId);
  if (!client) return { ok: false, message: "Клиент не найден." };
  const author = userOf(actorId).name;
  const event = {
    id: `ev-${Date.now()}`,
    type: payload.type,
    date: TODAY,
    title: payload.type === "call" ? "Звонок" : payload.type === "email" ? "Письмо" : "Комментарий",
    text: payload.comment || payload.result || "Без комментария",
    author,
    result: payload.result || null,
    promise: payload.promise || null,
  };
  client.events.unshift(event);
  if (payload.stage) client.stage = payload.stage;
  if (payload.result === "Обещание" && payload.promise) client.promise = payload.promise;
  if (payload.result === "Отказ") {
    client.stage = "Закрыт";
    client.active = false;
    client.promise = null;
  }
  return { ok: true, event };
}

export async function addToPool(ids) {
  await wait(380);
  let changed = 0;
  for (const id of ids) {
    const client = store.clients.find((item) => item.id === id);
    if (client && !client.owner) {
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
      fatal: true,
      fileName: "clients_duplicate.xlsx",
      counters: { created: 0, updated: 0, errors: 1, total: 6 },
      rows: [
        { row: 3, externalId: "1045001", name: "ООО «Альфа»", inn: "7701111111", action: "create" },
        { row: 4, externalId: "1045009", name: "ООО «Прайд»", inn: "7702222222", action: "create" },
        { row: 7, externalId: "1045009", name: "ООО «Прайд» (дубль)", inn: "7702222222", action: "create" },
      ],
      errors: [
        { row: 7, column: "A", code: "DUPLICATE_KCR", message: "Код КЦР 1045009 уже встречается в строке 4.", value: "1045009" },
      ],
      notes: ["Загрузка остановлена: сначала исправьте дубль кода КЦР в файле."],
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
  for (const row of result.rows) {
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
    const last = client.history[client.history.length - 1];
    if (last && last.period === LATEST_PERIOD) {
      last.unsent = row.unsent;
      last.total = row.total ?? last.total;
    }
    if (row.inheritedTotal && last) last.total = row.inheritedTotal;
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
