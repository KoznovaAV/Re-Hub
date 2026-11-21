export function callSummary(client, period = null) {
  const calls = (client.events ?? []).filter(e => e.type === 'call' && (!period || e.period === period));
  const last = [...calls].sort((a,b) => String(b.date).localeCompare(String(a.date)))[0];
  return { count: calls.length, missed: calls.filter(e => e.result === 'Недозвон').length,
    status: last?.result ?? 'Не звонили', lastDate: last?.date ?? null, callbackOn: last?.callbackOn ?? null };
}
export function eligibleForCall(client, period) {
  const observation = client.history.find(item => item.period === period && item.observed !== false);
  return Boolean(client.active !== false && !client.excluded && !client.inactive &&
    client.stage !== 'Закрыт' && observation && observation.unsent > 0);
}
export function visibleSelection(selected, rows) {
  const visible = new Set(rows.map(row => row.client.id));
  return selected.filter(id => visible.has(id));
}
export function csvCell(value) {
  let text = String(value ?? '');
  if (/^[=+@\-\t\r]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
