"""Independent direct-SQL assertions for the controlled Part4.2 browser scenario."""
import json
import sqlite3


def verify(folder,artifacts):
    evidence=json.loads((artifacts/'part42-browser.json').read_text())
    identity=evidence['strategy_id'];account='strategy-'+identity
    with sqlite3.connect(folder/'part42.sqlite3') as db:
        db.row_factory=sqlite3.Row
        cash=db.execute('SELECT cash_cents FROM paper_accounts WHERE id=?',(account,)).fetchone()[0]
        shares=db.execute('SELECT quantity FROM paper_positions WHERE account_id=?',(account,)).fetchone()[0]
        fills=[dict(r) for r in db.execute('SELECT f.* FROM paper_fills f JOIN paper_orders o ON o.id=f.order_id WHERE o.account_id=? ORDER BY f.id',(account,))]
        events=[dict(r) for r in db.execute('SELECT * FROM sma_events WHERE run_id=? ORDER BY id',(identity,))]
        pnl=dict(db.execute('SELECT * FROM paper_pnl WHERE account_id=? ORDER BY id DESC LIMIT 1',(account,)).fetchone())
        assert (cash,shares,pnl['realized_exact'],pnl['unrealized_exact'])==(101000,0,'1000','0')
        assert [(f['quantity'],f['price_cents'],f['receipt_id']) for f in fills]==[(1,10000,7),(1,11000,10)]
        expected=[(None,None,None),(11.5,None,None),(8.5,10,None),(10,10,None),(16,13,'up'),(13,13,None),(4,9,'down')]
        assert [(e['short_value'],e['long_value'],e['signal']) for e in events]==expected
        assert events[4]['receipt_id']==6  # receipt5 was unfinished: no confirmed signal/order
        for fill in fills:
            event=next(e for e in events if e['order_id']==fill['order_id'])
            assert fill['receipt_id']>event['receipt_id']
        assert db.execute('SELECT enabled FROM sma_runs WHERE id=?',(identity,)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM smoke_calls').fetchone()[0]==0
        assert db.execute("SELECT cash_cents FROM paper_accounts WHERE id='live'").fetchone()[0]==100000
        assert not db.execute("SELECT 1 FROM paper_orders WHERE account_id='live'").fetchone()
        assert evidence['final']['account']['cash_cents']==cash
        assert evidence['final']['account']['pnl_current']==pnl
        for actual,shown in zip(fills,evidence['final']['account']['fills']):
            assert all(shown[k]==v for k,v in actual.items())
    for name in ['prefix','prefixLater','full']:
        saved=evidence[name]
        with sqlite3.connect(folder/'backtests'/(saved['run_id']+'.sqlite3')) as db:
            status,stored,frozen=db.execute('SELECT status,result,frozen_input FROM backtest_run').fetchone()
            assert status=='completed' and json.loads(stored)==saved['result']
            assert json.loads(frozen)['provenance']['not_yahoo_evidence'] is True
            expected_fills=2 if name=='full' else 0
            assert db.execute('SELECT COUNT(*) FROM paper_fills').fetchone()[0]==expected_fills
            assert db.execute("SELECT cash_cents FROM paper_accounts WHERE id='backtest'").fetchone()[0]==(101000 if name=='full' else 100000)
    assert evidence['prefix']['result']['decisions']==evidence['prefixLater']['result']['decisions']
    full=evidence['full']['result']
    assert full['equity_curve'][0]['equity']==1000 and min(v['equity'] for v in full['equity_curve'])==901
    assert full['ending_equity']==1010 and full['total_return']==(1010-1000)/1000
    assert full['max_drawdown']==(1000-901)/1000
    report={'status':'passed','data':'OFFLINE constructed; not historical/live evidence','strategy_id':identity,
            'backtest_id':evidence['full']['run_id'],'cash_cents':cash,'shares':shares,'fills':len(fills),'realized':10,'unrealized':0,
            'sma_expected':expected,'sma_sqlite':[(e['short_value'],e['long_value'],e['signal']) for e in events],
            'unfinished_receipt':5,'up_decision_receipt':6,'fill_receipts':[7,10],
            'initial_equity':1000,'minimum_equity':901,'ending_equity':1010,'return':.01,'drawdown':.099,
            'prefix_before_after_future_equal':True,'provider_calls':0,'error_status':evidence['error_status']}
    (artifacts/'part42-sqlite.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
