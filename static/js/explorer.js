/* No analytics, advertising, or third-party requests. Progressive enhancement. */
(() => {
  'use strict';
  const status = document.getElementById('explorer-status');
  const announce = text => { if(status) status.textContent=text; };
  const makeButton = (text,fn) => { const b=document.createElement('button'); b.type='button'; b.textContent=text; b.addEventListener('click',fn); return b; };
  const submit = form => { if(form.requestSubmit)form.requestSubmit(); else form.submit(); };
  function copy(text) {
    if(navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(()=>announce('Copied to clipboard.'),()=>fallback());
    else fallback();
    function fallback(){const area=document.createElement('textarea');area.value=text;document.body.append(area);area.select();document.execCommand('copy');area.remove();announce('Copied.');}
  }
  function enhanceForms() {
    document.querySelectorAll('form[data-search-form]').forEach(form=>{
      if(form.dataset.enhanced)return; form.dataset.enhanced='true';
      const toolbar=document.createElement('div');toolbar.className='explorer-toolbar';
      toolbar.append(makeButton('Copy this search',()=>copy(location.href)));
      let cleared;
      const chips=document.createElement('div');chips.className='filter-chips';chips.setAttribute('aria-label','Active search filters');
      const fields=()=>Array.from(form.elements).filter(x=>x.name&&!x.disabled&&!['submit','button','hidden'].includes(x.type));
      function refresh(){chips.replaceChildren();let count=0;fields().forEach(field=>{
        if((['checkbox','radio'].includes(field.type)&&!field.checked)||!field.value||field.name==='sort')return;
        count++;
        const label=form.querySelector(`label[for="${CSS.escape(field.id)}"]`)?.textContent.trim()||field.getAttribute('aria-label')||field.name.replaceAll('_',' ');
        chips.append(makeButton(`${label}: ${field.value} ×`,()=>{if(['checkbox','radio'].includes(field.type))field.checked=false;else field.value='';refresh();submit(form);}));
      });toggle.textContent=`Filters (${count})`;}
      let filterDialog;
      const toggle=makeButton('Filters',()=>{
        if(filterDialog){form.classList.add('filters-open');toggle.setAttribute('aria-expanded','true');filterDialog.showModal();}
        else {const open=form.classList.toggle('filters-open');toggle.setAttribute('aria-expanded',String(open));}
      });
      toggle.className='mobile-filter-toggle';toggle.setAttribute('aria-expanded','false');
      const advanced=form.querySelector('[data-advanced-filters]');
      if(advanced){
        advanced.id=advanced.id||'filters-'+form.dataset.searchForm;toolbar.append(toggle);form.classList.add('filters-enhanced');
        if(typeof HTMLDialogElement!=='undefined'){
          filterDialog=document.createElement('dialog');filterDialog.className='search-filter-dialog';filterDialog.setAttribute('aria-label','Advanced search filters');
          filterDialog.id=advanced.id+'-dialog';toggle.setAttribute('aria-controls',filterDialog.id);
          const heading=document.createElement('h2');heading.textContent='Search filters';heading.className='filter-dialog-title';
          const done=makeButton('Done with filters',()=>filterDialog.close());done.className='btn-primary';
          advanced.before(filterDialog);filterDialog.append(heading,advanced,done);
          filterDialog.addEventListener('close',()=>{form.classList.remove('filters-open');toggle.setAttribute('aria-expanded','false');toggle.focus();});
        } else {toggle.setAttribute('aria-controls',advanced.id);}
      }
      toolbar.append(makeButton('Clear filters',()=>{cleared=fields().map(x=>({name:x.name,value:x.value,checked:x.checked}));fields().forEach(x=>{if(['checkbox','radio'].includes(x.type))x.checked=false;else if(x.name==='sort')x.value='newest';else x.value='';});undo.hidden=false;refresh();submit(form);}));
      const undo=makeButton('Undo clear',()=>{if(!cleared)return;fields().forEach(x=>{const old=cleared.find(v=>v.name===x.name&&(!['checkbox','radio'].includes(x.type)||v.value===x.value));if(old){x.value=old.value;x.checked=old.checked;}});undo.hidden=true;refresh();submit(form);});undo.hidden=true;toolbar.append(undo);
      form.prepend(toolbar);form.append(chips);form.addEventListener('change',refresh);form.addEventListener('input',refresh);form.addEventListener('keydown',e=>{if(!filterDialog&&e.key==='Escape'&&form.classList.contains('filters-open')){form.classList.remove('filters-open');toggle.setAttribute('aria-expanded','false');toggle.focus();}});refresh();
    });
  }
  function enhanceTables() {
    document.querySelectorAll('table.research-table').forEach(table=>{
      if(table.dataset.enhanced)return;table.dataset.enhanced='true';
      const headings=Array.from(table.querySelectorAll('thead th')).map(x=>x.textContent.trim());
      table.querySelectorAll('thead th').forEach(x=>x.scope='col');
      table.querySelectorAll('tbody tr').forEach(row=>{Array.from(row.children).forEach((cell,i)=>{cell.dataset.columnLabel=headings[i]||'Value';if(cell.tagName==='TH')cell.scope='row';});});
      const controls=document.createElement('div');controls.className='table-tools';
      const stack=makeButton('Stack on mobile',e=>{const active=table.dataset.stacked!=='true';table.dataset.stacked=String(active);e.currentTarget.setAttribute('aria-pressed',String(active));});stack.setAttribute('aria-pressed',String(table.dataset.stacked==='true'));controls.append(stack);
      const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Visible columns';details.append(summary);
      headings.forEach((name,index)=>{const label=document.createElement('label');label.className='dropdown-option';const box=document.createElement('input');box.type='checkbox';box.checked=true;box.disabled=index===0;box.addEventListener('change',()=>table.querySelectorAll('tr').forEach(row=>{if(row.children[index])row.children[index].hidden=!box.checked;}));label.append(box,document.createTextNode(' '+name));details.append(label);});controls.append(details);table.parentElement.before(controls);
    });
  }
  function syncSearchLinks() {
    document.querySelectorAll('[data-export-search]').forEach(link=>{const url=new URL('/research/exports/',location.origin);url.searchParams.set('dataset',link.dataset.exportSearch);url.searchParams.set('query',location.search.slice(1));link.href=url.pathname+url.search;});
  }
  document.addEventListener('htmx:afterSettle',syncSearchLinks);
  function enhance() {
    syncSearchLinks();
    enhanceForms();enhanceTables();
    document.querySelectorAll('[data-copy]').forEach(el=>{if(el.dataset.copyReady)return;el.dataset.copyReady='true';el.addEventListener('click',()=>copy(el.dataset.copy));});
    document.querySelectorAll('table:not([data-stacked])').forEach(table=>table.querySelectorAll('thead th').forEach(th=>{if(!th.scope)th.scope='col';}));
    document.querySelectorAll('.field-error[data-generated]').forEach(x=>x.remove());
    document.querySelectorAll('[data-search-results] [role=alert] li').forEach(error=>{const name=error.dataset.field;if(!name)return;document.querySelectorAll(`form[data-search-form] [name="${CSS.escape(name)}"]`).forEach(field=>{field.setAttribute('aria-invalid','true');const id='error-'+name;error.id=id;const inline=document.createElement('p');inline.className='field-error';inline.setAttribute('role','alert');inline.dataset.generated='true';inline.textContent=error.textContent;inline.id=id+'-inline-'+Array.from(document.querySelectorAll('[aria-invalid]')).indexOf(field);field.after(inline);field.setAttribute('aria-describedby',inline.id);});});
  }
  document.addEventListener('htmx:beforeRequest',e=>{if(e.detail.elt?.closest('form[data-search-form]')){announce('Searching…');document.querySelectorAll('[data-search-results]').forEach(x=>x.setAttribute('aria-busy','true'));}});
  document.addEventListener('htmx:afterSwap',()=>{document.querySelectorAll('[aria-invalid]').forEach(x=>x.removeAttribute('aria-invalid'));enhance();document.querySelectorAll('[data-search-results]').forEach(x=>{x.setAttribute('aria-busy','false');announce(x.querySelector('[data-result-count]')?.textContent.trim()||x.querySelector('[role=alert]')?.textContent.trim()||'Search results updated.');});});
  const searchError=e=>{const form=e.detail.elt?.closest('form[data-search-form]');if(!form)return;announce('Search failed. Your filters are preserved. Retry the search.');const message=document.createElement('div');message.className='explorer-message';message.setAttribute('role','alert');message.append(document.createTextNode('The search could not finish. Your filters are preserved. '),makeButton('Retry search',()=>{message.remove();submit(form);}));form.after(message);document.querySelectorAll('[data-search-results]').forEach(x=>x.setAttribute('aria-busy','false'));};
  document.addEventListener('htmx:responseError',searchError);
  document.addEventListener('htmx:sendError',searchError);
  document.addEventListener('click',e=>{const link=e.target.closest('a');if(link&&document.querySelector('[data-search-results]')&&link.origin===location.origin){try{sessionStorage.setItem('explorer-position',JSON.stringify({url:location.href,y:scrollY}));}catch{}}});
  window.addEventListener('pageshow',()=>{try{const saved=JSON.parse(sessionStorage.getItem('explorer-position'));if(saved?.url===location.href)scrollTo({top:saved.y,behavior:'instant'});}catch{}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){const menu=document.getElementById('mobile-menu');if(menu&&!menu.classList.contains('hidden'))document.getElementById('menu-toggle')?.click();document.querySelectorAll('details[data-dropdown][open]').forEach(x=>{x.open=false;x.querySelector('summary')?.focus();});}});
  enhance();
})();
