import { reactive } from "vue";

export const TODAY = "2026-11-18";
export const LATEST_PERIOD = "2026Q3";

export const periods = [
  { code: "2025Q3", label: "III кв. 2025" },
  { code: "2025Q4", label: "IV кв. 2025" },
  { code: "2026Q1", label: "I кв. 2026" },
  { code: "2026Q2", label: "II кв. 2026" },
  { code: "2026Q3", label: "III кв. 2026" },
];

export const users = {
  admin: { id: "admin", name: "Администратор", short: "АД", role: "admin" },
  "operator-a": { id: "operator-a", name: "Оператор А", short: "А", role: "operator" },
  "operator-b": { id: "operator-b", name: "Оператор Б", short: "Б", role: "operator" },
};

const periodIndex = (code) => periods.findIndex((item) => item.code === code);

export function periodLabel(code) {
  return periods.find((item) => item.code === code)?.label ?? code;
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

export function formatShortDate(value) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "long" }).format(date);
}

export function daysBetween(from, to) {
  const a = new Date(`${from}T00:00:00`).getTime();
  const b = new Date(`${to}T00:00:00`).getTime();
  return Math.max(0, Math.round((a - b) / 86400000));
}

export function clientMetrics(client) {
  const history = [...client.history].sort((a, b) => periodIndex(a.period) - periodIndex(b.period));
  const last = history[history.length - 1] ?? null;
  const previous = history[history.length - 2] ?? null;
  const hasLatest = history.some((item) => item.period === LATEST_PERIOD);
  const missing = client.active !== false && !hasLatest;
  const inherited = Boolean(last && last.total == null && previous?.total != null);
  const total = last?.total ?? (inherited ? previous.total : null);
  const unsent = last?.unsent ?? 0;
  const transferred = total != null ? Math.max(0, total - unsent) : null;
  const share = total > 0 ? Math.round((unsent / total) * 100) : null;
  const transferredPercent = total > 0 ? Math.round((transferred / total) * 100) : null;
  const delta = previous ? unsent - previous.unsent : null;
  const overdue = Boolean(client.promise && client.promise < TODAY && unsent > 0);
  const overdueDays = overdue ? daysBetween(TODAY, client.promise) : 0;

  let dynamics = "Новый";
  if (missing) dynamics = "Нет наблюдения";
  else if (client.cycle === "repeat") dynamics = "Повторный";
  else if (previous) {
    if (delta < 0) dynamics = "Уменьшается";
    else if (delta === 0) dynamics = "Не меняется";
    else dynamics = "Растёт";
  }

  return {
    history,
    last,
    previous,
    missing,
    inherited,
    total,
    unsent,
    transferred,
    transferredPercent,
    share,
    delta,
    dynamics,
    overdue,
    overdueDays,
    needsRepeat: overdue && dynamics !== "Новый",
    owner: client.owner ? users[client.owner] : null,
    ownerName: client.owner ? users[client.owner].name : "Свободен",
    free: !client.owner && client.stage !== "Закрыт" && client.active !== false,
  };
}

export function meterClass(share) {
  if (share == null) return "meter__fill--0";
  const bucket = Math.max(0, Math.min(100, Math.round(share / 5) * 5));
  return `meter__fill--${bucket}`;
}

export function chartBucket(value, max) {
  if (!max || !value) return 0;
  return Math.max(5, Math.min(100, Math.round((value / max) * 20) * 5));
}

