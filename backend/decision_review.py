"""One bounded analyst call, one bounded reviewer call, deterministic final gate."""
import copy
import hashlib
import json
import math
import queue
import threading

from backend import decisions as d, paper

ROLE_TIMEOUT_SECONDS = 30
STRATEGY = ('Strategy version sma-cross-v1: buy requires an upward crossover and affordable configured order_size; '
            'sell or close requires a downward crossover and sufficient shares. Hold requires an open position '
            'and no downward crossover. Wait requires a flat position and is permitted without buying. '
            'Use only the frozen snapshot. No order is executed.')
VERDICTS = ('accept', 'reject_insufficient_cash', 'reject_insufficient_position',
            'reject_unsupported_signal', 'reject_unreadable_evidence', 'reject_invalid_proposal')
REVIEW_QUESTION = {'name':'review_verdict','type':'choice',
    'instructions':'You are the reviewer, not the analyst. Independently check the analyst actual proposal and named answers '
        'against the frozen snapshot, supplied observed values, and attached frozen image if present. '
        'Do not replace the proposal or invent a new action. Choose accept only if all account, signal and evidence rules pass. '
        + STRATEGY,
    'choices':[{'value':v} for v in VERDICTS]}


def bounded_call(provider,payload):
    """Deadline includes provider work; no retries. Late results cannot update records."""
    output=queue.Queue(maxsize=1)
    def worker():
        try:output.put((True,provider(payload)))
        except Exception as error:output.put((False,error))
    threading.Thread(target=worker,daemon=True).start()
    try:ok,value=output.get(timeout=ROLE_TIMEOUT_SECONDS)
    except queue.Empty:raise d.ProviderFailure('timeout') from None
    if not ok:
        if isinstance(value,d.ProviderFailure):raise value
        if isinstance(value,TimeoutError):raise d.ProviderFailure('timeout') from None
        raise d.ProviderFailure('provider_error') from None
    return value


def visible_output(response):
    """Keep categorical visible output, not hidden reasoning or raw failure bodies."""
    if not isinstance(response,dict) or not isinstance(response.get('answers'),list):return []
    result=[]
    for item in response['answers'][:10]:
        if not isinstance(item,dict):result.append({'invalid':'answer must be an object'});continue
        visible={}
        for key in ('name','type','choice'):
            if key not in item: continue
            value=item[key]
            if isinstance(value,str): visible[key]=value[:512]
            elif value is None or isinstance(value,(bool,int)): visible[key]=value
            elif isinstance(value,float) and math.isfinite(value): visible[key]=value
            else: visible[key]='[invalid value type]'
        result.append(visible)
    return result


def checks(snapshot,result):
    action=(result.get('proposal') or {}).get('action')
    account=snapshot['account']; held=account['shares'];size=snapshot['order_size']
    price=paper.price_cents(snapshot['candle']['close']); cash=account['cash_cents']
    signal=snapshot['indicators']['at_candle']['signal'] or 'none'
    cost=size*price
    account_pass=(action=='buy' and cost<=cash or action=='sell' and 0<size<=held or
                  action in ('close','hold') and held>0 or action=='wait' and held==0)
    strategy_pass=(action=='buy' and signal=='up' or action in ('sell','close') and signal=='down' or
                   action=='hold' and signal!='down' or action=='wait')
    chart_pass=(not result.get('image') or (result.get('answers',{}).get('crossover')==signal and
                                          result.get('answers',{}).get('evidence')=='sufficient'))
    return {'strategy_version':'sma-cross-v1','action':action,'cash_cents':cash,'unit_price_cents':price,
            'configured_order_size':size,'buy_cost_cents':cost,'shares':held,'python_crossover':signal,
            'account_rules_pass':bool(account_pass),'strategy_rules_pass':bool(strategy_pass),'chart_evidence_pass':bool(chart_pass)}


def reviewer_payload(snapshot,result,facts,image_url=None):
    parts=[{'type':'input_json','data':{'snapshot':snapshot,'analyst':{'proposal':result['proposal'],
        'named_answers':result.get('answers') or {'paper_action':result['proposal']['action']}},'backend_observed_values':facts}}]
    if image_url:parts.append({'type':'input_image','image_url':image_url})
    return {'model':d.MODEL,'input':[{'role':'user','content':parts}],'questions':[copy.deepcopy(REVIEW_QUESTION)]}


def verdict(response):
    answers=response.get('answers') if isinstance(response,dict) else None
    if not isinstance(answers,list) or len(answers)!=1 or not isinstance(answers[0],dict):raise d.ProviderFailure('malformed_answer')
    answer=answers[0]
    if answer.get('name')!='review_verdict':raise d.ProviderFailure('malformed_answer')
    if answer.get('type')=='refusal':raise d.ProviderFailure('refused')
    choice=answer.get('choice')
    if answer.get('type')!='choice' or not isinstance(choice,str) or choice not in VERDICTS:raise d.ProviderFailure('malformed_answer')
    return choice


