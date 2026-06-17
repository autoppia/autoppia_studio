from __future__ import annotations

import smtplib
import re
from email.mime.text import MIMEText
from html.parser import HTMLParser
from urllib.parse import urljoin
from typing import Any

from app.connectors.base import BaseConnector, ConnectorExecutionError, HttpApiConnector, read_text_file
from app.database import knowledge_documents_collection
from app.services.bopa import latest_bopa_pdf
from app.services.knowledge_index import search_knowledge


class _TextAndLinksParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self._link_href = ""
        self._link_text: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self._link_href = urljoin(self.base_url, attrs_dict["href"])
            self._link_text = []

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "a" and self._link_href:
            label = " ".join(" ".join(self._link_text).split())
            self.links.append({"url": self._link_href, "text": label})
            self._link_href = ""
            self._link_text = []

    def handle_data(self, data: str):
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        self.text_parts.append(text)
        if self._link_href:
            self._link_text.append(text)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text_parts)).strip()


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
        if tool_name not in {"telegram.send_message", "telegram.get_chat"}:
            raise ConnectorExecutionError(f"Telegram does not implement {tool_name}")
        bot_token = self.config.require("botToken")
        chat_id = str(arguments.get("chatId") or self.config.get("chatId", "defaultChatId")).strip()
        if not chat_id:
            raise ConnectorExecutionError("Telegram chatId is required")
        if tool_name == "telegram.get_chat":
            data = await self._request("GET", f"https://api.telegram.org/bot{bot_token}/getChat", params={"chat_id": chat_id})
            chat = data.get("result", {}) if isinstance(data, dict) else {}
            return self.result(tool_name, {"chatId": chat_id, "title": chat.get("title", ""), "type": chat.get("type", ""), "username": chat.get("username", "")})
        message = str(arguments.get("message") or arguments.get("text") or "").strip()
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
        if tool_name not in {"smtp.draft_email", "smtp.send_email", "gmail.send_email"}:
            raise ConnectorExecutionError(f"SMTP does not implement {tool_name}")
        to_email = str(arguments.get("to") or arguments.get("to_email") or "").strip()
        subject = str(arguments.get("subject") or "").strip()
        body = str(arguments.get("body") or arguments.get("message") or "").strip()
        if not to_email or not subject or not body:
            raise ConnectorExecutionError("Email requires to, subject and body")
        from_email = self.config.get("email", "userEmail", "defaultFrom", default="")
        if tool_name == "smtp.draft_email":
            return self.result(tool_name, {"to": to_email, "from": from_email, "subject": subject, "body": body, "readyToSend": True})
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
        if tool_name in {"holded.list_clients", "holded.search_clients"}:
            query = str(arguments.get("query") or "").lower()
            limit = max(1, min(100, int(arguments.get("limit") or 25)))
            data = await self._request("GET", f"{base_url.rstrip('/')}/invoicing/v1/contacts", headers=headers)
            if isinstance(data, list) and query:
                data = [item for item in data if query in str(item).lower()]
            if isinstance(data, list):
                data = data[:limit]
            return self.result(tool_name, data)
        if tool_name in {"holded.list_invoices", "holded.search_invoices"}:
            query = str(arguments.get("query") or "").lower()
            status = str(arguments.get("status") or "").lower()
            limit = max(1, min(100, int(arguments.get("limit") or 25)))
            data = await self._request("GET", f"{base_url.rstrip('/')}/invoicing/v1/documents/invoice", headers=headers)
            if isinstance(data, list):
                if status:
                    data = [item for item in data if status in str(item.get("status", "")).lower()]
                if query:
                    data = [item for item in data if query in str(item).lower()]
                data = data[:limit]
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
        normalized_tool = (
            "knowledge.search" if tool_name.endswith(".search")
            else "knowledge.read_document" if tool_name.endswith(".read_document")
            else "knowledge.list_documents" if tool_name.endswith(".list_documents")
            else "knowledge.stats" if tool_name.endswith(".stats")
            else tool_name
        )
        collection = self.config.get("collectionName", default="")
        vector_database_id = self.config.get("vectorDatabaseId", default="")
        doc_query = {"companyId": self.config.company_id, "email": self.config.email}
        if vector_database_id:
            doc_query["vectorDatabaseId"] = vector_database_id
        if normalized_tool == "knowledge.search":
            query = str(arguments.get("query") or "").strip()
            if not query:
                raise ConnectorExecutionError("query is required")
            k = max(1, min(50, int(arguments.get("topK") or arguments.get("k") or arguments.get("limit") or 5)))
            min_score = float(arguments.get("minScore") or 0)
            filters = {"email": self.config.email}
            if vector_database_id:
                filters["vectorDatabaseId"] = vector_database_id
            if arguments.get("documentId"):
                filters["documentId"] = str(arguments["documentId"])
            if arguments.get("source"):
                filters["source"] = str(arguments["source"])
            results = await search_knowledge(
                company_id=self.config.company_id,
                query=query,
                k=k,
                collection=collection,
                filters=filters,
            )
            if min_score:
                results = [item for item in results if float(item.get("score") or 0) >= min_score]
            return self.result(tool_name, {"results": results, "query": query, "topK": k, "minScore": min_score, "vectorDatabaseId": vector_database_id, "collectionName": collection})
        if normalized_tool == "knowledge.list_documents":
            status = str(arguments.get("status") or "").lower()
            limit = max(1, min(500, int(arguments.get("limit") or 100)))
            query = dict(doc_query)
            if status:
                query["status"] = status
            cursor = knowledge_documents_collection.find(query, {"_id": 0, "storagePath": 0}).sort("createdAt", -1)
            docs = await cursor.to_list(length=limit)
            return self.result(tool_name, {"documents": docs, "count": len(docs), "vectorDatabaseId": vector_database_id, "collectionName": collection})
        if normalized_tool == "knowledge.stats":
            cursor = knowledge_documents_collection.find(doc_query, {"_id": 0, "storagePath": 0})
            docs = await cursor.to_list(length=1000)
            indexed = [doc for doc in docs if str(doc.get("status") or "").lower() in {"indexed", "ready"}]
            total_size = sum(int(doc.get("size") or 0) for doc in docs)
            by_status: dict[str, int] = {}
            for doc in docs:
                status = str(doc.get("status") or "unknown")
                by_status[status] = by_status.get(status, 0) + 1
            return self.result(tool_name, {"documentCount": len(docs), "indexedDocuments": len(indexed), "totalSize": total_size, "byStatus": by_status, "vectorDatabaseId": vector_database_id, "collectionName": collection})
        if normalized_tool == "knowledge.read_document":
            document_id = str(arguments.get("documentId") or "").strip()
            if not document_id:
                raise ConnectorExecutionError("documentId is required")
            max_chars = max(100, min(100000, int(arguments.get("maxChars") or 20000)))
            query = {**doc_query, "documentId": document_id}
            doc = await knowledge_documents_collection.find_one(query, {"_id": 0})
            if not doc:
                raise ConnectorExecutionError("Document not found")
            return self.result(
                tool_name,
                {
                    "documentId": document_id,
                    "filename": doc.get("filename", ""),
                    "text": read_text_file(str(doc.get("storagePath") or ""), limit=max_chars),
                },
            )
        raise ConnectorExecutionError(f"Knowledge does not implement {tool_name}")


