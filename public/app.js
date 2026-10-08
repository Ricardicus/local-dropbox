const $ = s => document.querySelector(s);
let storageLost=!$('#storage-error').hidden;
let csrf='', parent=null, items=[], replacement=null, dialogMode='', selected=null, busy=false;
const size = n => n < 1024 ? n+' B' : n < 1048576 ? (n/1024).toFixed(1)+' KB' : n < 1073741824 ? (n/1048576).toFixed(1)+' MB' : (n/1073741824).toFixed(1)+' GB';
async function api(path, options={}) {
  const res=await fetch(path,{...options,headers:{'X-CSRF-Token':csrf,...(options.body && typeof options.body==='string'?{'Content-Type':'application/json'}:{}),...options.headers}});
  const data=await res.json();
  if(data.code==='STORAGE_UNAVAILABLE') storageState(false);
  if(!res.ok){if(res.status===401 && path!='/api/login') showLogin();throw Error(data.error||'Request failed.');}
  return data;
}
function toast(message,error=false){const t=$('#toast');t.textContent=message;t.classList.toggle('bad',error);t.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.hidden=true,5000);}
function showLogin(){if(storageLost)return;csrf='';$('#app').hidden=true;$('#login').hidden=false;$('#rows').replaceChildren();}
async function signedIn(data){csrf=data.csrf;$('#login').hidden=true;$('#app').hidden=false;$('#user-name').textContent=data.username;parent=null;await load();}
$('#login-form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;$('#login-error').textContent='';try{await signedIn(await api('/api/login',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))}));e.target.reset();}catch(err){$('#login-error').textContent=err.message;}finally{button.disabled=false;}};
$('#logout').onclick=async()=>{try{await api('/api/logout',{method:'POST'});showLogin();}catch(e){toast(e.message,true);}};
function view(settings){$('#files-view').hidden=settings;$('#settings-view').hidden=!settings;$('#files-nav').classList.toggle('active',!settings);$('#settings-nav').classList.toggle('active',settings);}
$('#files-nav').onclick=()=>view(false);$('#settings-nav').onclick=()=>view(true);
$('#password-form').onsubmit=async e=>{e.preventDefault();const b=Object.fromEntries(new FormData(e.target));if(b.password!==b.confirm){toast('The new passwords do not match.',true);return;}const button=e.target.querySelector('button');button.disabled=true;try{await api('/api/password',{method:'POST',body:JSON.stringify(b)});e.target.reset();toast('Your password has been updated.');}catch(err){toast(err.message,true);}finally{button.disabled=false;}};
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
async function openFolder(id){parent=id;$('#search').value='';await load();}
async function load(){try{const data=await api('/api/items'+(parent?'?parent='+encodeURIComponent(parent):''));items=data.items;$('#used').textContent=size(data.used);const crumbs=$('#breadcrumbs');crumbs.replaceChildren();const root=node('button','My files');root.onclick=()=>openFolder(null);crumbs.append(root);for(const c of data.breadcrumbs){crumbs.append(node('span','/'));const b=node('button',c.name);b.onclick=()=>openFolder(c.id);crumbs.append(b);}render();}catch(e){toast(e.message,true);}}
function render(){const rows=$('#rows');rows.replaceChildren();const filtered=items.filter(i=>i.name.toLowerCase().includes($('#search').value.toLowerCase()));for(const item of filtered){const tr=node('tr');const name=node('td');const b=node('button',undefined,'file-name');b.append(node('span',item.kind==='folder'?'▰':'▤','file-icon '+item.kind),node('span',item.name));b.title=item.kind==='folder'?'Open folder':'Download file';b.onclick=()=>item.kind==='folder'?openFolder(item.id):download(item.id);name.append(b);tr.append(name,node('td',new Date(item.updated*1000).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}),'date-cell'),node('td',item.kind==='folder'?'—':size(item.size),'size-cell'));const actions=node('td',undefined,'actions');const menu=node('details');const summary=node('summary','•••');summary.setAttribute('aria-label','Actions for '+item.name);menu.append(summary);const entries=node('div',undefined,'action-menu');const add=(label,fn)=>{const b=node('button',label);b.onclick=()=>{menu.open=false;fn();};entries.append(b);};if(item.kind==='file'){add('Download',()=>download(item.id));add('Replace file',()=>{replacement=item;$('#replace-input').click();});}add('Rename',()=>edit('rename',item));add('Move',()=>edit('move',item));add('Delete',async()=>{if(!confirm('Delete “'+item.name+'”? This cannot be undone.'))return;try{await api('/api/items/'+item.id,{method:'DELETE'});await load();toast('Item deleted.');}catch(e){toast(e.message,true);}});menu.append(entries);actions.append(menu);tr.append(actions);rows.append(tr);}$('#empty').hidden=filtered.length>0;$('#empty h3').textContent=items.length?'No matching files':'A fresh space for your work';$('#empty p').textContent=items.length?'Try a different search.':'Drop files here or use Upload files to get started.';$('#count').textContent=items.length+' item'+(items.length===1?'':'s');}
function download(id){window.location.assign('/api/items/'+id+'/download');}
$('#search').oninput=render;
async function upload(files,replace){if(busy){toast('Please wait for the current upload.');return;}busy=true;$('#upload').disabled=true;let done=0;try{for(const file of files){toast('Uploading '+file.name+'…');const params=new URLSearchParams({name:file.name,parent:parent||''});if(replace)params.set('replace',replace.id);await api('/api/upload?'+params,{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});done++;}toast(replace?'File replaced.':done+' file'+(done===1?'':'s')+' uploaded.');}catch(e){toast(e.message+(done?' '+done+' file(s) uploaded successfully.':''),true);}finally{busy=false;$('#upload').disabled=false;await load();}}
$('#upload').onclick=()=>$('#file-input').click();$('#file-input').onchange=async e=>{await upload([...e.target.files]);e.target.value='';};$('#replace-input').onchange=async e=>{if(e.target.files[0])await upload([e.target.files[0]],replacement);e.target.value='';};
const drop=$('#drop-zone');let depth=0;drop.ondragenter=e=>{e.preventDefault();depth++;drop.classList.add('dragging');};drop.ondragover=e=>e.preventDefault();drop.ondragleave=()=>{if(--depth<=0)drop.classList.remove('dragging');};drop.ondrop=e=>{e.preventDefault();depth=0;drop.classList.remove('dragging');upload([...e.dataTransfer.files]);};
async function edit(mode,item){dialogMode=mode;selected=item;$('#dialog-error').textContent='';$('#dialog-title').textContent=mode==='new'?'New folder':mode==='rename'?'Rename item':'Move item';$('#save-dialog').textContent=mode==='new'?'Create folder':'Save changes';$('#name-label').hidden=mode==='move';$('#item-name').required=mode!=='move';$('#item-name').value=item?.name||'';$('#move-label').hidden=mode!=='move';if(mode==='move'){const select=$('#destination');select.replaceChildren();const root=node('option','My files');root.value='';select.append(root);async function collect(id,prefix){const d=await api('/api/items'+(id?'?parent='+id:''));for(const f of d.items.filter(x=>x.kind==='folder'&&x.id!==item.id)){const o=node('option',prefix+f.name);o.value=f.id;select.append(o);await collect(f.id,prefix+f.name+' / ');}}try{await collect(null,'');select.value=item.parent||'';}catch(e){toast(e.message,true);return;}}$('#edit-dialog').showModal();if(mode!=='move')$('#item-name').focus();}
$('#new-folder').onclick=()=>edit('new');$('#close-dialog').onclick=$('#cancel-dialog').onclick=()=>$('#edit-dialog').close();$('#edit-form').onsubmit=async e=>{e.preventDefault();const button=$('#save-dialog');button.disabled=true;try{if(dialogMode==='new')await api('/api/folders',{method:'POST',body:JSON.stringify({name:$('#item-name').value,parent})});else await api('/api/items/'+selected.id,{method:'PATCH',body:JSON.stringify(dialogMode==='move'?{parent:$('#destination').value}:{name:$('#item-name').value})});$('#edit-dialog').close();await load();toast('Changes saved.');}catch(err){$('#dialog-error').textContent=err.message;}finally{button.disabled=false;}};
function storageState(available){
  storageLost=!available;
  $('#storage-error').hidden=available;
  document.body.classList.toggle('storage-unavailable',!available);
  $('#login').inert=!available;$('#app').inert=!available;
  if(!available){
    if($('#edit-dialog').open)$('#edit-dialog').close();
    $('#toast').hidden=true;
  }
}
async function checkStorage(){
  try{
    const res=await fetch('/api/storage',{cache:'no-store'});
    if(!res.ok){storageState(false);return false;}
    const data=await res.json();const wasLost=storageLost;
    storageState(data.available);
    if(data.available && wasLost) await api('/api/me').then(signedIn).catch(()=>showLogin());
    return data.available;
  }catch(e){storageState(false);return false;}
}
$('#retry-storage').onclick=checkStorage;
setInterval(checkStorage,10000);
(async()=>{if(await checkStorage())await api('/api/me').then(signedIn).catch(()=>showLogin());})();
