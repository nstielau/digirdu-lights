"""Configure the dedicated Digirdu project using local gcloud credentials."""
import argparse
import json
from pathlib import Path
import subprocess
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
PROJECT='digirdu-lights'

class Cloud:
    def __init__(self):
        self.token=subprocess.check_output(['gcloud','auth','print-access-token'],text=True).strip()
    def call(self,url,method='GET',data=None):
        request=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,
            method=method,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','x-goog-user-project':PROJECT})
        with urllib.request.urlopen(request,timeout=45) as response:
            value=response.read()
            return json.loads(value) if value else {}
    def web_config(self):
        project=self.call('https://firebase.googleapis.com/v1beta1/projects/'+PROJECT)
        number=project['projectNumber']
        apps=self.call('https://firebase.googleapis.com/v1beta1/projects/'+PROJECT+'/webApps')['apps']
        app=next(a for a in apps if a['displayName']=='Digirdu dashboard')
        config=self.call('https://firebase.googleapis.com/v1beta1/'+app['name']+'/config')
        base='https://recaptchaenterprise.googleapis.com/v1/projects/'+PROJECT+'/keys'
        keys=self.call(base).get('keys',[])
        key=next((k for k in keys if k.get('displayName')=='Digirdu App Check'),None)
        if key is None:
            key=self.call(base,'POST',{'displayName':'Digirdu App Check','webSettings':{'allowedDomains':[
                PROJECT+'.web.app',PROJECT+'.firebaseapp.com'],'allowAllDomains':False,'integrationType':'SCORE'}})
        site=key['name'].rsplit('/',1)[1]
        name=f'projects/{number}/apps/{app["appId"]}/recaptchaEnterpriseConfig'
        self.call('https://firebaseappcheck.googleapis.com/v1/'+name+'?updateMask=siteKey,tokenTtl','PATCH',
                  {'name':name,'siteKey':site,'tokenTtl':'3600s'})
        (ROOT/'web/firebase-config.js').write_text('export const firebaseConfig = '+json.dumps(config)+';\nexport const appCheckSiteKey = '+json.dumps(site)+';\n')
        print('Public web config and App Check key saved.')
    def auth_status(self):
        base='https://identitytoolkit.googleapis.com/admin/v2/projects/'+PROJECT
        for label,url in [('Auth config',base+'/config'),('Google sign-in',base+'/defaultSupportedIdpConfigs/google.com')]:
            try:
                d=self.call(url)
                print(label,json.dumps({k:d[k] for k in ('name','enabled','authorizedDomains') if k in d}))
            except urllib.error.HTTPError as e:
                print(label,'HTTP',e.code)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('web-config','auth-status'));args=parser.parse_args()
    try:getattr(Cloud(),args.action.replace('-','_'))()
    except urllib.error.HTTPError as e:
        raise SystemExit('Cloud configuration failed: HTTP %d'%e.code) from None
