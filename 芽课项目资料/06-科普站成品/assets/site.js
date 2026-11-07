
(function(){
function ls(k,d){try{var v=localStorage.getItem(k);return v?JSON.parse(v):d;}catch(e){return d;}}
function save(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
var read=ls("pm_read",{}),quiz=ls("pm_quiz",{});
document.querySelectorAll("[data-read]").forEach(function(b){
  var id=b.getAttribute("data-read");
  if(read[id])b.classList.add("ok"),b.textContent="已学会";
  b.addEventListener("click",function(){
    read[id]=!read[id];save("pm_read",read);
    b.classList.toggle("ok",!!read[id]);
    b.textContent=read[id]?"已学会":"标记已学会";
    paint();
  });
});
function paint(){
  var n=Object.keys(read).filter(function(k){return read[k];}).length;
  document.querySelectorAll("[data-progress]").forEach(function(el){el.textContent=n;});
}
paint();
/* ---- 选择题：选项判定 + 错题本（localStorage）----
   注意：题库由页面内联脚本注入，这里延迟到 load 之后执行，避免脚本顺序问题 */
function initQuiz(){
var ans=ls("pm_q_ans",{}),wrong=ls("pm_q_wrong",[]),QS=window.__QUIZ__||[];
var LV={1:["入门","#0ea5a4"],2:["进阶","#2f7bf6"],3:["挑战","#9333ea"]};
var filter="all";
if(!QS.length){
  document.querySelectorAll("[data-q]").forEach(function(c){
    c.innerHTML='<div class="t">题库未能加载，请强制刷新页面（Ctrl+F5）重试。</div>';
  });
  return;
}
function paintScore(){
  var box=document.getElementById("scoreBox");if(!box)return;
  var today=QS.filter(function(q){return q.date===latestDate;});
  var done=0,right=0,byLv={1:[0,0],2:[0,0],3:[0,0]};
  today.forEach(function(q){
    if(ans[q.id]===undefined)return;
    done++;byLv[q.level][0]++;
    if(ans[q.id]===q.answer){right++;byLv[q.level][1]++;}
  });
  var rate=done?Math.round(right/done*100)+"%":"—";
  var parts=[1,2,3].map(function(l){
    var d=byLv[l][0],r=byLv[l][1];
    return LV[l][0]+" "+(d?Math.round(r/d*100)+"%":"—");
  }).join(" · ");
  box.textContent="已答 "+done+"/"+today.length+" · 正确率 "+rate+" ｜ "+parts;
}
function applyFilter(){
  document.querySelectorAll("[data-q]").forEach(function(c){
    c.style.display=(filter==="all"||c.getAttribute("data-level")===filter)?"":"none";
  });
  var sc=document.getElementById("scoreBox");if(sc)sc.style.display=(filter==="all")?"":"none";
}
document.querySelectorAll("#lvChips .chip").forEach(function(chip){
  chip.addEventListener("click",function(){
    filter=chip.getAttribute("data-lv");
    document.querySelectorAll("#lvChips .chip").forEach(function(x){x.classList.toggle("on",x===chip);});
    applyFilter();
  });
});
function findQ(id){for(var i=0;i<QS.length;i++){if(QS[i].id===id)return QS[i];}return null;}
function renderQ(card,q){
  var picked=ans[q.id];
  var lv=LV[q.level]||LV[1];
  card.innerHTML='<div class="h"><span style="display:inline-block;background:'+lv[1]+';color:#fff;border-radius:980px;padding:2px 9px;font-size:11px;margin-right:8px">'+lv[0]+'</span>'+
    q.date+' · '+(q.kind==="inverse"?"反向边界题":q.kind==="boundary"?"能力边界题":"资讯归属题")+'</div>'+
    '<div class="t">'+q.q.replace(/</g,"&lt;")+'</div><div class="opts"></div><div class="why" style="display:none"></div>';
  var box=card.querySelector(".opts");
  q.options.forEach(function(o,i){
    var b=document.createElement("button");
    b.className="opt"+(picked===i?(i===q.answer?" right":" pick-wrong"):"")+
      (picked!==undefined&&i===q.answer?" right":"");
    b.textContent=String.fromCharCode(65+i)+". "+o;
    b.addEventListener("click",function(){
      if(ans[q.id]!==undefined)return;
      ans[q.id]=i;save("pm_q_ans",ans);
      if(i!==q.answer&&wrong.indexOf(q.id)<0){wrong.push(q.id);save("pm_q_wrong",wrong);}
      renderQ(card,q);renderWrong();paintScore();
    });
    box.appendChild(b);
  });
  var why=card.querySelector(".why");
  if(picked!==undefined){
    why.style.display="block";
    why.innerHTML=(picked===q.answer?'<b style="color:#16a34a">答对了。</b>':'<b style="color:#e11d48">答错了，已加入错题本。</b>')+
      ' '+q.why+' ｜ <a href="k/'+q.eid+'.html">去看这个知识点</a>';
  }
}
document.querySelectorAll("[data-q]").forEach(function(card){
  var q=findQ(card.getAttribute("data-q"));if(q)renderQ(card,q);
});
function renderWrong(){
  var box=document.getElementById("wrongBox");if(!box)return;
  var ids=wrong.filter(function(id){var q=findQ(id);return q&&q.date!==latestDate;});
  var today=wrong.filter(function(id){var q=findQ(id);return q&&q.date===latestDate;});
  var all=ids.concat(today);
  if(!all.length){box.innerHTML='<div class="empty">错题本是空的。答错自动进这里，次日回来重做一遍。</div>';return;}
  box.innerHTML=all.map(function(id){
    var q=findQ(id);
    return '<div class="row"><div class="main"><div class="t">'+q.q.replace(/</g,"&lt;")+'</div>'+
      '<div class="s">正确答案：'+String.fromCharCode(65+q.answer)+'. '+q.options[q.answer]+'</div></div>'+
      '<div class="m">'+(q.date===latestDate?"今日":"回顾")+'</div></div>';
  }).join("")+'<div style="margin-top:10px"><button class="btn ghost" id="clearWrong">清空错题本</button></div>';
  document.getElementById("clearWrong").addEventListener("click",function(){
    wrong=wrong.filter(function(id){var q=findQ(id);return q&&q.date===latestDate&&false;});
    save("pm_q_wrong",wrong);renderWrong();
  });
}
var latestDate=(QS[0]||{}).date||"";
renderWrong();
paintScore();
applyFilter();
}
if(document.readyState==="complete")initQuiz();else window.addEventListener("load",initQuiz);
})();