export const store = reactive({
  clients: [
    {
      id: "c1",
      externalId: "1029384",
      name: "ООО «Вектор»",
      inn: "7701234567",
      kpp: "770101001",
      stage: "Не в работе",
      owner: null,
      previousOwner: "operator-a",
      previousClaim: true,
      active: false,
      cycle: "repeat",
      tags: ["Повторный", "Ключевой"],
      contact: { name: "Ирина Соколова", phone: "+7 495 120-45-10", email: "i.sokolova@vector.example" },
      promise: null,
      pool: false,
      claims: [
        { id: "cl1", number: "7", date: "2025-08-14", status: "Закрыта", reason: "Просрочка передачи документов", amount: "—" },
      ],
      sanctions: [
        { id: "sn1", date: "2025-08-20", type: "Пеня", amount: "1 200 ₽", status: "Списана" },
      ],
      history: [
        { period: "2025Q3", date: "2025-10-20", total: 200, unsent: 30, observed: true },
        { period: "2025Q4", date: "2026-01-15", total: 200, unsent: 0, observed: true, closed: true },
        { period: "2026Q1", date: "2026-04-20", total: 210, unsent: 12, observed: true },
      ],
      events: [
        { id: "e1", type: "call", date: "2025-09-12", title: "Звонок", text: "Клиент подтвердил оплату до 20.09.2025.", author: "Оператор А", result: "Обещание", promise: "2025-09-20" },
        { id: "e2", type: "call", date: "2025-10-01", title: "Звонок", text: "Долг погашен, цикл закрыт. Клиент переведён в «Не в работе».", author: "Оператор А", result: "Дозвон" },
        { id: "e3", type: "system", date: "2026-04-20", title: "Новый цикл", text: "Загружен срез I кв. 2026: 210 документов, не передано 12.", author: "Система" },
      ],
    },
    {
      id: "c2",
      externalId: "1000002",
      name: "АО «Северный путь»",
      inn: "7802345678",
      kpp: "780201001",
      stage: "В работе",
      owner: "operator-a",
      active: true,
      cycle: "current",
      tags: ["Ключевой"],
      contact: { name: "Павел Крылов", phone: "+7 812 330-18-22", email: "p.krylov@northway.example" },
      promise: "2026-11-15",
      pool: false,
      history: [
        { period: "2026Q2", date: "2026-07-20", total: 100, unsent: 40, observed: true },
        { period: "2026Q3", date: "2026-10-20", total: 100, unsent: 40, observed: true },
      ],
      events: [
        { id: "e4", type: "call", date: "2026-11-01", title: "Звонок", text: "Клиент обещал погасить долг до 15.11.2026.", author: "Оператор А", result: "Обещание", promise: "2026-11-15" },
        { id: "e5", type: "slice", date: "2026-10-20", title: "Срез III кв. 2026", text: "Всего 100, не передано 40. Долг не изменился.", author: "Система" },
      ],
    },
    {
      id: "c3",
      externalId: "1000003",
      name: "ООО «Гранит»",
      inn: "5023456789",
      kpp: "502301001",
      stage: "В работе",
      owner: "operator-b",
      active: true,
      cycle: "current",
      tags: ["Повторный"],
      contact: { name: "Марина Белова", phone: "+7 498 770-11-33", email: "m.belova@granit.example" },
      promise: "2026-11-10",
      pool: false,
      claims: [
        { id: "cl2", number: "14", date: "2026-06-12", status: "Направлена", reason: "Систематическая просрочка передачи", amount: "—" },
      ],
      sanctions: [
        { id: "sn2", date: "2026-06-20", type: "Пеня", amount: "2 400 ₽", status: "Начислена" },
      ],
      history: [
        { period: "2026Q2", date: "2026-07-20", total: 100, unsent: 40, observed: true },
        { period: "2026Q3", date: "2026-10-20", total: 100, unsent: 25, observed: true },
      ],
      events: [
        { id: "e6", type: "call", date: "2026-10-28", title: "Звонок", text: "Клиент обещал частично закрыть долг до 10.11.2026.", author: "Оператор Б", result: "Обещание", promise: "2026-11-10" },
        { id: "e7", type: "claim", date: "2026-06-12", title: "Претензия", text: "Претензия № 14 от 12.06.2026, статус «Направлена».", author: "Администратор" },
      ],
    },
    {
      id: "c4",
      externalId: "1000004",
      name: "ООО «Лагуна»",
      inn: "6603456789",
      kpp: "660301001",
      stage: "В работе",
      owner: "operator-a",
      active: true,
      cycle: "current",
      tags: ["Без наблюдения"],
      contact: { name: "Сергей Титов", phone: "+7 343 210-77-05", email: "s.titov@laguna.example" },
      promise: null,
      pool: false,
      history: [{ period: "2026Q2", date: "2026-07-20", total: 100, unsent: 30, observed: true }],
      events: [
        { id: "e8", type: "call", date: "2026-09-15", title: "Звонок", text: "Клиент просил перенести контакт на октябрь.", author: "Оператор А", result: "Недозвон" },
        { id: "e9", type: "system", date: "2026-10-20", title: "Пропуск в срезе", text: "Клиента нет в срезе III кв. 2026. Последний известный срез сохранён.", author: "Система" },
      ],
    },
    {
      id: "c5",
      externalId: "1000005",
      name: "ООО «Меридиан»",
      inn: "7704567890",
      kpp: "770401001",
      stage: "В работе",
      owner: "operator-a",
      active: true,
      cycle: "current",
      tags: ["Ключевой"],
      contact: { name: "Ольга Романова", phone: "+7 495 640-22-18", email: "o.romanova@meridian.example" },
      promise: null,
      pool: false,
      history: [
        { period: "2026Q2", date: "2026-07-20", total: 100, unsent: 40, observed: true },
        { period: "2026Q3", date: "2026-10-20", total: null, unsent: 30, observed: true, note: "В файле только «Не передано»" },
      ],
      events: [
        { id: "e10", type: "system", date: "2026-10-20", title: "Срез без «Всего»", text: "Поле «Всего документов» отсутствует. Значение унаследовано: 100.", author: "Система" },
      ],
    },
    {
      id: "c6",
      externalId: "1000006",
      name: "ООО «Полярная звезда»",
      inn: "8905678901",
      kpp: "890501001",
      stage: "Не в работе",
      owner: null,
      active: true,
      cycle: "current",
      tags: ["Новый"],
      contact: { name: "Антон Лебедев", phone: "+7 921 440-09-71", email: "a.lebedev@polar.example" },
      promise: null,
      pool: true,
      history: [{ period: "2026Q3", date: "2026-10-20", total: 120, unsent: 35, observed: true }],
      events: [],
    },
    {
      id: "c7",
      externalId: "1000007",
      name: "ООО «Каскад»",
      inn: "5906789012",
      kpp: "590601001",
      stage: "Ожидание",
      owner: "operator-b",
      active: true,
      cycle: "current",
      tags: ["Новый"],
      contact: { name: "Дмитрий Орлов", phone: "+7 342 118-40-26", email: "d.orlov@kaskad.example" },
      promise: "2026-11-25",
      pool: false,
      history: [{ period: "2026Q3", date: "2026-10-20", total: 80, unsent: 16, observed: true }],
      events: [
        { id: "e11", type: "call", date: "2026-11-12", title: "Звонок", text: "Клиент обещал оплату до 25.11.2026.", author: "Оператор Б", result: "Обещание", promise: "2026-11-25" },
        { id: "e12", type: "system", date: "2026-11-10", title: "Переназначение", text: "Клиент передан Оператору Б по решению администратора.", author: "Администратор" },
      ],
    },
    {
      id: "c8",
      externalId: "1000008",
      name: "АО «Терра»",
      inn: "4707890123",
      kpp: "470701001",
      stage: "Не в работе",
      owner: null,
      active: true,
      cycle: "current",
      tags: ["Ключевой"],
      contact: { name: "Елена Гусева", phone: "+7 495 901-33-44", email: "e.guseva@terra.example" },
      promise: null,
      pool: true,
      history: [{ period: "2026Q3", date: "2026-10-20", total: 60, unsent: 42, observed: true }],
      events: [],
    },
    {
      id: "c9",
      externalId: "1000009",
      name: "ООО «Импульс»",
      inn: "3608901234",
      kpp: "360801001",
      stage: "В работе",
      owner: "operator-a",
      active: true,
      cycle: "current",
      tags: ["Новый"],
      contact: { name: "Виктор Зайцев", phone: "+7 473 220-15-90", email: "v.zaytsev@impulse.example" },
      promise: null,
      pool: false,
      history: [
        { period: "2026Q2", date: "2026-07-20", total: 50, unsent: 20, observed: true },
        { period: "2026Q3", date: "2026-10-20", total: 50, unsent: 10, observed: true },
      ],
      events: [],
    },
    {
      id: "c10",
      externalId: "1000010",
      name: "ООО «Контур-Сервис»",
      inn: "7709012345",
      kpp: "770901001",
      stage: "Не в работе",
      owner: null,
      active: true,
      cycle: "current",
      tags: ["Новый"],
      contact: { name: "Алина Фёдорова", phone: "+7 495 777-01-02", email: "a.fedorova@kontur-service.example" },
      promise: null,
      pool: true,
      history: [{ period: "2026Q3", date: "2026-10-20", total: 300, unsent: 90, observed: true }],
      events: [],
    },
    {
      id: "c11",
      externalId: "1000011",
      name: "ООО «Развитие»",
      inn: "7701122334",
      kpp: "770101002",
      stage: "В работе",
      owner: "operator-a",
      active: true,
      cycle: "current",
      tags: ["Ключевой"],
      contact: { name: "Наталья Ковалёва", phone: "+7 495 222-90-11", email: "n.kovaleva@razvitie.example" },
      promise: null,
      pool: false,
      claims: [],
      sanctions: [],
      history: [
        { period: "2026Q2", date: "2026-07-20", total: 50, unsent: 10, observed: true },
        { period: "2026Q3", date: "2026-10-20", total: 50, unsent: 30, observed: true },
      ],
      events: [
        { id: "e13", type: "slice", date: "2026-10-20", title: "Рост долга", text: "Не передано выросло с 10 до 30 документов.", author: "Система" },
      ],
    },
  ],
  importLog: [],
  lastImport: null,
});
