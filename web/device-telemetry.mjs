/** Summarize the batches returned by the fleet telemetry query for one device. */
export function summarizeDeviceTelemetry(device,batches,sessions){
  const own=batches.filter(batch=>batch.device_id===device.id&&batch.record.role===device.role);
  if(!own.length)return null;
  const total=key=>own.reduce((sum,batch)=>sum+(batch.record.counts[key]||0),0);
  const latest=[...own].sort((a,b)=>b.receivedAt-a.receivedAt);
  const readings=own.map(batch=>batch.record.rssi).filter(Boolean);
  const summary={uploads:own.length,lastUpload:latest[0].receivedAt,
    features:total('features'),controls:total('controls'),rejected:total('rejected'),
    nativeDrops:total('native_drops'),linkLosses:total('link_losses'),
    skipped:total('skipped'),audioDiscontinuities:total('audio_discontinuities'),
    truncatedWindows:own.reduce((sum,batch)=>sum+(batch.record.truncated_windows||0),0),
    rssi:latest[0].record.rssi||null,
    rssiHistory:readings.length?{uploads:readings.length,
      mean:-Math.round(-readings.reduce((sum,reading)=>sum+reading.mean,0)/readings.length),
      min:Math.min(...readings.map(reading=>reading.min)),
      max:Math.max(...readings.map(reading=>reading.max))}:null};
  if(device.role==='consumer'){
    let observed=0,missing=0,producerEvidence=false;
    for(const session of sessions){
      if(!session.producerDevice)continue;
      const peer=session.consumers.find(consumer=>consumer.id===device.id);
      if(!peer)continue;
      producerEvidence=true;
      observed+=Math.max(0,session.producerDelivered-peer.unobserved);
      missing+=peer.missing.length;
    }
    summary.matched=observed?{observed,missing}:null;
    summary.producerEvidence=producerEvidence;
  }else{
    const produced=sessions.filter(session=>session.producerDevice===device.id);
    summary.send={completed:produced.reduce((sum,session)=>sum+session.producerDelivered,0),
      failed:produced.reduce((sum,session)=>sum+session.producerFailures,0),
      unresolved:produced.reduce((sum,session)=>sum+session.producerUnknown,0)};
  }
  return summary;
}
