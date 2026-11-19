class SpkVad extends AudioWorkletProcessor {
  constructor(){
    super();
    this.frameLen=Math.max(1,Math.round(sampleRate*0.02));
    this.buf=new Float32Array(this.frameLen);
    this.fill=0;
    this.prev=0;
    this.cal=[];
    this.ready=false;
    this.on=0.004;
    this.off=0.0024;
    this.above=0;
    this.below=0;
    this.speaking=false;
  }
  process(inputs){
    const ch=inputs[0]&&inputs[0][0];
    if(!ch)return true;
    for(let i=0;i<ch.length;i++){
      this.buf[this.fill++]=ch[i];
      if(this.fill===this.frameLen){this.fill=0;this.emit()}
    }
    return true;
  }
  emit(){
    let sum=0,peak=0,crossings=0;
    const n=this.frameLen;
    for(let i=0;i<n;i++){
      const v=this.buf[i];
      sum+=v*v;
      const a=v<0?-v:v;
      if(a>peak)peak=a;
      if((v>=0)!==(this.prev>=0))crossings++;
      this.prev=v;
    }
    const rms=Math.sqrt(sum/n);
    if(!this.ready){
      this.cal.push(rms);
      if(this.cal.length>=25){
        const s=this.cal.slice().sort((a,b)=>a-b);
        const floor=s[s.length>>1];
        this.on=floor*4.0+0.008;
        this.off=this.on*0.6;
        this.ready=true;
      }
    }
    if(this.ready){
      if(rms>this.on){this.above++;this.below=0}
      else if(rms<this.off){this.below++;this.above=0}
      else{this.above=0;this.below=0}
      if(!this.speaking&&this.above>=3)this.speaking=true;
      else if(this.speaking&&this.below>=8)this.speaking=false;
    }
    this.port.postMessage({rms:rms,peak:peak,zcr:crossings/n,speaking:this.speaking,ready:this.ready});
  }
}
registerProcessor('spkVad',SpkVad);
