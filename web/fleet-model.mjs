function compareVersions(left,right){
  const a=left.split('.').map(Number),b=right.split('.').map(Number);
  for(let index=0;index<3;index++)if(a[index]!==b[index])return a[index]-b[index];
  return 0;
}

export function sortDevices(devices,key='checkin',direction='desc'){
  const value=device=>key==='version'?device.report?.version||null:device.lastCheckIn||null;
  const compare=key==='version'?compareVersions:(a,b)=>a-b;
  return [...devices].sort((a,b)=>{
    const left=value(a),right=value(b);
    if(left===null)return right===null?0:1;
    if(right===null)return -1;
    const order=compare(left,right)*(direction==='asc'?1:-1);
    return order||((b.lastCheckIn||0)-(a.lastCheckIn||0))||a.id.localeCompare(b.id);
  });
}

export function sortReleases(releases){
  return [...releases].sort((a,b)=>compareVersions(b.version,a.version));
}

const percent=(count,total)=>total>0?Math.round(count*1000/total)/10:null;
const metric=(count,total,threshold)=>({count,total,percent:percent(count,total),
  issue:total>=20&&count*100>=threshold*total});

export function sessionHealth(session){
  const attempts=session.producerAttempts;
  const failurePercent=percent(session.producerFailures,attempts);
  return {producer:{failurePercent,
    failureIssue:attempts>=20&&session.producerFailures*100>=2*attempts,
    unresolvedPercent:percent(session.producerUnknown,attempts)},
    consumers:session.consumers.filter(consumer=>consumer.receivedAt!==null).map(consumer=>{
      const observed=session.producerDevice?
        Math.max(0,session.producerDelivered-consumer.unobserved):0;
      const rxTotal=(consumer.rxAccepted||0)+consumer.nativeDrops+consumer.rejected;
      return {id:consumer.id,
        missing:metric(consumer.missing.length,observed,5),
        nativeDrops:metric(consumer.nativeDrops,rxTotal,2),
        rejected:metric(consumer.rejected,rxTotal,2),
        weakSignal:consumer.rssi?.mean<=-85};
    })};
}
