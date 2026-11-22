export function callSummary(client, period = null) {
  const unknownPeriod = Boolean(period && (client.events ?? []).some(e => e.type === 'call' && !e.period));
  const calls = (client.events ?? []).filter(e => e.type === 'call' && (!period || e.period === period));
  const last = [...calls].sort((a,b) => String(b.date).localeCompare(String(a.date)))[0];
  return { unknownPeriod, count: calls.length, missed: calls.filter(e => e.result === 'Недозвон').length,
    status: (last?.result === 'Не тот контакт' ? 'Не тот администратор' : last?.result) ?? (unknownPeriod ? 'Период прежних звонков не указан' : 'Не звонили'), lastDate: last?.date ?? null, callbackOn: last?.callbackOn ?? null };
}
export function eligibleForCall(client, period, latestDate=null) {
  const observations=[...client.history].filter(item=>item.period===period).sort((a,b)=>String(a.date).localeCompare(String(b.date)));
  const observation=observations.at(-1);
  const total=observation?.total??observations.filter(h=>h.observed!==false&&h.total!=null).at(-1)?.total;
  if(latestDate&&observation?.date<latestDate)return false;
  return Boolean(client.active !== false && !client.excluded && !client.inactive &&
    client.stage !== 'Закрыт' && observation && observation.observed !== false && observation.unsent > 0 && ((total>0&&observation.unsent/total>=0.05)||(client.tags??[]).some(t=>['Новичок','newcomer'].includes(t))||(client.joinedOn&&client.joinedOn<=new Date().toISOString().slice(0,10)&&new Date(client.joinedOn)>=new Date(new Date().setMonth(new Date().getMonth()-6)))));
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
