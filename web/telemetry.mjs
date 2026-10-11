// Historical packet comparison. A gap is known only between two observations
// from the same producer session; outside that interval it is unobserved.
function bits(hex,base){
  const out=[];
  for(let byte=0;byte<hex.length/2;byte++){
    const value=parseInt(hex.slice(byte*2,byte*2+2),16);
    for(let bit=0;bit<8;bit++)if(value&(1<<bit))out.push(base+byte*8+bit);
  }
  return out;
}
function packetSet(windows,key){
  const set=new Set();for(const w of windows)for(const seq of bits(w[key],w.base))set.add(seq);return set;
}
export function compareTelemetry(batches,devices){
  const sessions=new Map();
  for(const batch of batches){
    for(const w of batch.record.windows){
      let session=sessions.get(w.session);
      if(!session){session={id:w.session,producer:[],consumers:new Map(),producerDevice:null,receivedAt:0};sessions.set(w.session,session);}
      session.receivedAt=Math.max(session.receivedAt,batch.receivedAt);
      if(batch.record.role==='producer'){
        session.producer.push(w);session.producerDevice=batch.device_id;session.producerRecord=batch.record;
      }else{
        let entries=session.consumers.get(batch.device_id);
        if(!entries){entries=[];session.consumers.set(batch.device_id,entries);}
        let entry=entries.find(item=>item.batch===batch);
        if(!entry){entry={batch,windows:[],record:batch.record,receivedAt:batch.receivedAt};entries.push(entry);}
        entry.windows.push(w);
      }
    }
  }
  const result=[];
  for(const session of sessions.values()){
    const attempted=packetSet(session.producer,'attempted'),delivered=packetSet(session.producer,'delivered');
    const failed=packetSet(session.producer,'failed'),controls=packetSet(session.producer,'controls');
    const features=[...delivered].filter(seq=>!controls.has(seq)).sort((a,b)=>a-b);
    const maxProducer=Math.max(0,...session.producer.map(w=>w.base));
    const consumers=devices.filter(d=>d.role==='consumer').map(device=>{
      const entries=session.consumers.get(device.id)||[];
      const received=new Set(),intervals=[];
      let ambiguous=false;
      for(const entry of entries){
        for(const seq of packetSet(entry.windows,'received'))received.add(seq);
        const seen=new Set([...packetSet(entry.windows,'received'),...packetSet(entry.windows,'controls')]);
        const ordered=[...seen].sort((a,b)=>a-b);
        const uncertain=!!entry.record.epoch_uncertain&&maxProducer>=65536;
        ambiguous ||= uncertain;
        if(ordered.length&&!uncertain)intervals.push([ordered[0],ordered[ordered.length-1]]);
      }
      let unobserved=0;const missing=[];
      for(const seq of features){
        if(!intervals.some(([first,last])=>first<=seq&&seq<=last))unobserved++;
        else if(!received.has(seq))missing.push(seq);
      }
      return {id:device.id,name:device.name||device.id,received:received.size,missing,
        unobserved,ambiguous,receivedAt:entries.length?Math.max(...entries.map(e=>e.receivedAt)):null,
        nativeDrops:entries.reduce((n,e)=>n+e.record.counts.native_drops,0),
        rejected:entries.reduce((n,e)=>n+e.record.counts.rejected,0),
        linkLosses:entries.reduce((n,e)=>n+e.record.counts.link_losses,0),
        bootIds:[...new Set(entries.map(e=>e.record.boot_id).filter(Boolean))],
        rssi:entries.filter(e=>e.record.rssi).sort((a,b)=>b.receivedAt-a.receivedAt)[0]?.record.rssi||null,
        truncatedWindows:entries.reduce((n,e)=>n+e.record.truncated_windows,0)};
    });
    result.push({id:session.id,producerDevice:session.producerDevice,receivedAt:session.receivedAt,
      producerAttempts:[...attempted].filter(seq=>!controls.has(seq)).length,
      producerDelivered:features.length,producerFailures:[...failed].filter(seq=>!controls.has(seq)).length,
      producerUnknown:[...attempted].filter(seq=>!controls.has(seq)&&!delivered.has(seq)&&!failed.has(seq)).length,
      producerBootId:session.producerRecord?.boot_id||null,
      producerOverruns:session.producerRecord?.counts.audio_overruns||0,
      producerDiscontinuities:session.producerRecord?.counts.audio_discontinuities||0,
      consumers});
  }
  return result.sort((a,b)=>b.receivedAt-a.receivedAt);
}

export function unmatchedTelemetry(batches,devices){
  return batches.filter(b=>!b.record.windows.length).map(b=>({
    id:b.device_id,name:devices.find(d=>d.id===b.device_id)?.name||b.device_id,
    role:b.record.role,receivedAt:b.receivedAt,counts:b.record.counts
  }));
}
