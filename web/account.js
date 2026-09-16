import {signIn,signOut,onUser} from './gateway.js';

// Shared account control for the fleet and effects pages.
export function initAccount(onChange=()=>{}) {
  const root=document.getElementById('account-control');
  root.innerHTML=`<button id="sign-in">Sign in with Google</button>
    <div id="profile" hidden>
      <button id="profile-toggle" class="avatar" aria-label="Open account menu" aria-expanded="false" aria-controls="profile-menu">
        <span id="profile-initials" aria-hidden="true"></span><img id="profile-photo" alt="" referrerpolicy="no-referrer" hidden>
      </button>
      <div id="profile-menu" class="profile-menu" hidden>
        <strong id="profile-name"></strong><span id="profile-email"></span>
        <button id="sign-out">Sign out</button>
      </div>
    </div>`;
  const $=id=>document.getElementById(id),toggle=$('profile-toggle'),menu=$('profile-menu');
  const message=text=>{$('status').textContent=text;};
  function open(value){menu.hidden=!value;toggle.setAttribute('aria-expanded',String(value));}
  toggle.onclick=()=>open(menu.hidden);
  toggle.addEventListener('keydown',event=>{
    if(event.key==='ArrowDown'){event.preventDefault();open(true);$('sign-out').focus();}
  });
  document.addEventListener('click',event=>{if(!root.contains(event.target))open(false);});
  root.addEventListener('focusout',event=>{if(!root.contains(event.relatedTarget))open(false);});
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&!menu.hidden){open(false);toggle.focus();}
  });
  $('sign-in').onclick=async()=>{try{await signIn();}catch{message('Sign-in did not complete. Please try again.');}};
  $('sign-out').onclick=async()=>{
    $('sign-out').disabled=true;
    try{await signOut();$('sign-in').focus();}
    catch{message('Sign-out did not complete. Please try again.');}
    finally{$('sign-out').disabled=false;}
  };
  $('profile-photo').onerror=()=>{$('profile-photo').hidden=true;};
  onUser(user=>{
    open(false);$('sign-in').hidden=!!user;$('profile').hidden=!user;
    const name=user?.displayName||user?.email||'Account';
    $('profile-name').textContent=name;$('profile-email').textContent=user?.email||'';
    $('profile-initials').textContent=name.split(/\s+/).slice(0,2).map(part=>part[0]).join('').toUpperCase();
    const photo=$('profile-photo');photo.hidden=true;photo.removeAttribute('src');
    if(user?.photoURL){photo.hidden=false;photo.src=user.photoURL;}
    message('');return onChange(user);
  });
}
