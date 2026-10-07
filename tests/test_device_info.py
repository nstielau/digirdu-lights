"""Device page identity, small-display bounds and truthful OTA status."""
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import sys
import dashboard as d


class DevicePageTests(unittest.TestCase):
    def info(self, status=None):
        return {'app':'1.1.2','base':'1.1.3','id':'468e33377e80',
                'role':'CONSUMER','source':'64:e8:33:73:d8:3c',
                'update':status or {'state':'not_checked','blocked':None}}

    def page(self, info):
        self.assertIn('device',__import__('inspect').signature(d.snapshot).parameters)
        return d.page_content(d.snapshot('consumer',0,device=info),3)

    def test_four_pages_keep_brightness_index_and_wrap(self):
        ui=d.Dashboard(Mock());pages=[]
        for _ in range(4):ui.toggle();pages.append(ui.page)
        self.assertEqual(pages,[1,2,3,0])
        p=self.page(self.info())
        self.assertEqual(p['page'],'4/4');self.assertEqual(p['b1'],'NEXT');self.assertEqual(p['b2'],'AUX')
        self.assertIn('Role CONSUMER',p.values());self.assertIn('Src 64:e8:33:73:d8:3c',p.values())

    def test_producer_page_shows_its_own_radio_mac(self):
        info=self.info();info.update(role='PRODUCER',source='64:e8:33:73:d8:3c')
        p=self.page(info)
        self.assertIn('Role PRODUCER',p.values())
        self.assertIn('MAC 64:e8:33:73:d8:3c',p.values())
        self.assertNotIn('Src 64:e8:33:73:d8:3c',p.values())

    def test_cleared_consumer_source_is_explicit(self):
        info=self.info();info['source']='NONE'
        self.assertIn('Src NONE',self.page(info).values())

    def test_actual_versions_and_complete_id_cached_but_status_refreshes(self):
        self.assertTrue(hasattr(d,'device_information'))
        import ota_status
        with patch.object(d,'_device_identity',None),patch.dict(sys.modules,{
            'app_version':SimpleNamespace(APP_VERSION='1.7.2'),
            'ota_manifest':SimpleNamespace(BASE_VERSION='1.6.3'),
            'microcontroller':SimpleNamespace(cpu=SimpleNamespace(uid=bytes.fromhex('abcdef123456')))}):
            ota_status.reset('maintenance');info=d.device_information()
            self.assertEqual((info['app'],info['base'],info['id']),('1.7.2','1.6.3','abcdef123456'))
            self.assertEqual(info['update']['state'],'maintenance')
            ota_status.reset('checked');self.assertEqual(d.device_information()['update']['state'],'checked')
            with patch.dict(sys.modules,{'ota_status':None}):
                self.assertEqual(d.device_information()['update']['state'],'unsupported')

    def test_full_versions_id_and_block_fit_even_at_contract_limits(self):
        info=self.info({'state':'checked','blocked':{'version':'999999.999999.999999','minimum_base':'999999.999999.999999'}})
        info.update(app='888888.888888.888888',base='777777.777777.777777',id='a'*32)
        content=self.page(info)
        rows=[content.get('info%d'%i,'') for i in range(8)]
        text='\n'.join(rows)
        self.assertIn(info['app'],text);self.assertIn(info['base'],text)
        self.assertIn('ID '+'a'*32,''.join(rows))
        self.assertIn('USB BASE NEEDED',text)
        self.assertIn('App 999999.999999.999999',text)
        self.assertIn('Needs base 999999.999999.999999',text)
        for name,x,y,count,scale,_ in d.TFT_FIELDS:
            self.assertLessEqual(len(content.get(name,'')),count,name)
            self.assertLessEqual(x+count*6*scale,240)
            self.assertLessEqual(y+14*scale,135)

    def test_unknown_disabled_and_checked_are_distinct(self):
        expected={'not_checked':'Not checked this boot','disabled':'OTA not enabled/enrolled',
                  'maintenance':'Not checked: USB mode','unavailable':'Check unavailable',
                  'unsupported':'Status needs base 1.1.3','paused':'Updates paused',
                  'no_release':'No release configured','checked':'No base block found'}
        for status,label in expected.items():
            content=self.page(self.info({'state':status,'blocked':None}))
            self.assertIn(label,content.values(),status)
            self.assertNotIn('Up to date',content.values())

    def test_unavailable_reason_is_shown_without_exposing_exception_details(self):
        content=self.page(self.info({'state':'unavailable','blocked':None,
                                     'reason':'HTTP 400'}))
        self.assertIn('Check unavailable: HTTP 400',content.values())
        self.assertNotIn('token', ''.join(content.values()).lower())

    def test_sleep_and_banner_preempt_info_header(self):
        self.assertIn('device',__import__('inspect').signature(d.snapshot).parameters)
        s=d.snapshot('producer',0,device=self.info(),banner='Broadcasting...')
        c=d.page_content(s,3);self.assertNotIn('header',c);self.assertEqual(c['banner'],'Broadcasting...')
        s['overlay']=('SLEEPING','2','Group shutdown')
        self.assertEqual(d.page_content(s,3),{'sleep_title':'SLEEPING','sleep_number':'2','sleep_detail':'Group shutdown'})
