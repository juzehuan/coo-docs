
(function(){
  var links=[].slice.call(document.querySelectorAll('.toc a'));
  var heads=links.map(function(a){return document.getElementById(a.getAttribute('href').slice(1));});
  var side=document.getElementById('sidebar'),back=document.getElementById('backdrop');

  function setOpen(v){side.classList.toggle('open',v);back.classList.toggle('open',v);}
  document.getElementById('menuBtn').onclick=function(){setOpen(!side.classList.contains('open'));};
  back.onclick=function(){setOpen(false);};
  // 窄屏点完目录就收起，否则浮层一直盖着正文
  links.forEach(function(a){a.onclick=function(){if(window.innerWidth<=1000)setOpen(false);};});

  // 目录高亮：取最后一个已滚过顶部的标题
  var top=document.getElementById('top'),cur=-1,ticking=false;
  function sync(){
    ticking=false;
    var y=window.scrollY+80,idx=0;
    for(var i=0;i<heads.length;i++){if(heads[i]&&heads[i].offsetTop<=y)idx=i;}
    if(idx!==cur){
      if(links[cur])links[cur].classList.remove('active');
      links[idx].classList.add('active');cur=idx;
      // 目录很长，跟随滚动把当前项带进可视区（仅在它已经跑出视野时）。
      // 这里必须直接改 side.scrollTop，不能用 scrollIntoView：后者会把**所有**
      // 祖先滚动容器（含文档本身）一起滚，于是点目录触发的平滑滚动刚走到一半
      // 就被它拽回来——实测点「6.3」后 scrollY 从 0 冲到 384 又退回 211 停住，
      // 页面看起来像是根本没跳转。
      var r=links[idx].getBoundingClientRect(),s=side.getBoundingClientRect();
      if(r.top<s.top+8||r.bottom>s.bottom-8){
        side.scrollTop+=(r.top-s.top)-(side.clientHeight/2-r.height/2);
      }
    }
    top.style.display=window.scrollY>400?'block':'none';
  }
  window.addEventListener('scroll',function(){if(!ticking){ticking=true;requestAnimationFrame(sync);}},{passive:true});
  sync();
  top.onclick=function(){window.scrollTo({top:0,behavior:'smooth'});};
  var pb=document.getElementById('printBtn'); if(pb)pb.onclick=function(){window.print();};

  // 目录过滤：676 行的手册靠肉眼找章节太慢
  var f=document.getElementById('tocfilter');
  f.oninput=function(){
    var q=f.value.trim().toLowerCase();
    links.forEach(function(a){
      a.classList.toggle('hidden',!!q&&a.textContent.toLowerCase().indexOf(q)<0);
    });
  };
  f.onkeydown=function(e){if(e.key==='Escape'){f.value='';f.oninput();f.blur();}};
})();