class WebConnector(BaseConnector):
    async def execute(self, tool_name: str, arguments: dict[str, Any]):
        if tool_name in {"web.fetch", "web.fetch_text", "web.extract_links"}:
            import httpx

            url = str(arguments.get("url") or self.config.get("baseUrl", "startUrl")).strip()
            if not url:
                raise ConnectorExecutionError("url is required")
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code >= 400:
                    raise ConnectorExecutionError(f"Web fetch returned {response.status_code}")
                final_url = str(response.url)
                if tool_name == "web.fetch":
                    return self.result(tool_name, {"url": final_url, "statusCode": response.status_code, "contentType": response.headers.get("content-type", ""), "text": response.text[:12000]})
                parser = _TextAndLinksParser(final_url)
                parser.feed(response.text)
                if tool_name == "web.fetch_text":
                    max_chars = max(100, min(50000, int(arguments.get("maxChars") or 12000)))
                    return self.result(tool_name, {"url": final_url, "text": parser.text[:max_chars]})
                limit = max(1, min(200, int(arguments.get("limit") or 50)))
                seen = set()
                links = []
                for link in parser.links:
                    key = link["url"]
                    if key in seen:
                        continue
                    seen.add(key)
                    links.append(link)
                    if len(links) >= limit:
                        break
                return self.result(tool_name, {"url": final_url, "links": links, "count": len(links)})
        if tool_name == "browser.navigate":
            return self.result(tool_name, {"tool_call": {"name": "browser.navigate", "arguments": arguments}})
        raise ConnectorExecutionError(f"Web connector does not implement {tool_name}")
