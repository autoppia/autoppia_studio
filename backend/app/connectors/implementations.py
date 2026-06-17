from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import Any

from app.connectors.base import BaseConnector, ConnectorExecutionError, HttpApiConnector, read_text_file
from app.database import knowledge_documents_collection
from app.services.bopa import latest_bopa_pdf


class GenericApiConnector(HttpApiConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        if tool_name.endswith(".search"):
            return self.result(tool_name, {"message": f"{self.config.name} search is not implemented yet.", "query": arguments})
        if tool_name.endswith(".get"):
            return self.result(tool_name, {"message": f"{self.config.name} get is not implemented yet.", "query": arguments})
        if tool_name.endswith(".create") or tool_name.endswith(".update"):
            raise ConnectorExecutionError(f"{tool_name} needs a concrete connector implementation before writes can run.")
        if tool_name == "api.call":
            return await self._api_call(tool_name, arguments)
        raise ConnectorExecutionError(f"{self.config.name} does not implement {tool_name}")

    async def _api_call(self, tool_name: str, arguments: dict[str, Any]):
        base_url = self.config.require("baseUrl", "baseURL", "apiBaseUrl")
        method = str(arguments.get("method") or "GET").upper()
        path = str(arguments.get("path") or "").strip()
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        headers = dict(arguments.get("headers") or {})
        api_key = self.config.get("apiKey", "token", "bearerToken", "apiToken")
        if api_key and not any(key.lower() == "authorization" for key in headers):
            headers["Authorization"] = f"Bearer {api_key}"
        body = arguments.get("body")
        data = await self._request(method, url, headers=headers, json=body if body is not None else None)
        return self.result(tool_name, data)


class TelegramConnector(HttpApiConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        if tool_name != "telegram.send_message":
            raise ConnectorExecutionError(f"Telegram does not implement {tool_name}")
        bot_token = self.config.require("botToken")
        chat_id = str(arguments.get("chatId") or self.config.get("chatId", "defaultChatId")).strip()
        message = str(arguments.get("message") or arguments.get("text") or "").strip()
        if not chat_id:
            raise ConnectorExecutionError("Telegram chatId is required")
        if not message:
            raise ConnectorExecutionError("Telegram message is required")
        data = await self._request(
            "POST",
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
        )
        return self.result(tool_name, {"messageId": data.get("result", {}).get("message_id"), "chatId": chat_id})


class SMTPConnector(BaseConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        if tool_name not in {"smtp.send_email", "gmail.send_email"}:
            raise ConnectorExecutionError(f"SMTP does not implement {tool_name}")
        to_email = str(arguments.get("to") or arguments.get("to_email") or "").strip()
        subject = str(arguments.get("subject") or "").strip()
        body = str(arguments.get("body") or arguments.get("message") or "").strip()
        if not to_email or not subject or not body:
            raise ConnectorExecutionError("Email requires to, subject and body")
        server_host = self.config.require("smtpServer", "host")
        server_port = int(self.config.get("smtpPort", "port", default="465"))
        from_email = self.config.require("email", "userEmail", "defaultFrom")
        password = self.config.require("password")

        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        with smtplib.SMTP_SSL(server_host, server_port, timeout=15) as server:
            server.login(from_email, password)
            server.send_message(msg)
        return self.result(tool_name, {"to": to_email, "subject": subject})


class GmailConnector(SMTPConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        if tool_name == "gmail.send_email" and self.config.get("smtpServer"):
            return await super().execute(tool_name, arguments)
        if tool_name in {"gmail.search_emails", "gmail.read_email"}:
            raise ConnectorExecutionError(f"{tool_name} needs a Gmail API implementation; only the schema and auth validation exist now.")
        raise ConnectorExecutionError(f"Gmail does not implement {tool_name}")


class HoldedConnector(HttpApiConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        api_key = self.config.require("apiKey")
        base_url = self.config.get("baseUrl", default="https://api.holded.com/api")
        headers = {"key": api_key, "Accept": "application/json"}
        if tool_name == "holded.search_clients":
            query = str(arguments.get("query") or "").lower()
            data = await self._request("GET", f"{base_url.rstrip('/')}/invoicing/v1/contacts", headers=headers)
            if isinstance(data, list) and query:
                data = [item for item in data if query in str(item).lower()]
            return self.result(tool_name, data)
        if tool_name == "holded.get_invoice":
            invoice_id = str(arguments.get("invoiceId") or arguments.get("id") or "").strip()
            if not invoice_id:
                raise ConnectorExecutionError("Holded invoiceId is required")
            data = await self._request("GET", f"{base_url.rstrip('/')}/invoicing/v1/documents/invoice/{invoice_id}", headers=headers)
            return self.result(tool_name, data)
        raise ConnectorExecutionError(f"Holded does not implement {tool_name}")


class BOPAConnector(BaseConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        if tool_name not in {"bopa.latest_bulletin_pdf", "bopa.latest_bulletin", "bopa.list_bulletins"}:
            raise ConnectorExecutionError(f"BOPA does not implement {tool_name}")
        data = latest_bopa_pdf()
        if tool_name == "bopa.latest_bulletin_pdf":
            return self.result(tool_name, data)
        if tool_name == "bopa.latest_bulletin":
            return self.result(
                tool_name,
                {
                    "numBOPA": data.get("numBOPA", ""),
                    "number": data.get("number", ""),
                    "publishedAt": data.get("publishedAt", ""),
                    "isExtra": data.get("isExtra", False),
                    "pdfUrl": data.get("pdfUrl", ""),
                },
            )
        return self.result(tool_name, {"items": [data], "source": data.get("apiUrl", "")})


class KnowledgeConnector(BaseConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        if tool_name == "knowledge.search":
            query = str(arguments.get("query") or "").lower().strip()
            cursor = knowledge_documents_collection.find(
                {"companyId": self.config.company_id, "email": self.config.email},
                {"_id": 0},
            ).sort("createdAt", -1)
            docs = await cursor.to_list(length=50)
            results = []
            for doc in docs:
                text = read_text_file(str(doc.get("storagePath") or ""), limit=12000)
                haystack = f"{doc.get('filename', '')}\n{text}".lower()
                if not query or query in haystack:
                    results.append(
                        {
                            "documentId": doc.get("documentId", ""),
                            "filename": doc.get("filename", ""),
                            "snippet": text[:600],
                        }
                    )
            return self.result(tool_name, {"results": results[:10]})
        if tool_name == "knowledge.read_document":
            document_id = str(arguments.get("documentId") or "").strip()
            if not document_id:
                raise ConnectorExecutionError("documentId is required")
            doc = await knowledge_documents_collection.find_one(
                {"companyId": self.config.company_id, "email": self.config.email, "documentId": document_id},
                {"_id": 0},
            )
            if not doc:
                raise ConnectorExecutionError("Document not found")
            return self.result(
                tool_name,
                {
                    "documentId": document_id,
                    "filename": doc.get("filename", ""),
                    "text": read_text_file(str(doc.get("storagePath") or ""), limit=20000),
                },
            )
        raise ConnectorExecutionError(f"Knowledge does not implement {tool_name}")


class WebConnector(BaseConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        if tool_name == "web.fetch":
            import httpx

            url = str(arguments.get("url") or self.config.get("baseUrl", "startUrl")).strip()
            if not url:
                raise ConnectorExecutionError("url is required")
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code >= 400:
                    raise ConnectorExecutionError(f"Web fetch returned {response.status_code}")
                return self.result(tool_name, {"url": str(response.url), "text": response.text[:12000]})
        if tool_name == "browser.navigate":
            return self.result(tool_name, {"tool_call": {"name": "browser.navigate", "arguments": arguments}})
        raise ConnectorExecutionError(f"Web connector does not implement {tool_name}")
