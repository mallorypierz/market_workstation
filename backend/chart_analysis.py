"""Bound chart PNGs and three named answers; no paper execution."""
import base64
import binascii
import hashlib
import json
import struct
import zlib

QUESTIONS = [
    {'name':'action','type':'choice','instructions':'Which action fits this paper position and the strategy rules? Use frozen account facts and configured order_size. A bullish SMA crossover supports buy if affordable; a bearish crossover supports reducing/exiting. Hold requires shares; wait requires no shares. Propose only, never execute.',
     'choices':[{'value':v,'description':d} for v,d in [('buy','Add order_size shares.'),('sell','Reduce holdings by order_size shares.'),('hold','Keep an open position.'),('wait','Stay flat.'),('close','Exit the entire position.')]]},
    {'name':'crossover','type':'choice','instructions':'At the selected candle cutoff, is an upward crossover, downward crossover, or no crossover visible in the PNG? Judge the image, not the supplied Python signal. If the lines/cutoff cannot be read, answer unreadable. Equal averages retain the last known side; only a change of side confirms a crossover.',
     'choices':[{'value':v} for v in ['up','down','none','unreadable']]},
    {'name':'evidence','type':'choice','instructions':'Is the visible chart sufficient to assess the signal at the cutoff? Require identifiable cutoff, both SMA lines and enough preceding context to establish a change of side. The first comparable pair alone is not a crossover.',
     'choices':[{'value':v} for v in ['sufficient','insufficient','unreadable']]},
]


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS decision_images (
        decision_id TEXT PRIMARY KEY REFERENCES decisions(id), snapshot_id TEXT NOT NULL REFERENCES decision_snapshots(id),
        png BLOB NOT NULL, sha256 TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
        questions_json TEXT NOT NULL)''')
    db.commit()


def decode_png(data_url):
    """Decode bounded canvas RGB/RGBA PNGs, including all five PNG row filters."""
    if not isinstance(data_url,str) or not data_url.startswith('data:image/png;base64,') or len(data_url)>8_000_000:
        raise ValueError('Recapture the chart as a PNG under 6 MB.')
    try: raw=base64.b64decode(data_url.split(',',1)[1],validate=True)
    except (ValueError,binascii.Error):raise ValueError('Unreadable PNG encoding; recapture the chart.') from None
    if raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Image is not a PNG; recapture the chart.')
    pos=8;chunks=[];compressed=bytearray();metadata=None;ended=False
    while pos+12<=len(raw):
        size=struct.unpack('>I',raw[pos:pos+4])[0]
        if size>6_000_000 or pos+12+size>len(raw):raise ValueError('Truncated PNG; recapture.')
        kind=raw[pos+4:pos+8];data=raw[pos+8:pos+8+size]
        if zlib.crc32(kind+data)&0xffffffff != struct.unpack('>I',raw[pos+8+size:pos+12+size])[0]:raise ValueError('Damaged PNG checksum; recapture.')
        chunks.append(kind)
        if kind==b'IHDR':
            if len(chunks)!=1 or size!=13:raise ValueError('Invalid PNG header; recapture.')
            width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
            if not (320<=width<=2400 and 200<=height<=1600 and depth==8 and color in (2,6) and compression==filtering==interlace==0):
                raise ValueError('Recapture a readable noninterlaced RGB/RGBA chart (320–2400 × 200–1600).')
            channels=4 if color==6 else 3
        elif kind==b'IDAT':compressed.extend(data)
        elif kind==b'tEXt' and data.startswith(b'market_snapshot\x00'):
            if metadata is not None or size>4096:raise ValueError('Ambiguous or oversized snapshot metadata; recapture.')
            try:metadata=json.loads(data.split(b'\x00',1)[1])
            except (ValueError,UnicodeError,RecursionError):raise ValueError('Invalid snapshot metadata; recapture.') from None
        elif kind==b'IEND':
            if size!=0:raise ValueError('Invalid PNG end; recapture.')
            ended=True;pos+=12;break
        elif kind[:1].isupper() and kind not in (b'PLTE',):raise ValueError('Unsupported PNG; recapture with chart export.')
        pos+=12+size
    if not chunks or chunks[0]!=b'IHDR' or not ended or pos!=len(raw) or not compressed:
        raise ValueError('Incomplete PNG; recapture.')
    stride=width*channels;expected=(stride+1)*height
    try:
        inflater=zlib.decompressobj();pixels=inflater.decompress(bytes(compressed),expected+1)
        if len(pixels)!=expected or not inflater.eof or inflater.unused_data:raise ValueError('Invalid decoded PNG size')
    except (ValueError,zlib.error):raise ValueError('PNG cannot be decoded; recapture.') from None
    previous=bytearray(stride);colors=set()
    for y in range(height):
        offset=y*(stride+1);kind=pixels[offset];row=bytearray(pixels[offset+1:offset+1+stride])
        if kind>4:raise ValueError('Invalid PNG filter; recapture.')
        for i in range(stride):
            a=row[i-channels] if i>=channels else 0;b=previous[i];c=previous[i-channels] if i>=channels else 0
            if kind==1: predictor=a
            elif kind==2: predictor=b
            elif kind==3: predictor=(a+b)//2
            elif kind==4:
                p=a+b-c;pa,pb,pc=abs(p-a),abs(p-b),abs(p-c);predictor=a if pa<=pb and pa<=pc else b if pb<=pc else c
            else:predictor=0
            row[i]=(row[i]+predictor)&255
        if len(colors)<3:
            for i in range(0,stride,channels):
                if channels==3 or row[i+3]>0:colors.add(bytes(row[i:i+3]))
                if len(colors)>=3:break
        previous=row
    if len(colors)<3:raise ValueError('Blank or unreadable chart; recapture after rendering.')
    return raw,width,height,metadata


def payload(snapshot,png):
    from backend.decisions import MODEL
    return {'model':MODEL,'input':[{'role':'user','content':[
        {'type':'input_json','data':snapshot},
        {'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(png).decode()}]}],
        'questions':QUESTIONS}


def analyze(db,request,provider=None):
    from backend import decisions as d, paper
    import uuid
    initialize(db)
    snapshot=d.get_snapshot(db,request.get('snapshot_id')) if isinstance(request.get('snapshot_id'),str) else None
    identity=str(uuid.uuid4())
    result={'decision_id':identity,'snapshot_id':snapshot['snapshot_id'] if snapshot else None,'provider':d.provider_name(provider),
        'model':d.MODEL,'model_call':'not_called','market_data':snapshot.get('market_data') if snapshot else None,
        'status':'pending','questions':QUESTIONS,'answers':{},'proposal':None,'validation':None,'order_eligible':False,'order_created':False,'review_required':True,
        'explanation_source':'backend recorded facts','explanation':None}
    db.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?)',(identity,result['snapshot_id'],paper.now(),None,result['provider'],d.MODEL,'pending',d.encode(result)));db.commit()
    try:
        if snapshot is None or not snapshot['complete']:
            result['status']='missing_input';raise ValueError('Recapture a complete snapshot with warmed-up SMAs and an account at the cutoff.')
        raw,width,height,metadata=decode_png(request.get('image'))
        expected={'snapshot_id':snapshot['snapshot_id'],'sha256':snapshot['sha256'],'chart_range':snapshot.get('capture_range')}
        if metadata!=expected or request.get('snapshot_sha256')!=snapshot['sha256'] or request.get('chart_range')!=snapshot.get('capture_range'):
            result['status']='snapshot_mismatch';raise ValueError('PNG and snapshot do not match. Click Ask about chart to recapture both together.')
        digest=hashlib.sha256(raw).hexdigest()
        db.execute('INSERT INTO decision_images VALUES(?,?,?,?,?,?,?)',(identity,snapshot['snapshot_id'],raw,digest,width,height,d.encode(QUESTIONS)));db.commit()
        result['image']={'url':f'/api/decisions/{identity}/image','sha256':digest,'width':width,'height':height}
        result['cutoff']=snapshot['decision_time'];result['chart_range']=snapshot['capture_range']
        result['python_crossover']=snapshot['indicators']['at_candle']['signal'] or 'none'
        if provider is None and not d.os.environ.get('OPENAI_API_KEY'):raise d.ProviderFailure('configuration_error')
        result['model_call']='live_provider_attempt' if d.provider_name(provider)=='openai' else 'controlled_test'
        response=(provider or d.openai_request)(payload(snapshot,raw))
        result['model_call']='live_provider' if d.provider_name(provider)=='openai' else 'controlled_test'
        answers=response.get('answers') if isinstance(response,dict) else None
        if not isinstance(answers,list):raise d.ProviderFailure('malformed_answer')
        names=[a.get('name') for a in answers if isinstance(a,dict)]
        if len(names)!=len(answers) or any(not isinstance(n,str) for n in names) or len(set(names))!=len(names) or set(names)-{'action','crossover','evidence'}:
            raise d.ProviderFailure('malformed_answer')
        missing=set(('action','crossover','evidence'))-set(names)
        for question in QUESTIONS:
            name=question['name'];answer=next((a for a in answers if a.get('name')==name),None)
            if answer is None:continue
            if answer.get('type')=='refusal':result['answers'][name]='refused';continue
            if answer.get('type')!='choice' or answer.get('choice') not in [c['value'] for c in question['choices']]:
                raise d.ProviderFailure('malformed_answer')
            result['answers'][name]=answer['choice']
        if missing:raise d.ProviderFailure('missing_answers')
        if 'refused' in result['answers'].values():raise d.ProviderFailure('refused')
        action,quantity,reason=d.validate_answer({'answers':[{'name':d.QUESTION,'type':'choice','choice':result['answers']['action']}]},snapshot)
        result['proposal']={'action':action,'quantity':quantity}
        conflict=result['answers']['crossover'] not in ('unreadable',result['python_crossover'])
        readable=result['answers']['crossover']!='unreadable' and result['answers']['evidence']!='unreadable'
        sufficient=result['answers']['evidence']=='sufficient'
        result['status']='unreadable_image' if not readable else 'conflicting_signal' if conflict else 'insufficient_evidence' if not sufficient else 'invalid_proposal' if reason else 'valid'
        result['validation']={'valid':result['status']=='valid','action_reason':reason,'visual_matches_python':not conflict and readable,
                              'evidence_sufficient':sufficient,'recapture_required':not readable or not sufficient or conflict}
        result['order_eligible']=False  # Only the completed reviewer/Python gate may make this eligible.
        result['explanation']=f"Python recorded crossover {result['python_crossover']} at {snapshot['decision_time']}; model image answer {result['answers']['crossover']}. Frozen cash ${snapshot['account']['cash']:.2f}, shares {snapshot['account']['shares']}. No order submitted."
    except ValueError as error:
        if result['status']=='pending':result['status']='unreadable_image'
        result['validation']={'valid':False,'recapture_required':True,'reason':str(error)}
    except d.ProviderFailure as error:
        result['status']=error.status;result['validation']={'valid':False,'reason':error.status,'recapture_required':error.status in ('missing_answers','malformed_answer')}
    except TimeoutError:
        result['status']='timeout';result['validation']={'valid':False,'reason':'timeout'}
    db.execute('UPDATE decisions SET completed_at=?,status=?,result_json=? WHERE id=?',(paper.now(),result['status'],d.encode(result),identity));db.commit()
    return result
