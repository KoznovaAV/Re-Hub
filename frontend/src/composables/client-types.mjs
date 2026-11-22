export const clientTypeOptions = [
  {value:'vip',label:'ВИП'},
  {value:'integrator',label:'Интегратор'},
  {value:'tech_partner',label:'Техпартнёр'},
  {value:'mpp',label:'Работа через МПП'},
  {value:'newcomer',label:'Новичок'},
];
const aliases={vip:'vip',VIP:'vip','ВИП':'vip','Ключевой':'vip',integrator:'integrator','Интегратор':'integrator',tech_partner:'tech_partner','Техпартнёр':'tech_partner',mpp:'mpp','МПП':'mpp',newcomer:'newcomer','Новичок':'newcomer'};
export function clientTypeCodes(client){return [...new Set((client.tags??[]).map(t=>aliases[t]).filter(Boolean))];}
export function clientTypeText(client){
  const codes=clientTypeCodes(client);
  return clientTypeOptions.filter(t=>codes.includes(t.value)).map(t=>t.label).join(', ')||'Не указан';
}
