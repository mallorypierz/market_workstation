import test from 'node:test'
import assert from 'node:assert/strict'
import {VoiceConnection} from './voiceConnection.js'
function fixture(options={}) {
  const updates=[],sent=[],track={stopped:false,stop(){this.stopped=true}},stream={getTracks:()=>[track]}
  const audio={srcObject:null,pause(){},play:()=>Promise.resolve()}
  class Peer {
    constructor(){this.iceGatheringState='complete';this.connectionState='new';this.closed=false;this.localDescription={sdp:'v=0 offer'}}
    addTrack(){} createDataChannel(){this.channel={readyState:'open',send:e=>sent.push(JSON.parse(e)),close(){this.closed=true}};return this.channel}
    createOffer(){return Promise.resolve({type:'offer',sdp:'v=0 offer'})} setLocalDescription(){return Promise.resolve()}
    setRemoteDescription(d){this.answer=d;return Promise.resolve()} close(){this.closed=true}
  }
  const c=new VoiceConnection({audio,update:v=>updates.push(v),caption:()=>{},media:{getUserMedia:()=>Promise.resolve(stream)},Peer,request:async()=>({ok:true,json:async()=>({session_id:'live_mock',sdp:'v=0 answer',summary:{}})}),...options})
  return {c,track,stream,updates,sent,audio}
}
test('SDP is insufficient; waits for session.started, keeps same channel for follow-up, releases on End',async()=>{
 const f=fixture();await f.c.start('decision');const pc=f.c.pc,ch=f.c.channel
 assert.equal(f.c.started,false);assert.equal(pc.answer.sdp,'v=0 answer')
 ch.onmessage({data:JSON.stringify({type:'session.started'})});assert.equal(f.c.started,true)
 f.c.end();assert.equal(f.track.stopped,true);assert.equal(f.sent[0].type,'session.close')
 ch.onmessage({data:JSON.stringify({type:'session.closed'})});assert.equal(pc.closed,true);assert.equal(f.audio.srcObject,null)
})
test('denied microphone reports failure and sends no request',async()=>{
 let calls=0;const f=fixture({media:{getUserMedia:async()=>{throw Object.assign(new Error(),{name:'NotAllowedError'})}},request:()=>calls++})
 await f.c.start('decision');assert.equal(calls,0);assert.match(f.updates.at(-1).error,/permission denied/)
})
test('failed exchange releases tracks and connection',async()=>{
 const f=fixture({request:async()=>({ok:false,json:async()=>({detail:'controlled failure'})})});await f.c.start('decision')
 assert.equal(f.track.stopped,true);assert.equal(f.c.pc,null);assert.equal(f.updates.at(-1).error,'controlled failure')
})
test('End while permission is pending stops late microphone tracks',async()=>{
 let resolve;const f=fixture({media:{getUserMedia:()=>new Promise(r=>resolve=r)}})
 const pending=f.c.start('decision');f.c.end();resolve(f.stream);await pending
 assert.equal(f.track.stopped,true);assert.equal(f.c.pc,null)
})
test('network disconnect closes connection and microphone',async()=>{
 const f=fixture();await f.c.start('decision');const pc=f.c.pc;pc.connectionState='disconnected';pc.onconnectionstatechange()
 assert.equal(pc.closed,true);assert.equal(f.track.stopped,true)
})
test('default fetch preserves the browser global receiver',async()=>{
 const original=globalThis.fetch;let called=false
 globalThis.fetch=async function(){assert.equal(this,globalThis);called=true;return {ok:true,json:async()=>({session_id:'live_mock',sdp:'v=0 answer',summary:{}})}}
 const f=fixture({request:undefined})
 try{await f.c.start('decision');assert.equal(called,true);assert.equal(f.c.pc.answer.sdp,'v=0 answer')}
 finally{f.c.end(true);globalThis.fetch=original}
})
