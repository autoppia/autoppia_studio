from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.assistant.context import AssistantContext
from app.assistant.service import AutomataAssistantService
from app.database import companies_collection

router = APIRouter(prefix="/embed/v1", tags=["embed"])


class EmbedSessionRequest(BaseModel):
    token: str
    userRef: str = ""
    companyId: str = ""
    hostJwt: str = ""


class EmbedChatRequest(BaseModel):
    sessionToken: str
    message: str
    conversationId: str = ""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _session_secret(public_token: str) -> bytes:
    return (os.getenv("AUTOMATA_EMBED_SESSION_SECRET") or public_token).encode("utf-8")


def _sign(payload: dict[str, Any], public_token: str) -> str:
    raw = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_session_secret(public_token), raw.encode("ascii"), hashlib.sha256).digest()
    return f"{raw}.{_b64(signature)}"


def _verify(token: str, public_token: str) -> dict[str, Any]:
    try:
        raw, signature = token.split(".", 1)
        expected = _b64(hmac.new(_session_secret(public_token), raw.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(raw))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid embed session") from exc
    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Embed session expired")
    return payload


def _verify_hs256_jwt(token: str, secret: str) -> dict[str, Any]:
    try:
        header_raw, payload_raw, signature = token.split(".", 2)
        header = json.loads(_unb64(header_raw))
        if header.get("alg") != "HS256":
            raise ValueError("unsupported alg")
        signing_input = f"{header_raw}.{payload_raw}".encode("ascii")
        expected = _b64(hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(payload_raw))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid host JWT") from exc
    exp = payload.get("exp")
    if exp is not None and int(exp or 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Host JWT expired")
    return payload


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/")


def _origin_allowed(origin: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    clean = _normalize_origin(origin)
    return "*" in allowed or clean in {_normalize_origin(item) for item in allowed}


async def _company_for_public_token(public_token: str, company_id: str = "") -> dict[str, Any]:
    query: dict[str, Any] = {"embedSettings.publicToken": public_token}
    if company_id:
        query["companyId"] = company_id
    company = await companies_collection.find_one(query, {"_id": 0})
    if not company:
        raise HTTPException(status_code=401, detail="Invalid embed token")
    settings = company.get("embedSettings") if isinstance(company.get("embedSettings"), dict) else {}
    if not settings.get("enabled"):
        raise HTTPException(status_code=403, detail="Embed is disabled for this company")
    return company


@router.get("/widget.js", include_in_schema=False)
async def embed_widget_js():
    js = """
(function(){
  var script=document.currentScript;
  var token=script&&script.getAttribute('data-token');
  var userRef=script&&script.getAttribute('data-user-ref')||'';
  var hostJwt=script&&script.getAttribute('data-host-jwt')||'';
  if(!token||window.__automataEmbedLoaded)return;
  window.__automataEmbedLoaded=true;
  var wrap=document.createElement('div');
  wrap.style.cssText='position:fixed;right:20px;bottom:20px;z-index:2147483647';
  var tip=document.createElement('div');
  tip.textContent='Ask Automata';
  tip.style.cssText='position:absolute;right:64px;top:50%;transform:translateY(-50%);white-space:nowrap;border-radius:8px;background:#111827;color:white;padding:8px 12px;font:500 14px system-ui;box-shadow:0 10px 30px rgba(0,0,0,.25);opacity:0;pointer-events:none;transition:opacity .15s';
  var button=document.createElement('button');
  button.type='button';
  button.textContent='>_';
  button.setAttribute('aria-label','Open Automata assistant');
  button.style.cssText='width:56px;height:56px;border:1px solid #3f3f46;border-radius:999px;background:#272735;color:white;font:600 20px ui-monospace,SFMono-Regular,Menlo,monospace;box-shadow:0 10px 30px rgba(0,0,0,.25);cursor:pointer';
  wrap.onmouseenter=function(){tip.style.opacity='1'};
  wrap.onmouseleave=function(){tip.style.opacity='0'};
  var frame=document.createElement('iframe');
  frame.title='Automata assistant';
  frame.style.cssText='position:fixed;right:20px;bottom:72px;width:380px;height:560px;max-width:calc(100vw - 40px);max-height:calc(100vh - 96px);z-index:2147483647;border:1px solid #d1d5db;border-radius:8px;background:white;box-shadow:0 20px 50px rgba(0,0,0,.25);display:none';
  var scriptUrl=script&&script.src?new URL(script.src,window.location.href):new URL('/embed/v1/widget.js',window.location.href);
  var frameUrl=new URL('/embed/v1/frame',scriptUrl.origin);
  frameUrl.searchParams.set('token',token);
  if(userRef){frameUrl.searchParams.set('userRef',userRef)}
  if(hostJwt){frameUrl.searchParams.set('hostJwt',hostJwt)}
  frame.src=(script&&script.getAttribute('data-frame-src'))||frameUrl.href;
  button.onclick=function(){frame.style.display=frame.style.display==='none'?'block':'none'};
  function mount(){wrap.appendChild(tip);wrap.appendChild(button);document.body.appendChild(wrap);document.body.appendChild(frame)}
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',mount)}else{mount()}
})();
""".strip()
    return Response(content=js, media_type="application/javascript")


@router.get("/frame", include_in_schema=False)
async def embed_frame(token: str, userRef: str = "", hostJwt: str = ""):
    html = """
<!doctype html>
<html>
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Automata</title></head>
  <body style="margin:0;font:14px system-ui;background:#f9fafb;color:#111827">
    <div style="padding:16px;border-bottom:1px solid #e5e7eb;background:white;font-weight:600">Automata</div>
    <div id="log" style="height:430px;overflow:auto;padding:16px"></div>
    <form id="form" style="display:flex;gap:8px;padding:12px;border-top:1px solid #e5e7eb;background:white">
      <input id="message" autocomplete="off" placeholder="Ask Automata" style="flex:1;border:1px solid #d1d5db;border-radius:6px;padding:10px">
      <button style="border:0;border-radius:6px;background:#111827;color:white;padding:0 12px">Send</button>
    </form>
    <script>
      var publicToken=__TOKEN__;
      var embedUserRef=__USER_REF__;
      var embedHostJwt=__HOST_JWT__;
      var sessionToken='';
      var conversationId='';
      var log=document.getElementById('log');
      function line(role,text){var node=document.createElement('div');node.style.cssText='margin:0 0 10px;padding:10px;border-radius:8px;background:'+(role==='user'?'#111827;color:white':'white;border:1px solid #e5e7eb');node.textContent=text;log.appendChild(node);log.scrollTop=log.scrollHeight}
      async function ensureSession(){if(sessionToken)return;var res=await fetch('/embed/v1/session',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({token:publicToken,userRef:embedUserRef,hostJwt:embedHostJwt})});if(!res.ok)throw new Error('Embed session failed');var data=await res.json();sessionToken=data.sessionToken}
      document.getElementById('form').addEventListener('submit',async function(event){event.preventDefault();var input=document.getElementById('message');var text=input.value.trim();if(!text)return;input.value='';line('user',text);try{await ensureSession();var res=await fetch('/embed/v1/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({sessionToken:sessionToken,conversationId:conversationId,message:text})});var data=await res.json();if(!res.ok)throw new Error(data.detail||'Chat failed');conversationId=data.conversation.conversationId;var messages=data.conversation.messages||[];var last=messages.slice().reverse().find(function(item){return item.role==='assistant'&&item.content});line('assistant',last?last.content:'Done.')}catch(err){line('assistant',err.message||'Chat failed')}}
      );
    </script>
  </body>
</html>
""".replace("__TOKEN__", json.dumps(token)).replace("__USER_REF__", json.dumps(userRef)).replace("__HOST_JWT__", json.dumps(hostJwt)).strip()
    return Response(content=html, media_type="text/html")


@router.post("/session")
async def create_embed_session(body: EmbedSessionRequest, origin: str = Header(default="")):
    company = await _company_for_public_token(body.token, body.companyId)
    settings = company.get("embedSettings") if isinstance(company.get("embedSettings"), dict) else {}
    allowed = [str(item) for item in settings.get("allowedOrigins") or [] if item]
    if origin and not _origin_allowed(origin, allowed):
        raise HTTPException(status_code=403, detail="Origin is not allowed for this embed")
    now = int(time.time())
    host_payload: dict[str, Any] = {}
    host_secret = str(settings.get("hostJwtSecret") or "")
    if host_secret:
        if not body.hostJwt:
            raise HTTPException(status_code=401, detail="Host JWT is required for this embed")
        host_payload = _verify_hs256_jwt(body.hostJwt, host_secret)
    payload = {
        "companyId": company.get("companyId", ""),
        "email": company.get("email", ""),
        "userRef": str(host_payload.get("sub") or host_payload.get("userRef") or body.userRef).strip(),
        "hostClaims": {key: value for key, value in host_payload.items() if key in {"sub", "userRef", "email", "name", "role"}},
        "iat": now,
        "exp": now + 60 * 60,
    }
    return {"sessionToken": _sign(payload, body.token), "expiresAt": payload["exp"], "companyId": payload["companyId"]}


@router.post("/chat")
async def embed_chat(body: EmbedChatRequest):
    try:
        raw_payload = json.loads(_unb64(body.sessionToken.split(".", 1)[0]))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid embed session") from exc
    company = await companies_collection.find_one({"companyId": raw_payload.get("companyId", "")}, {"_id": 0})
    if not company:
        raise HTTPException(status_code=401, detail="Invalid embed session")
    settings = company.get("embedSettings") if isinstance(company.get("embedSettings"), dict) else {}
    payload = _verify(body.sessionToken, str(settings.get("publicToken") or ""))
    context = AssistantContext(
        email=str(payload.get("email") or ""),
        mode="work",
        company_id=str(payload.get("companyId") or ""),
        route="embed",
        visible_state={"embedUserRef": payload.get("userRef", "")},
        allowed_scopes=("studio:read",),
    )
    service = AutomataAssistantService(context)
    if body.conversationId:
        conversation = await service.send_message(body.conversationId, body.message)
    else:
        conversation = await service.create_conversation(seed_prompt=body.message)
    return {"conversation": conversation}
