class SpkTx extends AudioWorkletProcessor {
  constructor(){
    super();
    this.frameLen=Math.max(1,Math.round(sampleRate*0.1));
    this.buf=new Int16Array(this.frameLen);
    this.fill=0;
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
      let v=ch[i];
      if(v>1)v=1;else if(v<-1)v=-1;
      this.buf[this.fill++]=Math.round(v*32767);
      if(this.fill===this.frameLen){this.fill=0;this.emit()}
    }
    return true;
  }
  emit(){
    const n=this.frameLen;
    const pcm=this.buf.slice(0);
    let sum=0;
    for(let i=0;i<n;i++){
      const v=pcm[i]/32768;
      sum+=v*v;
    }
    const rms=Math.sqrt(sum/n);
    if(!this.ready){
      this.cal.push(rms);
      if(this.cal.length>=10){
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
      else if(this.speaking&&this.below>=3)this.speaking=false;
    }
    this.port.postMessage({pcm:pcm,speaking:this.speaking,ready:this.ready,rms:rms},[pcm.buffer]);
    this.buf=new Int16Array(n);
  }
}
registerProcessor('spkTx',SpkTx);
