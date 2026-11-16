import base64
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from backend import decisions,chart_analysis
from backend.decision_fixture import build
from backend.recorder import connect
from backend.decision_check import ledger


def png(snapshot):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    meta={'snapshot_id':snapshot['snapshot_id'],'sha256':snapshot['sha256'],'chart_range':snapshot['capture_range']}
    # Constructed decoder fixture only, not a market chart / browser evidence.
    rows=b''.join(b'\0'+b''.join(bytes((x%256,y%256,(x+y)%256,255)) for x in range(320)) for y in range(200))
    raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',320,200,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'tEXt',b'market_snapshot\0'+json.dumps(meta).encode())+chunk(b'IEND',b'')
    return 'data:image/png;base64,'+base64.b64encode(raw).decode()


def answers(cross='up',evidence='sufficient'):
    return {'answers':[{'name':n,'type':'choice','choice':v} for n,v in [('evidence',evidence),('action','buy'),('crossover',cross)]]}

class ChartAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=connect(Path(self.folder.name)/'test.sqlite3');self.snapshot=build(self.db)
        self.request={'analysis':'chart','snapshot_id':self.snapshot['snapshot_id'],'snapshot_sha256':self.snapshot['sha256'],
                      'chart_range':self.snapshot['capture_range'],'image':png(self.snapshot)}
    def tearDown(self):self.db.close();self.folder.cleanup()
    def test_typed_image_input_saved_bytes_named_answers_and_no_orders(self):
        before=ledger(self.db);calls=[]
        def provider(payload):calls.append(payload);return answers()
        r=decisions.decide(self.db,self.request,provider)
        self.assertEqual(r['status'],'valid');self.assertEqual(r['answers'],{'action':'buy','crossover':'up','evidence':'sufficient'})
        self.assertFalse(r['order_eligible']);self.assertEqual(ledger(self.db),before)
        content=calls[0]['input'][0]['content'];self.assertEqual(content[0]['type'],'input_json');self.assertEqual(content[0]['data'],self.snapshot)
        self.assertEqual(content[1]['type'],'input_image')
        raw=chart_analysis.decode_png(content[1]['image_url'])[0]
        saved=self.db.execute('SELECT * FROM decision_images').fetchone();self.assertEqual(bytes(saved['png']),raw)
        self.assertEqual(saved['sha256'],hashlib.sha256(raw).hexdigest())
    def test_conflicting_unreadable_missing_duplicate_and_insufficient(self):
        for response,status in [(answers('down'),'conflicting_signal'),(answers('unreadable'),'unreadable_image'),(answers(evidence='insufficient'),'insufficient_evidence'),({'answers':answers()['answers'][:2]},'missing_answers'),({'answers':answers()['answers']*2},'malformed_answer'),({'answers':[{'name':[]}]},'malformed_answer')]:
            r=decisions.decide(self.db,self.request,lambda _:response)
            self.assertEqual(r['status'],status);self.assertFalse(r['order_eligible'])
    def test_wrong_snapshot_corrupt_and_missing_image_never_sent(self):
        def forbidden(_):self.fail('Provider must not run')
        bad={**self.request,'snapshot_sha256':'wrong'}
        self.assertEqual(decisions.decide(self.db,bad,forbidden)['status'],'snapshot_mismatch')
        for data in ['data:image/png;base64,YmFk',self.request['image'][:-20],None]:
            r=decisions.decide(self.db,{**self.request,'image':data},forbidden)
            self.assertEqual(r['status'],'unreadable_image')
    def test_range_saved_and_future_chart_removed(self):
        s=decisions.create_snapshot(self.db,{'candle_timestamp':'2026-11-09T14:34:00Z','chart_range':{'from':'2026-11-09T14:32:00Z','to':'2026-11-09T14:34:00Z'}})
        self.assertEqual(len(s['chart']['candles']),3);self.assertEqual(s['indicators']['at_candle']['signal'],'up')
        self.assertEqual(s['chart']['sma']['values'][-1]['short'],16)

    def test_png_http_retrieval(self):
        import asyncio,os
        from unittest.mock import patch
        from backend.main import app
        result=decisions.decide(self.db,self.request,lambda _:answers())
        path='/api/decisions/'+result['decision_id']+'/image'
        async def get():
            sent=[]
            async def receive():return {'type':'http.request','body':b'','more_body':False}
            async def send(message):sent.append(message)
            await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'GET','path':path,
                'raw_path':path.encode(),'query_string':b'','root_path':'','scheme':'http','headers':[],
                'server':('127.0.0.1',8000),'client':('127.0.0.1',1)},receive,send)
            return sent
        with patch.dict(os.environ,{'MARKET_DB_PATH':str(Path(self.folder.name)/'test.sqlite3')}):messages=asyncio.run(get())
        self.assertEqual(messages[0]['status'],200)
        self.assertIn((b'content-type',b'image/png'),messages[0]['headers'])
        self.assertEqual(b''.join(m.get('body',b'') for m in messages[1:]),chart_analysis.decode_png(self.request['image'])[0])
