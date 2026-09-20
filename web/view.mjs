export function describeDevice(d,stable){
  const r=d.report;
  const desired=d.pin||stable?.version||'No release';
  return {title:d.name||d.id,state:!d.enabled?'Revoked':d.paused?'Updates paused':r?.state||'Awaiting report',
    fields:{'Board':d.board,'Role':d.role,'Reported app':r?.version||'Not reported','USB base':r?.base_version||'Not reported',
      'Desired app':desired+(d.pin?' (pinned)':' (latest)'),
      'Last report':d.lastCheckIn?new Date(d.lastCheckIn).toLocaleString():'Never',
      'Battery terminal (last report)':batteryLabel(r?.battery),
      'Update result':r?.error||r?.state||'Awaiting report',
      'Radio protocol':r?`send ${r.protocol_send}; receive ${r.protocol_receive.join(', ')}`:'Not reported'}};
}

export function batteryLabel(reading){
  if(!reading)return 'Not reported';
  if(reading.status==='measured' && Number.isFinite(reading.voltage))return `${reading.voltage.toFixed(2)} V`;
  return {unsupported:'Unavailable on this board',out_of_range:'Outside battery voltage range',read_error:'Reading unavailable'}[reading.status]||'Not reported';
}