def run(db,request,provider=None):
    client=provider or d.openai_request
    provider_label='openai' if provider is None else 'controlled-test'
    roles={name:{'role':name,'model':d.MODEL,'provider':provider_label,'snapshot_id':None,'snapshot_sha256':None,
                 'status':'not_called','call_count':0,'timeout_seconds':ROLE_TIMEOUT_SECONDS,'output':[], 'questions':[]}
           for name in ('analyst','reviewer')}
    image_url=None
    def call_role(name,payload):
        role=roles[name]
        if role['call_count']:raise d.ProviderFailure('call_limit')
        role.update(status='pending',questions=copy.deepcopy(payload['questions']),started_at=paper.now())
        # Configuration errors are not network calls.
        if provider is None and not d.os.environ.get('OPENAI_API_KEY'):
            role.update(status='configuration_error',completed_at=paper.now());raise d.ProviderFailure('configuration_error')
        role['call_count']=1
        if name=='reviewer':persist()
        try:
            response=bounded_call(client,copy.deepcopy(payload))
            role.update(status='received',output=visible_output(response))
            if isinstance(response,dict) and isinstance(response.get('model'),str):role['returned_model']=response['model'][:128]
            return response
        except d.ProviderFailure as error:role['status']=error.status;raise
        finally:role['completed_at']=paper.now()
    def analyst(payload):
        nonlocal image_url
        payload=copy.deepcopy(payload)
        for q in payload['questions']:q['instructions']='You are the analyst. '+STRATEGY+' '+q['instructions']
        if isinstance(payload['input'],list):
            image_url=next((p['image_url'] for p in payload['input'][0]['content'] if p['type']=='input_image'),None)
        return call_role('analyst',payload)
    analyst.provider_kind=provider_label
    result=d.decide(db,request,provider=analyst)
    identity=result['decision_id'];snapshot=d.get_snapshot(db,result['snapshot_id']) if result['snapshot_id'] else None
    for role in roles.values():
        role['snapshot_id']=result['snapshot_id'];role['snapshot_sha256']=snapshot['sha256'] if snapshot else None
        if result.get('image'):role['image_sha256']=result['image']['sha256']
    roles['analyst']['validation_status']=result['status']
    roles['analyst']['validation']=copy.deepcopy(result.get('validation'))
    if roles['analyst']['status']=='received':roles['analyst']['status']='valid_output' if result.get('proposal') else 'invalid_output'
    result['roles']=roles;result['review_required']=True;result['order_eligible']=False
    result['provider']=provider_label
    result['model_call']=('live_provider' if roles['analyst']['status'] in ('valid_output','invalid_output') else 'live_provider_attempt') if provider is None and roles['analyst']['call_count'] else 'controlled_test' if roles['analyst']['call_count'] else 'not_called'
    result['final_check']={'passed':False,'reviewer_accepted':False,'order_eligible':False,'reason':'Analyst output is unavailable or invalid'}
    def persist():
        db.execute('UPDATE decisions SET completed_at=?,status=?,result_json=? WHERE id=?',
                   (None if result['status']=='review_pending' else paper.now(),result['status'],d.encode(result),identity));db.commit()
    # Save the analyst before the second network call. No provisional result is eligible.
    original_status=result['status']
    if snapshot and snapshot['complete'] and result.get('proposal'):
        facts=checks(snapshot,result)
        result['status']='review_pending';result['final_check'].update(facts);persist()
        try:
            response=call_role('reviewer',reviewer_payload(snapshot,result,facts,image_url))
            choice=verdict(response)
            roles['reviewer'].update(status='valid_output',verdict=choice)
            accepted=choice=='accept'
            # Recompute from frozen facts; never accept a provider's arithmetic or verdict as enforcement.
            final=checks(snapshot,result)
            passed=bool(accepted and final['account_rules_pass'] and final['strategy_rules_pass'] and final['chart_evidence_pass'] and original_status=='valid')
            eligible=bool(passed and snapshot['order_eligible'] and final['action'] in ('buy','sell','close'))
            final.update(passed=passed,reviewer_accepted=accepted,snapshot_complete=snapshot['complete'],
                         snapshot_order_eligible=snapshot['order_eligible'],order_eligible=eligible,
                         reason='Checks passed' if passed else 'Reviewer rejected' if not accepted else 'Python account, strategy or evidence rules failed')
            result['final_check']=final;result['order_eligible']=eligible
            result['status']='valid' if passed else 'review_rejected' if not accepted else 'blocked_by_rules'
            result['explanation']=(f"Analyst proposed {final['action']}; reviewer verdict {choice}. "
                f"Recorded cash ${final['cash_cents']/100:.2f}; {final['configured_order_size']} share(s) at "
                f"${final['unit_price_cents']/100:.2f} cost ${final['buy_cost_cents']/100:.2f}; held {final['shares']}. "
                f"Python crossover {final['python_crossover']}; account rules {'pass' if final['account_rules_pass'] else 'fail'}, "
                f"strategy {'pass' if final['strategy_rules_pass'] else 'fail'}, chart evidence {'pass' if final['chart_evidence_pass'] else 'fail'}. "
                'These are backend observations, not model reasoning. No order submitted.')
        except d.ProviderFailure as error:
            roles['reviewer']['status']=error.status
            result['status']='review_'+error.status
            result['final_check'].update(reason='Reviewer '+error.status,reviewer_accepted=False,passed=False,order_eligible=False)
    else:
        roles['reviewer']['skip_reason']='No complete snapshot and validated analyst choice to review'
    result['validation']={**(result.get('validation') or {}),'valid':result['final_check']['passed'],
        'reviewer_accepted':result['final_check']['reviewer_accepted'],'reason':result['final_check']['reason']}
    persist()
    return result
