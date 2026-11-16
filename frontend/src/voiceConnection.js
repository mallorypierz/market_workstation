// Browser-only media transport. It has no trading or account API calls.
export class VoiceConnection {
  constructor({audio, update, caption, media=navigator.mediaDevices, Peer=RTCPeerConnection, request=(...args)=>globalThis.fetch(...args)}) {
    Object.assign(this,{audio,update,caption,media,Peer,request});this.generation=0
  }
  stopTracks() {
    for(const track of this.stream?.getTracks() || [])track.stop()
    this.stream=null;this.update({microphone:false})
  }
  cleanup() {
    clearTimeout(this.deadline);clearTimeout(this.closeTimer);this.abort?.abort();this.stopTracks()
    const pc=this.pc,channel=this.channel;this.pc=null;this.channel=null
    if(channel){channel.onclose=null;channel.close()}
    if(pc){pc.onconnectionstatechange=null;pc.close()}
    this.audio.pause();this.audio.srcObject=null;this.started=false
  }
  fail(message) {this.generation++;this.cleanup();this.update({state:'Failed',error:message})}
  async start(decisionId) {
    this.cleanup();const generation=++this.generation
    this.update({state:'Requesting microphone',error:'',microphone:false})
    this.deadline=setTimeout(()=>this.fail('Voice startup timed out; microphone released.'),45000)
    try {
      const stream=await this.media.getUserMedia({audio:true,video:false})
      if(generation!==this.generation){stream.getTracks().forEach(t=>t.stop());return}
      this.stream=stream;this.update({state:'Connecting',microphone:true})
      const pc=this.pc=new this.Peer()
      stream.getTracks().forEach(track=>{pc.addTrack(track,stream);track.onended=()=>{if(this.stream)this.fail('Microphone disconnected')}})
      pc.ontrack=e=>{if(pc!==this.pc)return;this.audio.srcObject=e.streams[0] || new MediaStream([e.track]);this.audio.play().catch(()=>this.update({error:'Press Play audio to hear the voice.'}))}
      pc.onconnectionstatechange=()=>{if(pc===this.pc&&['failed','disconnected','closed'].includes(pc.connectionState))this.fail('Voice connection disconnected; microphone released.')}
      const channel=this.channel=pc.createDataChannel('oai-events')
      channel.onclose=()=>{if(this.channel===channel)this.fail('Voice event channel closed; microphone released.')}
      channel.onmessage=e=>{
        if(this.channel!==channel)return
        let event;try{event=JSON.parse(e.data)}catch{return}
        if(event.type==='session.started'){this.started=true;clearTimeout(this.deadline);this.update({state:'Connected'})}
        else if(event.type==='session.closed'){this.generation++;this.cleanup();this.update({state:'Ended'})}
        else if(event.type==='error')this.fail('Voice provider reported an error; session ended.')
        else if(['session.input_transcript.delta','session.output_transcript.delta'].includes(event.type))this.caption({speaker:event.type.includes('input')?'You':'Voice',text:event.delta || '',start_ms:event.start_ms,end_ms:event.end_ms})
      }
      await pc.setLocalDescription(await pc.createOffer())
      if(generation!==this.generation)return
      if(pc.iceGatheringState!=='complete')await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>{pc.removeEventListener('icegatheringstatechange',check);reject(new Error('ICE gathering timed out'))},10000)
        const check=()=>{if(pc.iceGatheringState==='complete'){clearTimeout(timer);pc.removeEventListener('icegatheringstatechange',check);resolve()}}
        pc.addEventListener('icegatheringstatechange',check);check()
      })
      if(generation!==this.generation)return
      this.abort=new AbortController()
      const response=await this.request('/api/voice/sessions',{method:'POST',headers:{'Content-Type':'application/json'},signal:this.abort.signal,body:JSON.stringify({decision_id:decisionId,sdp:pc.localDescription.sdp})})
      const body=await response.json()
      if(generation!==this.generation)return
      if(!response.ok)throw new Error(body.detail || 'Voice connection failed')
      this.update({summary:body.summary,sessionId:body.session_id})
      await pc.setRemoteDescription({type:'answer',sdp:body.sdp})
      // session.started, not SDP or an open socket, establishes readiness.
    }catch(e){if(generation===this.generation)this.fail(e.name==='NotAllowedError'?'Microphone permission denied. Allow it in browser settings and try again.':e.message || 'Voice startup failed')}
  }
  end(immediate=false) {
    ++this.generation;clearTimeout(this.deadline);this.abort?.abort();this.stopTracks()
    if(!immediate&&this.started&&this.channel?.readyState==='open'){
      this.update({state:'Ending · microphone released'})
      try{this.channel.send(JSON.stringify({type:'session.close'}))}catch{this.cleanup();this.update({state:'Ended; provider finalization unconfirmed'});return}
      this.closeTimer=setTimeout(()=>{this.cleanup();this.update({state:'Ended; provider finalization unconfirmed'})},15000)
    }else{this.cleanup();this.update({state:'Ended'})}
  }
}
