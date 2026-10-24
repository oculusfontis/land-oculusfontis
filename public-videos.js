'use strict';
(() => {
  let videos=window.OF_PUBLIC_VIDEOS||[], topic='全部', expanded=false, remote=false, partial=false;
  const grid=document.querySelector('#of-video-grid'), search=document.querySelector('#of-video-search');
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function render(){
    const query=search.value.trim().toLowerCase();
    const list=videos.filter(v=>v.status==='public'&&(topic==='全部'||v.category===topic||v.topic===topic)&&`${v.title} ${v.description||''}`.toLowerCase().includes(query));
    const shown=expanded||topic!=='全部'||query?list:list.slice(0,3);
    grid.innerHTML=shown.map(v=>`<article class="of-video"><a class="of-thumb" href="https://www.youtube.com/${v.short?'shorts/':'watch?v='}${encodeURIComponent(v.id)}" target="_blank" rel="noopener noreferrer"><img src="https://i.ytimg.com/vi/${encodeURIComponent(v.id)}/hqdefault.jpg" width="480" height="360" loading="lazy" alt="${escape(v.title)}"><span>${v.short?'短影音':escape(v.duration||'影片')} ▶</span></a><div class="of-video-copy"><span>${escape(v.topic||v.category)}</span><h3>${escape(v.title)}</h3>${v.description?`<p>${escape(v.description)}</p>`:''}<a href="https://www.youtube.com/${v.short?'shorts/':'watch?v='}${encodeURIComponent(v.id)}" target="_blank" rel="noopener noreferrer">前往觀看 ↗</a>${v.category!=='都更'?'<a href="#contact">詢問相關需求 →</a>':''}</div></article>`).join('')||'<p>此分類影片陸續公開，可先閱讀手冊，或查看系列播放清單。</p>';
    document.querySelector('#of-video-status').textContent=`顯示 ${shown.length}／${list.length} 支影片${remote?(partial?'｜部分來源暫無法更新，保留可用清單':'｜已同步公開影片'):'｜精選影片清單'}`;
    document.querySelector('#of-video-more').hidden=expanded||topic!=='全部'||!!query||list.length<=3;
    document.querySelectorAll('[data-of-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.ofFilter===topic)));
  }
  document.querySelectorAll('[data-of-filter]').forEach(b=>b.addEventListener('click',()=>{topic=b.dataset.ofFilter;render();}));
  search.addEventListener('input',render);
  document.querySelector('#of-video-more').addEventListener('click',()=>{expanded=true;render();});
  async function sync(){
    try{
      const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),25000);
      let response;try{response=await fetch('/api/videos',{signal:controller.signal});}finally{clearTimeout(timer);}
      if(!response.ok)return;
      const data=await response.json();
      if(!Array.isArray(data.videos)||!data.videos.length)return;
      videos=data.videos.filter(v=>typeof v.title==='string'&&/^[\w-]{11}$/.test(v.id));
      remote=!data.fallback;partial=!!data.partial;render();
    }catch{/* Retain verified seed on timeout or upstream failure. */}
  }
  render();sync();setInterval(()=>{if(!document.hidden)sync();},300000);
})();
