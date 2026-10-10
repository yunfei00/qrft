"""Small management client; all data requests still require the API token."""

PAGE = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>QRFT 控制中心</title>
<style>
body{font:16px system-ui;background:#f3f5f8;color:#172335;margin:2rem auto;max-width:960px;padding:0 1rem}
section{background:white;border:1px solid #dce2eb;border-radius:12px;padding:1.2rem;margin:1rem 0}
input,select,button{font:inherit;padding:.5rem;margin:.3rem;border:1px solid #bbc6d4;border-radius:6px}
button{background:#145bd7;color:white;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}
table{border-collapse:collapse;font:14px system-ui}th,td{text-align:left;border-bottom:1px solid #dce2eb;padding:.45rem;overflow-wrap:anywhere}
label{display:inline-block}#message{min-height:1.5rem}h1,h2{margin:.5rem 0}
</style>
<h1>QRFT 控制中心</h1><p>二进制文件传输 · 分布式视频解码</p>
<section><h2>系统概览</h2><p id="overview">连接后显示系统状态</p></section>
<section><label>API Token <input id="token" type="password" autocomplete="off"></label>
<button id="refresh">连接 / 刷新</button><p>令牌只用于当前页面请求；关闭页面后需重新输入。</p>
<p id="message" role="status"></p></section>
<section><h2>任务</h2><form id="newtask"><input id="name" required maxlength="200" placeholder="任务名称">
<button>创建任务</button></form><label>当前任务 <select id="task"></select></label>
<button id="progress">查看进度</button><button id="missing">导出缺包</button>
<button id="recover">恢复文件</button><pre id="details"></pre></section>
<section><button id="cancel">取消当前任务</button><p>停止领取和提交，保留已收数据包。</p></section>
<section><h2>缺包下载</h2><p>下载结果可用于编码端选择性补传。</p>
<button data-format="txt">missing.txt</button><button data-format="csv">CSV</button>
<button data-format="json">JSON</button></section>
<section><h2>登记视频</h2><p>使用节点可访问的本地或 SMB 路径。一个任务只对应同一原始文件。</p>
<form id="newvideo"><label>视频路径 <input id="path" required maxlength="4096"></label>
<label>时长（秒）<input id="duration" required type="number" min="0.001" step="any"></label>
<button>登记并划分时间片</button></form><pre id="videos"></pre><pre id="slices"></pre></section>
<section><label>重新扫描视频 ID <input id="rescanid" type="number" min="1"></label>
<button id="rescan">重新扫描</button><p>保留已收包，重新扫描全部时间片。</p></section>
<section><h2>节点</h2><pre id="nodes"></pre></section>
<section><h2>系统设置</h2><pre id="settings"></pre></section>
<script>
const el=id=>document.getElementById(id);
const show=(id,value)=>el(id).textContent=JSON.stringify(value,null,2);
function table(id,rows){
 const container=el(id);container.replaceChildren();
 if(!rows.length){container.textContent='暂无记录';return;}
 const grid=document.createElement('table');grid.style.width='100%';
 const keys=Object.keys(rows[0]);const head=document.createElement('tr');
 const labels={id:'ID',task_id:'任务',video_id:'视频',path:'路径',duration_seconds:'时长（秒）',
  created_at:'创建时间',node_id:'节点',last_seen:'最后心跳',status:'状态',processing:'处理中',
  start_ms:'开始（毫秒）',end_ms:'结束（毫秒）',state:'状态',owner:'节点',lease_until:'租约期限',
  attempts:'尝试次数',checkpoint_ms:'扫描位置（毫秒）',lease_token:'租约代次'};
 for(const key of keys){const cell=document.createElement('th');cell.textContent=labels[key]||key;head.append(cell);}
 grid.append(head);
 for(const row of rows){const tr=document.createElement('tr');
  for(const key of keys){const cell=document.createElement('td');cell.textContent=row[key]??'—';tr.append(cell);}
  grid.append(tr);}
 container.append(grid);
}
async function api(path,body){
 if(!el('token').value)throw new Error('请先输入 API Token');
 const headers={'Authorization':'Bearer '+el('token').value};
 if(body!==undefined)headers['Content-Type']='application/json';
 const response=await fetch(path,{method:body===undefined?'GET':'POST',headers,
   body:body===undefined?undefined:JSON.stringify(body)});
 const result=await response.json();
 if(!response.ok){const detail=result.detail||result;
 const messages={'START manifest required':'尚未识别 START，请先完整扫描包含起始帧的视频',
  'START manifest not bound':'尚未绑定 START 元数据，请先扫描起始帧',
  'Invalid API token':'Token 错误，请重新输入','Task cancelled':'任务已取消，不能继续处理',
  'reassembled file hash mismatch':'文件哈希校验失败，请检查冲突和来源并重新扫描',
  'Conflicting START manifest':'START 与任务文件不一致，请为不同文件新建任务',
  'lease_invalid':'租约已失效，请等待节点重新领取'};
 throw new Error(typeof detail==='string'?(messages[detail]||detail):JSON.stringify(detail));}
 return result;
}
async function action(fn){try{const message=await fn();el('message').textContent=typeof message==='string'?message:'操作成功';}
 catch(error){el('message').textContent=error.message;}}
function selected(){if(!el('task').value)throw new Error('请先选择任务');return el('task').value;}
async function progress(){
 const id=selected();const data=await api('/tasks/'+id+'/progress');
 const states={not_started:'未开始',incomplete:'缺包或缺少 FINISH',verified:'校验通过',failed:'校验失败'};
 table('details',[{项目:'数据包',结果:data.stored+' / '+(data.total_packets??'等待 START')},
  {项目:'缺包',结果:data.missing_count??'等待 START'},{项目:'重复 / 冲突',结果:data.duplicates+' / '+data.conflicts},
  {项目:'FINISH',结果:data.finished?'已识别':'未识别'},{项目:'任务',结果:data.cancelled?'已取消':(data.recovery.status==='verified'?'已恢复':'运行中')},
  {项目:'恢复',结果:states[data.recovery.status]||data.recovery.status},
  {项目:'输出文件',结果:data.recovery.path||'尚未生成'}]);
 const videos=await api('/videos?task_id='+id);table('videos',videos);
 const slices=await Promise.all(videos.map(v=>api('/slices?video_id='+v.id)));
 table('slices',slices.flat());
 await updateOverview();
}
async function updateOverview(){const overview=await api('/overview');
 el('overview').textContent='任务 '+overview.tasks+' · 在线节点 '+overview.online_nodes+
  ' · 处理中时间片 '+overview.processing_slices+' · 已验证恢复 '+overview.verified_tasks;}
async function refresh(){
 const tasks=await api('/tasks');const prior=el('task').value;el('task').replaceChildren();
 for(const task of tasks){const option=document.createElement('option');option.value=task.id;
   option.textContent=task.id+' · '+task.name;el('task').append(option);}
 if(tasks.some(t=>String(t.id)===prior))el('task').value=prior;
 const nodes=await api('/nodes');table('nodes',nodes);
 const settings=await api('/settings');table('settings',[{项目:'二维码协议',结果:'v'+settings.protocol_version},
  {项目:'租约 / 时间片 / 重叠',结果:settings.lease_seconds+' / '+settings.slice_seconds+' / '+settings.overlap_seconds+' 秒'},
  {项目:'在线超时',结果:settings.online_timeout_seconds+' 秒'},{项目:'输出目录',结果:settings.output_directory},
  {项目:'修改配置',结果:settings.configuration}]);
 await updateOverview();
 if(tasks.length)await progress();
}
el('refresh').onclick=()=>action(refresh);
el('progress').onclick=()=>action(progress);
el('task').onchange=()=>action(progress);
el('newtask').onsubmit=event=>{event.preventDefault();action(async()=>{
 await api('/tasks',{name:el('name').value});await refresh();});};
el('newvideo').onsubmit=event=>{event.preventDefault();action(async()=>{
 await api('/videos',{task_id:Number(selected()),path:el('path').value,
 duration_seconds:Number(el('duration').value)});await progress();});};
el('missing').onclick=()=>action(async()=>{const result=await api('/tasks/'+selected()+'/missing/export',{});
 return '缺包报告已生成：'+result.directory;});
el('recover').onclick=()=>action(async()=>{await api('/tasks/'+selected()+'/recover',{});
 await progress();});
el('cancel').onclick=()=>action(async()=>{await api('/tasks/'+selected()+'/cancel',{});await progress();});
el('rescan').onclick=()=>action(async()=>{const id=Number(el('rescanid').value);
 if(!Number.isInteger(id)||id<1)throw new Error('请输入有效的视频 ID');
 await api('/videos/'+id+'/rescan',{});await progress();});
for(const button of document.querySelectorAll('[data-format]'))button.onclick=()=>action(async()=>{
 const format=button.dataset.format;
 const response=await fetch('/tasks/'+selected()+'/missing/download?format='+format,
  {headers:{Authorization:'Bearer '+el('token').value}});
 if(!response.ok)throw new Error((await response.json()).detail);
 const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');
 link.href=url;link.download='missing.'+format;link.click();URL.revokeObjectURL(url);
});
</script></html>"""
